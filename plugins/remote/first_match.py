"""The first match, from the job to the summary dialog (plan 126.2).

``build_match`` runs on a job thread: it hashes the local tracks of each mapped folder (cached),
reads the server items of the mapped folder, and matches them. It stores nothing but the hash
cache. ``apply_match`` runs when the person presses Start sync: it writes the links, the conflicts,
the queue rows, the server-only rows and a log line, all in one transaction. Cancel writes nothing.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtee.plugins.api import JobContext, LibraryTrack, PluginContext

from .client import RemoteClient
from .connection import ConnectionManager
from .hashing import hash_tracks
from .matcher import DUPLICATE, LocalTrack, MatchResult, ServerItem, match
from .sources import refresh_server_only
from .store import (
    FolderMapping,
    RemoteStore,
    ServerRow,
    enqueue,
    insert_conflict,
    insert_link,
    server_item_exists,
    unresolved_conflict_id,
    upsert_server_item,
    utc_now,
    write_log,
)
from .tasks import submit
from .ui.first_match_backend import FirstMatchBackend

DIALOG_ID = "first_match"
DONE_SETTING = "first_match_done"
REF_FIRST = "first"
REF_COMPARE = "compare"


@dataclass(frozen=True)
class MatchReport:
    """What the summary shows: the result, and the sizes it was made from."""

    result: MatchResult
    local_total: int
    server_total: int
    skipped: int
    unhashed: int
    mappings: int


@dataclass(frozen=True)
class SyncSummary:
    """What Start sync wrote; a run again writes only what is new."""

    linked: int
    conflicts: int
    queued: int
    server_items: int
    # Every same-audio pair that waits for a side, new or left from an earlier run: the global
    # choice of the summary (plan 129.3) settles these.
    waiting: tuple[str, ...] = ()


def build_match(
    context: PluginContext,
    client: RemoteClient,
    mappings: Sequence[FolderMapping],
    job: JobContext,
) -> MatchReport:
    """Hash, read the server and match, for every mapping. Runs on a job thread."""
    owned = owned_tracks(context, mappings)
    readable_ids = [entry.track.track_id for entry in owned if entry.readable]
    hashed = hash_tracks(context, readable_ids, job)

    per_mapping: list[MatchResult] = []
    local_total = 0
    server_total = 0
    unhashed = 0
    skipped = 0
    for index, mapping in enumerate(mappings):
        local: list[LocalTrack] = []
        for entry in owned:
            if entry.mapping != index:
                continue
            local_total += 1
            hashes = hashed.hashes.get(entry.track.track_id)
            if hashes is None:
                skipped += 1
                local.append(LocalTrack(entry.track.track_id, entry.relative, None, None))
                continue
            local.append(
                LocalTrack(entry.track.track_id, entry.relative, hashes.sha256, hashes.audio_hash)
            )
        server, missing_hash = server_items(client, mapping)
        server_total += len(server)
        unhashed += missing_hash
        per_mapping.append(match(local, server))

    return MatchReport(
        result=MatchResult.merged(per_mapping),
        local_total=local_total,
        server_total=server_total,
        skipped=skipped,
        unhashed=unhashed,
        mappings=len(mappings),
    )


def server_items(client: RemoteClient, mapping: FolderMapping) -> tuple[list[ServerItem], int]:
    """The server items of one mapped folder, relative to it, and how many lack a hash yet."""
    subpath = mapping.server_subpath
    prefix = subpath + "/" if subpath else None
    raw = client.all_items(root_id=mapping.server_root_id, prefix=prefix)
    items: list[ServerItem] = []
    unhashed = 0
    for entry in raw:
        item_path = str(entry.get("relative_path", ""))
        inside = _inside_subpath(item_path, subpath)
        if inside is None:
            continue
        sha256 = entry.get("sha256")
        if not isinstance(sha256, str) or not sha256:
            unhashed += 1
            continue
        audio = entry.get("audio_hash")
        metadata = entry.get("metadata")
        items.append(
            ServerItem(
                item_id=str(entry.get("item_id", "")),
                root_id=str(entry.get("root_id", mapping.server_root_id)),
                relative_path=inside,
                sha256=sha256,
                audio_hash=audio if isinstance(audio, str) and audio else None,
                revision=int(entry.get("revision", 0) or 0),
                item_path=item_path,
                size_bytes=int(entry.get("size_bytes", 0) or 0),
                metadata_json=None
                if metadata is None
                else json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                updated_at_utc=str(entry.get("updated_at_utc", "") or ""),
            )
        )
    return items, unhashed


def apply_match(context: PluginContext, report: MatchReport) -> SyncSummary:
    """Write the result of a match: links, conflicts, queue rows, server-only rows, one log line.

    Runs on a job thread, in one transaction. Rows that exist already are left alone, so a second
    run adds only what is new.
    """
    store = RemoteStore(context)
    result = report.result
    linked = conflicts = queued = server_rows = 0
    with store.transaction() as conn:
        for pair in result.matched:
            if insert_link(
                conn,
                track_id=pair.local.track_id,
                item_id=pair.server.item_id,
                item_revision=pair.server.revision,
                local_sha256=_required(pair.local.sha256),
                audio_hash=pair.local.audio_hash,
                server_path=pair.server.item_path,
            ):
                linked += 1
        waiting: list[str] = []
        for pair in result.tags_differ:
            existing = unresolved_conflict_id(conn, pair.local.track_id, pair.server.item_id)
            if existing is not None:
                waiting.append(existing)
                continue
            waiting.append(
                insert_conflict(
                    conn,
                    track_id=pair.local.track_id,
                    item_id=pair.server.item_id,
                    local=_local_view(pair.local),
                    server=_server_view(pair.server),
                )
            )
            conflicts += 1
        for entry in result.not_matched:
            # A second copy of a track already matched stays out of the push (plan 126.4).
            if entry.reason == DUPLICATE:
                conn.execute(
                    "INSERT OR IGNORE INTO remote_excluded (track_id, reason, at_utc)"
                    " VALUES (?, ?, ?)",
                    (entry.local.track_id, entry.reason, utc_now()),
                )
        for local in result.to_upload:
            if enqueue(conn, kind="upload", track_id=local.track_id, item_id=None):
                queued += 1
        for item in result.server_only:
            if not server_item_exists(conn, item.item_id):
                server_rows += 1
            upsert_server_item(
                conn,
                ServerRow(
                    item_id=item.item_id,
                    root_id=item.root_id,
                    relative_path=item.item_path,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    audio_hash=item.audio_hash,
                    revision=item.revision,
                    metadata_json=item.metadata_json,
                    updated_at_utc=item.updated_at_utc,
                ),
            )
        write_log(
            conn,
            "First match: "
            f"{linked} linked, {queued} to upload, {server_rows} server only, "
            f"{conflicts} tags to decide, {len(result.not_matched)} not matched.",
        )
    return SyncSummary(
        linked=linked,
        conflicts=conflicts,
        queued=queued,
        server_items=server_rows,
        waiting=tuple(waiting),
    )


def _required(value: str | None) -> str:
    if value is None:
        raise ValueError("A matched track has no SHA-256; the match must not have produced it.")
    return value


def _local_view(local: LocalTrack) -> dict[str, Any]:
    return {
        "relative_path": local.relative_path,
        "sha256": local.sha256,
        "audio_hash": local.audio_hash,
    }


def _server_view(item: ServerItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "relative_path": item.item_path,
        "sha256": item.sha256,
        "revision": item.revision,
        "size_bytes": item.size_bytes,
    }


@dataclass(frozen=True)
class OwnedTrack:
    """A library track under a mapping: the mapping's index, the path inside it and readability."""

    track: LibraryTrack
    mapping: int
    relative: str
    readable: bool


def owned_tracks(context: PluginContext, mappings: Sequence[FolderMapping]) -> list[OwnedTrack]:
    """Each library track under a mapping, given to the deepest mapping that holds it.

    A mapping holds the tracks of its local folder (its watched folder, or the local subfolder it
    starts at, plan 129.1). A track outside that folder belongs to no mapping, and the ``relative``
    path of a track is relative to the local folder of its mapping.
    """
    ids = context.library.track_ids()
    if not ids:
        return []
    roots = [mapping.local_folder for mapping in mappings]
    owned: list[OwnedTrack] = []
    for track in context.library.tracks(ids):
        best: tuple[int, str] | None = None
        for index, root in enumerate(roots):
            relative = _relative_to(track.path, root)
            if relative is None:
                continue
            if best is None or len(os.path.abspath(root)) > len(os.path.abspath(roots[best[0]])):
                best = (index, relative)
        if best is not None:
            owned.append(OwnedTrack(track, best[0], best[1], bool(track.readable)))
    return owned


def _relative_to(path: Path, root: Path) -> str | None:
    """The POSIX path of ``path`` inside ``root``, or None when it is not inside it."""
    full = os.path.abspath(path)
    base = os.path.abspath(root).rstrip("\\/")
    if not os.path.normcase(full).startswith(os.path.normcase(base) + os.sep):
        return None
    return full[len(base) + 1 :].replace("\\", "/")


def _inside_subpath(item_path: str, subpath: str) -> str | None:
    if not subpath:
        return item_path
    prefix = subpath + "/"
    if item_path.startswith(prefix):
        return item_path[len(prefix) :]
    return None


class FirstMatchController:
    """Runs the match, shows its summary, and writes the result when the person starts the sync.

    Graphical thread only; the jobs run off it and call back on it.
    """

    def __init__(
        self,
        context: PluginContext,
        connection: ConnectionManager,
        backend: FirstMatchBackend,
    ) -> None:
        self._context = context
        self._connection = connection
        self._backend = backend
        self._store = RemoteStore(context)
        self._running = False
        self._closed = False
        # Settles the same-audio pairs with one side (plan 129.3); set once the conflicts exist.
        self._settle: Callable[[Sequence[str], str], None] | None = None
        backend.bind(self.apply)

    def set_settle(self, settle: Callable[[Sequence[str], str], None]) -> None:
        """Give the function that settles conflicts with one side: ``settle(ids, choice)``."""
        self._settle = settle

    def shutdown(self) -> None:
        self._closed = True

    def on_state(self, state: str) -> None:
        """Connection state changed: the first match runs once, at the first connection."""
        if state == "connected":
            self.first_connection()

    def first_connection(self) -> None:
        if self._context.settings.get(DONE_SETTING, "") == "true":
            return
        if not self._store.mappings():
            return
        self.run(REF_FIRST)

    def run(self, ref: str) -> None:
        """Match in a job, then open the summary. ``ref`` tells the dialog why it opened."""
        client = self._connection.client()
        if client is None:
            self._context.notify("Connect to the server first.")
            return
        mappings = self._store.mappings()
        if not mappings:
            self._context.notify("Link a folder to a server folder first, in Settings > Remote.")
            return
        if self._running:
            self._context.notify("The match with the server is already running.")
            return
        self._running = True
        submit(
            self._context,
            "Matching with the server",
            lambda job: build_match(self._context, client, mappings, job),
            lambda report, error: self._on_matched(ref, report, error),
        )

    def apply(self, report: MatchReport) -> None:
        """Start sync: write the result in a job, then remember that the first match is done.

        The choice for the same-audio pairs is read now, as the person left it in the summary.
        """
        choice = self._backend.current_choice()
        submit(
            self._context,
            "Starting the sync",
            lambda _job: self._write(report),
            lambda summary, error: self._on_applied(summary, error, choice),
        )

    def _write(self, report: MatchReport) -> SyncSummary:
        """Write the result, then give the server-only items their tracks (plan 126.4)."""
        summary = apply_match(self._context, report)
        refresh_server_only(self._context, self._store)
        return summary

    def _on_matched(
        self, ref: str, report: MatchReport | None, error: BaseException | None
    ) -> None:
        self._running = False
        if self._closed:
            return
        if error is not None or report is None:
            self._context.notify(str(error) or type(error).__name__)
            return
        self._backend.show(report, ref)
        self._context.open_dialog(DIALOG_ID, ref)

    def _on_applied(
        self, summary: SyncSummary | None, error: BaseException | None, choice: str = "later"
    ) -> None:
        if self._closed:
            return
        if error is not None or summary is None:
            self._context.notify(str(error) or type(error).__name__)
            return
        self._context.settings.set(DONE_SETTING, "true")
        settling = choice in ("computer", "server") and bool(summary.waiting)
        same = (
            f"{len(summary.waiting)} with the same audio being settled"
            if settling
            else f"{summary.conflicts} tags to decide"
        )
        self._context.notify(
            f"Sync set up: {summary.linked} linked, {summary.queued} to upload, "
            f"{summary.server_items} server only, {same}."
        )
        self._context.availability_changed(None)
        self._context.refresh_ui()
        if settling and self._settle is not None:
            self._settle(summary.waiting, choice)

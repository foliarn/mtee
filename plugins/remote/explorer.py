"""Explorer > Server: the server's folders of the mapped folders, and their tracks (plan 126.9).

The section is a ``SidebarSection`` of the Explorer. Its rows are the folders of each mapped server
folder: a group row per folder, with its depth and the number of tracks below it (``count``). A
click on a folder's name opens a ``remote.folder`` tab with the tracks directly in that folder; its
chevron folds it, and ``on_fold`` remembers the fold state. A linked track plays its local file; a
server-only track plays through its track source (the ``TrackSource`` of the plugin, which
downloads it).

The section itself starts collapsed when the local library has more than 2000 tracks, and expanded
otherwise (``starts_expanded``, read the first time the section is shown). The fold state of each
folder is kept in the plugin settings (``explorer_folds``); a folder not named there is expanded.
A folder reference is ``<server root id>/<folder path>``; an empty path is the root.

The tree is built by a job (``refresh``), so a large server does not stall the window; ``build`` is
the same work on the calling thread.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtee.plugins.api import (
    Contribution,
    PluginContext,
    PluginRowsModel,
    SidebarSection,
    TabHeader,
    TabKind,
    TabRequest,
    TrackListRow,
)

from .sources import source_track_of
from .store import FolderMapping, RemoteStore
from .tasks import submit

TAB_KIND = "remote.folder"
SECTION_ID = "server"
SECTION_TITLE = "Server"
FOLDS_KEY = "explorer_folds"
LARGE_LIBRARY = 2000
_UNNAMED = "Server library"


@dataclass(frozen=True)
class _Item:
    """One server item of a folder, with its local link and its server-only track, if any."""

    item_id: str
    relative_path: str
    metadata_json: str | None
    source_track_id: str | None
    linked_track_id: str | None


class ServerFolders:
    """The Server section of the Explorer and the ``remote.folder`` tab kind."""

    def __init__(self, context: PluginContext, store: RemoteStore) -> None:
        self._context = context
        self._store = store
        self._model = PluginRowsModel()
        self._reading = False
        self._again = False

    @property
    def model(self) -> PluginRowsModel:
        return self._model

    def contributions(self) -> Sequence[Contribution]:
        return [
            SidebarSection(
                SECTION_ID,
                SECTION_TITLE,
                "explorer",
                self._model,
                activate=self.activate,
                on_fold=self.on_fold,
                expanded=self.starts_expanded,
            ),
            TabKind(
                TAB_KIND,
                self.tab_title,
                self.tab_rows,
                header=self.tab_header,
                icon="cloud",
            ),
        ]

    # -- the section -----------------------------------------------------------------------
    def refresh(self) -> None:
        """Build the tree in a job and show it; a refresh asked while one runs runs after it."""
        if self._reading:
            self._again = True
            return
        self._reading = True
        submit(
            self._context,
            "Reading the server folders",
            lambda _job: self.build(),
            self._on_built,
            visible=False,
        )

    def build(self) -> list[dict[str, Any]]:
        """The rows of the tree now, on the calling thread (the job of ``refresh`` runs this)."""
        return self._rows()

    def activate(self, row_id: str) -> TabRequest | None:
        """A click on a folder's name opens the folder's tab."""
        return TabRequest(TAB_KIND, row_id) if row_id else None

    def on_fold(self, row_id: str, expanded: bool) -> None:
        """The user folded or unfolded a folder by its chevron: remember it."""
        self.set_folded(row_id, not expanded)

    def starts_expanded(self) -> bool:
        """The section starts collapsed for a local library of more than 2000 tracks."""
        return len(self._context.library.track_ids()) <= LARGE_LIBRARY

    def set_folded(self, ref: str, folded: bool) -> None:
        """Remember the fold state of one folder and show it again."""
        folds = dict(self._state())
        folds[ref] = folded
        self._context.settings.set_json(FOLDS_KEY, {"folded": folds})
        self._model.replace(self.build())

    def _on_built(self, rows: list[dict[str, Any]] | None, error: BaseException | None) -> None:
        self._reading = False
        if error is not None:
            self._context.log.warning("Reading the server folders failed: %s", error)
        elif rows is not None:
            self._model.replace(rows)
        if self._again:
            self._again = False
            self.refresh()

    # -- the tab ---------------------------------------------------------------------------
    def tab_title(self, ref: str) -> str:
        return self._name_of(ref)

    def tab_header(self, ref: str) -> TabHeader:
        items = self._direct(ref)
        on_computer = sum(1 for item in items if item.linked_track_id)
        return TabHeader(
            title=self._name_of(ref),
            kind_label="Server folder",
            meta=f"{_plural(len(items), 'track')} · {on_computer} on this computer",
        )

    def tab_rows(self, ref: str) -> list[TrackListRow]:
        """The tracks directly in the folder: linked ones play the local file, others the server."""
        rows: list[TrackListRow] = []
        for item in self._direct(ref):
            track = source_track_of(item.item_id, item.relative_path, _metadata(item.metadata_json))
            rows.append(
                TrackListRow(
                    row_id=item.item_id,
                    title=track.title,
                    artist=", ".join(track.artists),
                    album=track.album,
                    duration_seconds=track.duration_us / 1_000_000,
                    track_id=item.linked_track_id or item.source_track_id or "",
                    data={"itemId": item.item_id},
                )
            )
        return rows

    # -- internals -------------------------------------------------------------------------
    def _rows(self) -> list[dict[str, Any]]:
        """The tree of every mapped folder: a mapping's folder first, then the folders below it."""
        mappings = self._store.mappings()
        if not mappings:
            return []
        folded = self._state()
        items = self._all_items()
        rows: list[dict[str, Any]] = []
        emitted: set[str] = set()
        # A mapping inside another one is listed under it, once: the outer mapping goes first.
        for mapping in sorted(mappings, key=lambda found: len(_segments(found.server_subpath))):
            top = _segments(mapping.server_subpath)
            counts: Counter[tuple[str, tuple[str, ...]]] = Counter()
            for root_id, dirs in items:
                if root_id != mapping.server_root_id or dirs[: len(top)] != top:
                    continue
                for depth in range(len(top), len(dirs) + 1):
                    counts[(root_id, dirs[:depth])] += 1
            keys = sorted(set(counts) | {(mapping.server_root_id, top)})
            for root_id, folder in keys:
                ref = _ref(root_id, folder)
                if ref in emitted:
                    continue
                emitted.add(ref)
                rows.append(
                    {
                        "id": ref,
                        "name": folder[-1] if folder else _local_name(mapping),
                        "depth": len(folder) - len(top),
                        "kind": "group",
                        "expanded": not folded.get(ref, False),
                        "count": f"{counts.get((root_id, folder), 0):,}",
                    }
                )
        return rows

    def _all_items(self) -> list[tuple[str, tuple[str, ...]]]:
        found = self._store.connection().execute(
            "SELECT root_id, relative_path FROM remote_server_items"
        )
        return [(str(row["root_id"]), _dirs(str(row["relative_path"]))) for row in found.fetchall()]

    def _direct(self, ref: str) -> list[_Item]:
        root_id, folder = _split(ref)
        found = self._store.connection().execute(
            "SELECT s.item_id, s.relative_path, s.metadata_json, s.source_track_id,"
            " l.track_id AS linked_track_id FROM remote_server_items AS s"
            " LEFT JOIN remote_links AS l ON l.item_id = s.item_id WHERE s.root_id = ?"
            " ORDER BY s.relative_path",
            (root_id,),
        )
        return [
            _Item(
                item_id=str(row["item_id"]),
                relative_path=str(row["relative_path"]),
                metadata_json=row["metadata_json"],
                source_track_id=row["source_track_id"],
                linked_track_id=row["linked_track_id"],
            )
            for row in found.fetchall()
            if _dirs(str(row["relative_path"])) == folder
        ]

    def _name_of(self, ref: str) -> str:
        root_id, folder = _split(ref)
        if folder:
            return folder[-1]
        for mapping in self._store.mappings():
            if mapping.server_root_id == root_id:
                return _local_name(mapping)
        return _UNNAMED

    def _state(self) -> dict[str, bool]:
        """The stored fold state of the folders that are folded (True) or unfolded (False)."""
        raw = self._context.settings.get_json(FOLDS_KEY, None)
        folded = raw.get("folded") if isinstance(raw, dict) else None
        if not isinstance(folded, dict):
            return {}
        return {str(key): bool(value) for key, value in folded.items()}


def _metadata(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _local_name(mapping: FolderMapping) -> str:
    return Path(mapping.local_root_path).name or _UNNAMED


def _segments(text: str) -> tuple[str, ...]:
    return tuple(part for part in text.replace("\\", "/").split("/") if part)


def _dirs(relative_path: str) -> tuple[str, ...]:
    """The folders of a server path, relative to its root (the file name is left out)."""
    return _segments(relative_path)[:-1]


def _ref(root_id: str, folder: Sequence[str]) -> str:
    return f"{root_id}/{'/'.join(folder)}"


def _split(ref: str) -> tuple[str, tuple[str, ...]]:
    root_id, _, rest = ref.partition("/")
    return root_id, _segments(rest)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"

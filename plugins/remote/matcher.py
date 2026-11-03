"""The first match: which local tracks are the server's files (plan 126.2). A pure function.

The inputs are plain values: the hashes of the local tracks and the server items of one mapped
folder, with paths relative to that folder. Nothing here reads a file, the database or the
network, so the rules can be tested as a table.

The rules, in the order they are applied:

1. A local track whose SHA-256 could not be computed is **not matched** (unreadable).
2. Same audio hash on both sides: the pair is found, and the pair is **matched** when the
   SHA-256 values are equal, else **tags differ** (the audio is the same, the tags are not).
3. Several local tracks with that audio hash: the one whose relative path equals the server
   item's is paired (else the first by path); the others are **not matched** (duplicate).
   Several server items with that audio hash: the same rule picks the paired one; the others stay
   **server only**.
4. Where one side has no audio hash, the SHA-256 alone is compared (the same file bytes).
5. A local track with no server item left is **to upload**; the first of a group of local copies
   of the same audio is the one that goes up, the other copies are **not matched** (duplicate).
6. A server item with no local track left is **server only**.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

UNREADABLE = "unreadable"
DUPLICATE = "duplicate"


@dataclass(frozen=True)
class LocalTrack:
    """A local track as the match sees it: ``relative_path`` is inside its mapped folder."""

    track_id: str
    relative_path: str
    sha256: str | None
    audio_hash: str | None


@dataclass(frozen=True)
class ServerItem:
    """A server item of the mapped folder; ``relative_path`` is inside that folder.

    ``item_path`` is the path inside the server root (what the server stores), and the other
    fields are what the server returned, kept so that a server-only row can be stored as it is.
    """

    item_id: str
    root_id: str
    relative_path: str
    sha256: str
    audio_hash: str | None
    revision: int = 0
    item_path: str = ""
    size_bytes: int = 0
    metadata_json: str | None = None
    updated_at_utc: str = ""


@dataclass(frozen=True)
class Pair:
    """A local track and the server item it is the same audio as."""

    local: LocalTrack
    server: ServerItem


@dataclass(frozen=True)
class NotMatched:
    """A local track left out of the sync, with the reason (``unreadable`` or ``duplicate``)."""

    local: LocalTrack
    reason: str


@dataclass(frozen=True)
class MatchResult:
    """The outcome of the match, one list per category."""

    matched: tuple[Pair, ...] = ()
    tags_differ: tuple[Pair, ...] = ()
    to_upload: tuple[LocalTrack, ...] = ()
    server_only: tuple[ServerItem, ...] = ()
    not_matched: tuple[NotMatched, ...] = ()

    @property
    def counts(self) -> dict[str, int]:
        return {
            "matched": len(self.matched),
            "to_upload": len(self.to_upload),
            "server_only": len(self.server_only),
            "tags_differ": len(self.tags_differ),
            "not_matched": len(self.not_matched),
        }

    @staticmethod
    def merged(results: Iterable[MatchResult]) -> MatchResult:
        """Join the results of several mapped folders into one, each list in its order."""
        matched: list[Pair] = []
        tags: list[Pair] = []
        upload: list[LocalTrack] = []
        server_only: list[ServerItem] = []
        not_matched: list[NotMatched] = []
        for result in results:
            matched.extend(result.matched)
            tags.extend(result.tags_differ)
            upload.extend(result.to_upload)
            server_only.extend(result.server_only)
            not_matched.extend(result.not_matched)
        return MatchResult(
            matched=tuple(matched),
            tags_differ=tuple(tags),
            to_upload=tuple(upload),
            server_only=tuple(server_only),
            not_matched=tuple(not_matched),
        )


def _local_key(track: LocalTrack) -> tuple[str, str]:
    return track.relative_path, track.track_id


def _server_key(item: ServerItem) -> tuple[str, str]:
    return item.relative_path, item.item_id


def _group[T](items: Iterable[T], key: Callable[[T], str]) -> dict[str, list[T]]:
    groups: dict[str, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return groups


def _pick_pair(
    locals_: Sequence[LocalTrack], servers: Sequence[ServerItem]
) -> tuple[LocalTrack, ServerItem]:
    """Choose the pair of one group: equal relative path first, then equal SHA-256, then first."""
    for local in locals_:
        for server in servers:
            if local.relative_path == server.relative_path:
                return local, server
    for local in locals_:
        for server in servers:
            if local.sha256 == server.sha256:
                return local, server
    return locals_[0], servers[0]


def match(local: Sequence[LocalTrack], server: Sequence[ServerItem]) -> MatchResult:
    """Match the local tracks of one mapped folder with its server items."""
    matched: list[Pair] = []
    tags_differ: list[Pair] = []
    to_upload: list[LocalTrack] = []
    server_only: list[ServerItem] = []
    not_matched: list[NotMatched] = []

    free_local: list[LocalTrack] = []
    for track in sorted(local, key=_local_key):
        if track.sha256 is None:
            not_matched.append(NotMatched(track, UNREADABLE))
        else:
            free_local.append(track)
    free_server = sorted(server, key=_server_key)

    # Rule 2 and 3: the same audio hash on both sides.
    # The keys below are never empty: the filters keep only the values that are set.
    local_by_audio = _group(
        (track for track in free_local if track.audio_hash is not None),
        lambda track: track.audio_hash or "",
    )
    server_by_audio = _group(
        (item for item in free_server if item.audio_hash is not None),
        lambda item: item.audio_hash or "",
    )
    for audio in sorted(set(local_by_audio) & set(server_by_audio)):
        group_local = local_by_audio[audio]
        group_server = server_by_audio[audio]
        chosen_local, chosen_server = _pick_pair(group_local, group_server)
        if chosen_local.sha256 == chosen_server.sha256:
            matched.append(Pair(chosen_local, chosen_server))
        else:
            tags_differ.append(Pair(chosen_local, chosen_server))
        free_local.remove(chosen_local)
        free_server.remove(chosen_server)
        for copy in group_local:
            if copy is not chosen_local:
                free_local.remove(copy)
                not_matched.append(NotMatched(copy, DUPLICATE))

    # Rule 4: the SHA-256 alone, for the tracks still free.
    local_by_sha = _group(free_local, lambda track: track.sha256 or "")
    server_by_sha = _group(free_server, lambda item: item.sha256)
    for sha in sorted(set(local_by_sha) & set(server_by_sha)):
        group_local = local_by_sha[sha]
        group_server = server_by_sha[sha]
        chosen_local, chosen_server = _pick_pair(group_local, group_server)
        matched.append(Pair(chosen_local, chosen_server))
        free_local.remove(chosen_local)
        free_server.remove(chosen_server)
        for copy in group_local:
            if copy is not chosen_local:
                free_local.remove(copy)
                not_matched.append(NotMatched(copy, DUPLICATE))

    # Rule 5: what is left on this computer goes up; a second copy of the same audio does not.
    seen_audio: set[str] = set()
    for track in sorted(free_local, key=_local_key):
        identity = track.audio_hash if track.audio_hash is not None else f"sha:{track.sha256}"
        if identity in seen_audio:
            not_matched.append(NotMatched(track, DUPLICATE))
        else:
            seen_audio.add(identity)
            to_upload.append(track)

    # Rule 6: what is left on the server is server only.
    server_only.extend(free_server)

    return MatchResult(
        matched=tuple(sorted(matched, key=lambda pair: _local_key(pair.local))),
        tags_differ=tuple(sorted(tags_differ, key=lambda pair: _local_key(pair.local))),
        to_upload=tuple(to_upload),
        server_only=tuple(server_only),
        not_matched=tuple(sorted(not_matched, key=lambda entry: _local_key(entry.local))),
    )

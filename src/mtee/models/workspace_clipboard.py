"""The clipboard of track lists: what Ctrl+C and Ctrl+X hold, and what Ctrl+V does with it.

The clipboard holds references to library tracks, never files. Pasting is decided here, apart
from the Qt models, so the rules can be tested: tracks go to a playlist as new entries, and the
files of a folder are copied or moved by the file move service, which never overwrites a file.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["PastePlan", "TrackClipboard", "plan_drop", "plan_paste"]

LIKED = "liked"


@dataclass(frozen=True, slots=True)
class TrackClipboard:
    """The tracks of a selection, where they came from, and whether they were cut."""

    track_ids: tuple[str, ...] = ()
    # The playlist entries of the selection (empty for a folder), to remove from a cut playlist.
    entry_ids: tuple[str, ...] = ()
    # The list the tracks came from, as "kind:ref" ("folder:..." or "playlist:...").
    source: str = ""
    cut: bool = False

    @property
    def empty(self) -> bool:
        return not self.track_ids


@dataclass(frozen=True, slots=True)
class PastePlan:
    """What to do: ``add`` to a playlist, ``copy`` or ``move`` files into a folder, or ``none``.

    ``remove_from`` is the playlist to take ``remove_entries`` out of after a cut was added
    to another playlist. ``message`` is the refusal when the action is ``none``.
    """

    action: str
    track_ids: tuple[str, ...] = ()
    remove_from: str = ""
    remove_entries: tuple[str, ...] = ()
    message: str = ""


def _refused(message: str) -> PastePlan:
    return PastePlan("none", message=message)


def plan_paste(clipboard: TrackClipboard, target_kind: str, target_ref: str) -> PastePlan:
    """Decide what pasting ``clipboard`` into the list ``target_kind:target_ref`` does."""
    if clipboard.empty:
        return _refused("There is nothing to paste.")
    target = f"{target_kind}:{target_ref}"
    if target_kind == "playlist":
        if target_ref == LIKED:
            return _refused("Tracks cannot be pasted into Liked tracks.")
        if clipboard.cut and clipboard.source == target:
            return _refused("These tracks are already in this playlist.")
        source_playlist = clipboard.source.partition(":")[2]
        removes = (
            clipboard.cut
            and clipboard.source.startswith("playlist:")
            and source_playlist != LIKED
            and bool(clipboard.entry_ids)
        )
        return PastePlan(
            "add",
            clipboard.track_ids,
            remove_from=source_playlist if removes else "",
            remove_entries=clipboard.entry_ids if removes else (),
        )
    if target_kind == "folder":
        return PastePlan("move" if clipboard.cut else "copy", clipboard.track_ids)
    return _refused("Paste the tracks into a playlist or a folder list.")


def plan_drop(
    track_ids: tuple[str, ...], source: str, target_kind: str, target_ref: str, copy: bool
) -> PastePlan:
    """Decide what dropping tracks of ``source`` on the list ``target_kind:target_ref`` does.

    A drop on a playlist adds the tracks; a drop on a folder list moves the files, or copies them
    with ``copy`` (Ctrl held). A drop on the list the tracks come from does nothing.
    """
    if not track_ids:
        return _refused("There is nothing to drop.")
    if source == f"{target_kind}:{target_ref}":
        return _refused("")
    if target_kind == "playlist":
        if target_ref == LIKED:
            return _refused("Tracks cannot be dropped on Liked tracks.")
        return PastePlan("add", track_ids)
    if target_kind == "folder":
        return PastePlan("copy" if copy else "move", track_ids)
    return _refused("Drop the tracks on a playlist or a folder list.")

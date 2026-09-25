from __future__ import annotations

from mtee.models.file_clipboard_model import FileClipboardModel


def test_clipboard_snapshots_unique_track_ids_and_clears_successful_cut_items() -> None:
    clipboard = FileClipboardModel()

    clipboard.cutSelection(["a", "b", "a"])
    assert clipboard.mode == "move"
    assert clipboard.trackIds == ["a", "b"]

    clipboard.removeCompleted(["b"])
    assert clipboard.mode == "move"
    assert clipboard.trackIds == ["a"]
    clipboard.removeCompleted(["a"])
    assert clipboard.mode == ""
    assert clipboard.trackIds == []


def test_copy_replaces_previous_snapshot_without_marking_it_as_cut() -> None:
    clipboard = FileClipboardModel()
    clipboard.cutSelection(["old"])

    clipboard.copySelection(["new"])

    assert clipboard.mode == "copy"
    assert clipboard.trackIds == ["new"]

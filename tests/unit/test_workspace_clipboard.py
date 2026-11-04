"""What Ctrl+V and a drop do with tracks held from a list (plan: feedback batch 136)."""

from __future__ import annotations

from mtee.models.workspace_clipboard import TrackClipboard, plan_drop, plan_paste

FROM_PLAYLIST = TrackClipboard(("t1", "t2"), ("e1", "e2"), "playlist:a", cut=True)
FROM_FOLDER = TrackClipboard(("t1",), (), "folder:root/", cut=True)


def test_paste_into_a_playlist_adds_and_a_cut_playlist_loses_its_entries() -> None:
    plan = plan_paste(FROM_PLAYLIST, "playlist", "b")
    assert (plan.action, plan.track_ids) == ("add", ("t1", "t2"))
    assert (plan.remove_from, plan.remove_entries) == ("a", ("e1", "e2"))
    copied = TrackClipboard(("t1",), ("e1",), "playlist:a", cut=False)
    assert plan_paste(copied, "playlist", "b").remove_from == ""


def test_a_cut_from_a_folder_pasted_into_a_playlist_only_adds() -> None:
    plan = plan_paste(FROM_FOLDER, "playlist", "b")
    assert (plan.action, plan.remove_from) == ("add", "")


def test_paste_into_a_folder_copies_or_moves_the_files() -> None:
    assert plan_paste(FROM_FOLDER, "folder", "root/sub").action == "move"
    assert plan_paste(TrackClipboard(("t1",), (), "folder:x/", False), "folder", "r/").action == (
        "copy"
    )
    assert plan_paste(FROM_PLAYLIST, "playlist", "a").action == "none"


def test_nothing_is_pasted_into_liked_tracks_or_an_empty_clipboard() -> None:
    assert plan_paste(FROM_FOLDER, "playlist", "liked").action == "none"
    assert plan_paste(TrackClipboard(), "folder", "r/").message
    assert plan_paste(FROM_FOLDER, "settings", "").action == "none"


def test_a_drop_adds_to_a_playlist_moves_to_a_folder_and_copies_with_ctrl() -> None:
    assert plan_drop(("t1",), "folder:r/", "playlist", "p", False).action == "add"
    assert plan_drop(("t1",), "playlist:p", "folder", "r/sub", False).action == "move"
    assert plan_drop(("t1",), "playlist:p", "folder", "r/sub", True).action == "copy"
    assert plan_drop(("t1",), "folder:r/", "folder", "r/", True).action == "none"
    assert plan_drop(("t1",), "folder:r/", "playlist", "liked", False).action == "none"

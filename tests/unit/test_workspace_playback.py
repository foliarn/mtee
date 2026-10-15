"""Unit tests for workspace_playback."""

from __future__ import annotations

from unittest.mock import MagicMock

from mtee.models.workspace_playback import (
    EnqueueTracker,
    build_playlist_track_playback,
    filter_enqueue_targets,
    format_playback_source_title,
    prepare_playlist_playback_rows,
    reorder_playlist_items,
    resolve_folder_playback_rows,
)


def test_enqueue_tracker_in_order() -> None:
    tracker = EnqueueTracker()
    assert tracker.next_sequence() == 1
    assert tracker.next_sequence() == 2

    # Batch 1 arrives first
    ready1 = tracker.record_ready(1, {"batch": 1})
    assert ready1 == [{"batch": 1}]

    # Batch 2 arrives next
    ready2 = tracker.record_ready(2, {"batch": 2})
    assert ready2 == [{"batch": 2}]


def test_enqueue_tracker_out_of_order() -> None:
    tracker = EnqueueTracker()
    seq1 = tracker.next_sequence()
    seq2 = tracker.next_sequence()
    seq3 = tracker.next_sequence()

    # Batch 2 and 3 arrive before 1
    assert tracker.record_ready(seq2, {"batch": 2}) == []
    assert tracker.record_ready(seq3, {"batch": 3}) == []

    # Batch 1 arrives: should yield 1, 2, and 3 in order
    consecutive = tracker.record_ready(seq1, {"batch": 1})
    assert len(consecutive) == 3
    assert [b["batch"] for b in consecutive] == [1, 2, 3]


def test_filter_enqueue_targets(tmp_path) -> None:
    valid_file = tmp_path / "valid.mp3"
    valid_file.write_text("audio content")

    targets = [
        {"id": "t1", "trackId": "t1", "path": str(valid_file), "available": True},
        {"id": "t2", "trackId": "t2", "path": "non_existent.mp3", "available": True},
        {"id": "t3", "trackId": "t3", "path": str(valid_file), "available": False},
        "invalid_target_type",
    ]

    cancelled_mock = MagicMock()
    result = filter_enqueue_targets(
        targets,  # type: ignore
        source="playlist:p1",
        source_title="My Playlist",
        check_cancelled=cancelled_mock,
    )

    assert cancelled_mock.call_count == 4
    assert len(result["rows"]) == 1
    assert result["rows"][0]["id"] == "t1"
    assert result["rejected"] == 3
    assert result["source"] == "playlist:p1"
    assert result["source_title"] == "My Playlist"


def test_prepare_playlist_playback_rows() -> None:
    rows = [
        {"trackId": "t1", "available": True},
        {"trackId": "t2", "available": False},
        {"trackId": "", "available": True},
        {"trackId": "t3", "available": True},
    ]

    prepared = prepare_playlist_playback_rows(rows, shuffled=False)
    assert len(prepared) == 2
    assert [r["id"] for r in prepared] == ["t1", "t3"]

    shuffled = prepare_playlist_playback_rows(rows, shuffled=True)
    assert len(shuffled) == 2
    assert set(r["id"] for r in shuffled) == {"t1", "t3"}


def test_build_playlist_track_playback() -> None:
    captured = [
        {"id": "entry1", "trackId": "t1", "available": True},
        {"id": "entry2", "trackId": "t2", "available": True},
        {"id": "entry3", "trackId": "t3", "available": False},
    ]

    # Valid track
    res = build_playlist_track_playback(captured, "entry2", "Favorites", "playlist:fav")
    assert res is not None
    ids, index, title, playable = res
    assert ids == ["t1", "t2"]
    assert index == 1
    assert title == "Favorites"
    assert len(playable) == 2

    # Unavailable track
    assert build_playlist_track_playback(captured, "entry3", "Fav", "playlist:fav") is None

    # Unknown entry
    assert build_playlist_track_playback(captured, "non_existent", "Fav", "playlist:fav") is None


def test_resolve_folder_playback_rows() -> None:
    # 1. Supplied rows takes priority
    supplied = [{"id": "s1"}, {"id": "s2"}]
    order, rows = resolve_folder_playback_rows(
        supplied, None, {}, None, lambda r, rel: [], {}, "s1"
    )
    assert order == ["s1", "s2"]
    assert rows == supplied

    # 2. Model rows
    model_rows = [{"id": "m1"}, {"id": "m2"}]
    order2, rows2 = resolve_folder_playback_rows(
        None, model_rows, {}, None, lambda r, rel: [], {}, "m1"
    )
    assert order2 == ["m1", "m2"]
    assert rows2 == model_rows


def test_format_playback_source_title() -> None:
    r1 = "00000000-0000-0000-0000-000000000001"
    roots = {r1: {"name": "Music Root"}}
    artist_entry = MagicMock()
    artist_entry.name = "The Beatles"

    # Folder relative
    assert (
        format_playback_source_title(
            f"folder:{r1}/Rock/Classics", {}, roots, lambda k: None, lambda k: ""
        )
        == "Classics"
    )

    # Folder root
    assert (
        format_playback_source_title(
            f"folder:{r1}", {}, roots, lambda k: None, lambda k: ""
        )
        == "Music Root"
    )

    # Artist
    assert (
        format_playback_source_title(
            "artist:beatles", {}, roots, lambda k: artist_entry, lambda k: ""
        )
        == "The Beatles"
    )

    # Fallback to album / title
    assert (
        format_playback_source_title(
            "unknown", {"album": "Abbey Road"}, roots, lambda k: None, lambda k: ""
        )
        == "Abbey Road"
    )


def test_reorder_playlist_items() -> None:
    entries = ["e1", "e2", "e3", "e4"]
    reordered = reorder_playlist_items(entries, ["e4"], "e2")
    assert reordered == ["e1", "e4", "e2", "e3"]

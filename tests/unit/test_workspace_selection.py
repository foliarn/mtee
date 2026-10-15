"""Unit tests for workspace_selection."""

from __future__ import annotations

from mtee.models.workspace_selection import (
    calculate_selection,
    format_info_fields_read_only,
    format_info_file_fields,
    resolve_local_track_ids,
)


def test_calculate_selection_single_mode() -> None:
    selected, anchor = calculate_selection(["t1", "t2"], "t1", "t3", mode="single")
    assert selected == ["t3"]
    assert anchor == "t3"


def test_calculate_selection_toggle_mode() -> None:
    # Add new item
    selected, anchor = calculate_selection(["t1"], "t1", "t2", mode="toggle")
    assert selected == ["t1", "t2"]
    assert anchor == "t2"

    # Remove existing item
    selected, anchor = calculate_selection(["t1", "t2"], "t2", "t1", mode="toggle")
    assert selected == ["t2"]
    assert anchor == "t2"


def test_calculate_selection_range_mode() -> None:
    ordered = ["t1", "t2", "t3", "t4", "t5"]
    selected, anchor = calculate_selection(["t2"], "t2", "t4", mode="range", ordered=ordered)
    assert selected == ["t2", "t3", "t4"]
    assert anchor == "t2"

    # Reverse range
    selected, anchor = calculate_selection(["t4"], "t4", "t2", mode="range", ordered=ordered)
    assert selected == ["t2", "t3", "t4"]
    assert anchor == "t4"


def test_resolve_local_track_ids() -> None:
    playlist_rows = [
        {"id": "entry-1", "entryId": "entry-1", "trackId": "track-1"},
        {"id": "entry-2", "entryId": "entry-2", "trackId": "track-2"},
    ]
    assert resolve_local_track_ids(["entry-1", "entry-2"], playlist_rows) == ["track-1", "track-2"]
    assert resolve_local_track_ids(["track-1"], playlist_rows) == ["track-1"]
    assert resolve_local_track_ids(["unknown"], playlist_rows) == []

    folder_rows = [
        {"id": "track-1", "path": "C:/a.mp3"},
        {"id": "track-2", "path": "C:/b.mp3"},
    ]
    assert resolve_local_track_ids(["track-1"], folder_rows) == ["track-1"]
    assert resolve_local_track_ids(["other-id"], folder_rows) == ["other-id"]


def test_format_info_fields() -> None:
    track = {"title": "Song", "artist": "Band", "path": "C:/song.mp3", "duration": "3:20"}
    read_only = format_info_fields_read_only(track)
    assert {"label": "Title", "value": "Song"} in read_only
    assert {"label": "Artist", "value": "Band"} in read_only

    file_info = format_info_file_fields(track)
    assert {"label": "Path", "value": "C:/song.mp3"} in file_info
    assert {"label": "Duration", "value": "3:20"} in file_info

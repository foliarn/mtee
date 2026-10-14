"""Pure helpers of the Explorer workspace: folder references, local paths and row ordering."""

from __future__ import annotations

import os

import pytest

from mtee.models.workspace_rows import (
    SORT_KEYS,
    camelot_order,
    copy_column_preferences,
    folder_from_track,
    local_path,
    parse_folder_id,
    parse_folder_ref,
    sort_rows,
)
from mtee.persistence.workspace_repository import DEFAULT_COLUMN_PREFERENCES

ROOT = "0f8fad5b-d9cb-469f-a165-70867728950e"


def test_a_root_id_and_a_folder_id_name_a_root_and_a_relative_folder() -> None:
    assert parse_folder_id(f"root:{ROOT}") == (ROOT, "")
    assert parse_folder_id(f"folder:{ROOT}/") == (ROOT, "")
    assert parse_folder_id(f"folder:{ROOT}/Artists/Album") == (ROOT, "Artists/Album")
    assert parse_folder_id("playlist:abc") is None


@pytest.mark.parametrize(
    "ref",
    ["", "not-a-uuid/Album", f"{ROOT}/../outside", f"{ROOT}/Album/../../outside"],
)
def test_a_folder_reference_outside_its_root_or_without_a_root_is_refused(ref: str) -> None:
    with pytest.raises(ValueError):
        parse_folder_ref(ref)


def test_a_folder_reference_keeps_a_posix_relative_path() -> None:
    assert parse_folder_ref(ROOT) == (ROOT, "")
    assert parse_folder_ref(f"{ROOT}/A/B") == (ROOT, "A/B")


def test_a_dropped_file_url_becomes_a_local_path_and_plain_text_is_trimmed() -> None:
    assert local_path("  C:/Music  ") == "C:/Music"
    assert local_path("file://server/share/Music%20Box") == "//server/share/Music Box"
    expected = "C:/Music Box" if os.name == "nt" else "/C:/Music Box"
    assert local_path("file:///C:/Music%20Box") == expected


def test_camelot_order_reads_the_code_or_the_key_and_ignores_other_values() -> None:
    assert camelot_order({"keyCamelot": "10a"}) == (10, 0)
    assert camelot_order({"key": "9B"}) == (9, 1)
    assert camelot_order({"key": "13A"}) is None
    assert camelot_order({"key": "C minor"}) is None
    assert camelot_order({}) is None


def test_rows_sort_numerically_and_keep_missing_values_last_in_title_order() -> None:
    rows = [
        {"id": "1", "title": "b", "bpm": "128"},
        {"id": "2", "title": "a", "bpm": ""},
        {"id": "3", "title": "c", "bpm": 90},
        {"id": "4", "title": "d", "bpm": "fast"},
    ]
    assert [row["id"] for row in sort_rows(rows, "bpm", True)] == ["3", "1", "2", "4"]
    assert [row["id"] for row in sort_rows(rows, "bpm", False)] == ["1", "3", "2", "4"]


def test_the_index_and_unknown_keys_keep_the_original_order() -> None:
    rows = [{"id": "2", "title": "b"}, {"id": "1", "title": "a"}]
    assert "index" in SORT_KEYS
    assert sort_rows(rows, "index", False) == rows
    assert sort_rows(rows, "not-a-column", True) == rows
    assert sort_rows(rows, "index", True) is not rows


def test_column_preferences_are_copied_and_fall_back_to_the_defaults() -> None:
    saved = {"order": ["title"], "hidden": ["bpm"], "widths": {"title": 200}, "showArtwork": 0}
    copied = copy_column_preferences(saved)
    assert copied == {
        "order": ["title"],
        "hidden": ["bpm"],
        "widths": {"title": 200},
        "showArtwork": False,
    }
    copied["order"].append("artist")
    assert saved["order"] == ["title"]
    assert copy_column_preferences(None)["order"] == list(DEFAULT_COLUMN_PREFERENCES["order"])


def test_the_folder_of_a_track_is_its_relative_parent() -> None:
    assert folder_from_track({"relativePath": "Artists/Album/track.flac"}) == "Artists/Album"
    assert folder_from_track({"relativePath": "track.flac"}) == ""
    assert folder_from_track({}) == ""

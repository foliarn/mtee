"""Unit tests for workspace_artists."""

from __future__ import annotations

from unittest.mock import MagicMock

from mtee.domain.artist_index import ArtistEntry, ArtistIndex
from mtee.models.workspace_artists import (
    decide_artist_index_effects,
    format_artist_decision_message,
    prepare_artist_playback_rows,
    sort_artist_tracks,
)


def test_format_artist_decision_message() -> None:
    origins, msg = format_artist_decision_message(["David Bowie", "Queen"], one_artist=True)
    assert "david bowie" in origins
    assert "queen" in origins
    assert msg == "Kept “David Bowie”, “Queen” as one artist."

    _, split_msg = format_artist_decision_message(["Daft Punk"], one_artist=False)
    assert split_msg == "Split “Daft Punk” into separate artists."


def test_sort_artist_tracks() -> None:
    tracks = [
        {"album": "B", "trackNumber": 2, "title": "Song 2"},
        {"album": "A", "trackNumber": 1, "title": "Song 1"},
    ]
    sorted_tracks = sort_artist_tracks(tracks)
    assert sorted_tracks[0]["album"] == "A"
    assert sorted_tracks[1]["album"] == "B"


def test_prepare_artist_playback_rows() -> None:
    rows = [
        {"id": "t1", "title": "Song 1"},
        "invalid_row",
        {"title": "No ID"},
        {"id": "t2", "title": "Song 2"},
    ]
    prepared = prepare_artist_playback_rows(rows, shuffled=False)
    assert len(prepared) == 2
    assert prepared[0]["id"] == "t1"
    assert prepared[1]["id"] == "t2"


def test_decide_artist_index_effects() -> None:
    entry_bowie = ArtistEntry(
        key="bowie", name="David Bowie", track_count=2, origins=("David Bowie",)
    )
    entry_queen = ArtistEntry(key="queen", name="Queen", track_count=1, origins=("Queen",))

    new_index = MagicMock(spec=ArtistIndex)
    new_index.artists = [entry_bowie, entry_queen]
    new_index.entry.side_effect = lambda k: {"bowie": entry_bowie, "queen": entry_queen}.get(k)
    new_index.tracks_by_artist = {"bowie": ["t1", "t2"], "queen": ["t3"]}

    prev_index = MagicMock(spec=ArtistIndex)
    prev_index.tracks_by_artist = {"bowie": ["t1"], "queen": ["t3"]}

    groups = [
        {"tabs": ["artist:bowie", "artist:queen", "artist:deleted", "folder:rock"]},
    ]
    tab_states = {
        "artist:bowie": {"title": "Old Bowie"},
        "artist:queen": {"title": "Queen"},
        "artist:deleted": {"title": "Deleted"},
    }

    effects = decide_artist_index_effects(
        previous_index=prev_index,
        new_index=new_index,
        pending_choice=("old_key", frozenset(["david bowie"])),
        groups=groups,
        tab_states=tab_states,
        is_plugin_artist=lambda k: False,
    )

    assert effects.opened_artist == ("bowie", "David Bowie")
    assert effects.stale_tabs == [(0, "artist:deleted")]
    assert effects.retitled_tabs == [("artist:bowie", "David Bowie")]
    # bowie tracks changed (['t1'] -> ['t1', 't2']), queen unchanged
    assert effects.reloaded_tab_ids == ["artist:bowie"]

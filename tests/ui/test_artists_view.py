"""The core Artists view: sidebar, artist page, its credit actions and what they open (plan 112).

One runtime serves the module. The read-only checks come first; the two credit actions come
last and each uses an artist that no earlier test changes.
"""

from __future__ import annotations

import pytest
from tests.ui.artists_support import (
    active_tab,
    artist_tabs,
    ready,
    seed,
    start,
    stop,
    text,
    wait_until,
)
from tests.ui.test_player_views import _find


@pytest.fixture(scope="module")
def view(qapp, tmp_path_factory, _module_monkeypatch):
    data_dir, tracks = seed(tmp_path_factory.mktemp("artists"))
    runtime = start(qapp, _module_monkeypatch, data_dir)
    workspace, root = ready(runtime)
    yield workspace, root, tracks
    stop(runtime)


@pytest.fixture(scope="module")
def _module_monkeypatch():
    with pytest.MonkeyPatch.context() as patch:
        yield patch


def test_the_artists_activity_lists_every_artist_with_its_track_count(view) -> None:
    workspace, root, _tracks = view
    workspace.setActivity("artists")
    assert workspace.activity == "artists"
    assert wait_until(lambda: _find(root, "artistsPane") is not None)
    assert text(root, "artistCount") == "3 artists"
    assert _find(root, "artistRow_chase") is not None

    workspace.artistList.setFilterText("cam")
    assert wait_until(lambda: text(root, "artistCount") == "1 of 3 artists")
    assert _find(root, "artistRow_camo & krooked") is not None
    assert _find(root, "artistRow_chase") is None

    workspace.artistList.setFilterText("")
    assert wait_until(lambda: text(root, "artistCount") == "3 artists")


def test_the_artist_page_shows_its_cover_header_and_tracks_in_album_order(view) -> None:
    workspace, root, tracks = view
    workspace.openArtistPage("chase", "")
    assert active_tab(workspace) == "artist:chase"
    assert wait_until(lambda: text(root, "artistTitleText") == "Chase")
    assert text(root, "artistKind") == "Artist"
    assert text(root, "artistTrackCount") == "3 tracks  ·  from “Chase & Status”"
    cover = _find(root, "artistCover")
    assert cover is not None
    # The cover is the artwork of the first track in album order, served by the provider.
    assert wait_until(lambda: str(cover.property("source")).startswith("image://artwork/"))

    model = workspace.trackModelForTab("artist:chase", "artist", "chase", "index", True)
    assert wait_until(lambda: model.count == 3)
    # Album, then track number: "Alpha" 1/9 and 3 before "Brand New" 2.
    assert model.trackIds == [tracks["four"], tracks["two"], tracks["one"]]


def test_the_menu_enables_only_the_credit_actions_that_apply(view) -> None:
    workspace, root, _tracks = view
    status = workspace.artistInfo("status")
    assert status["oneArtistCredits"] == ["Chase & Status"]
    assert status["splitCredits"] == []
    assert workspace.artistInfo("camo & krooked")["splitCredits"] == ["Camo & Krooked"]

    # The "…" menu is a Popup whose items exist once it opens, so the enabled flags are checked
    # on the facts they bind to; the header shows the same credit.
    workspace.openArtistPage("status", "")
    assert wait_until(lambda: text(root, "artistTrackCount") != "")
    assert text(root, "artistTrackCount") == "1 track  ·  from “Chase & Status”"
    assert _find(root, "artistMoreButton") is not None

    # Chase was cut from "Chase & Status", so "This is one artist" applies; it is no separator
    # itself, so "Split" does not.
    workspace.openArtistPage("chase", "")
    assert wait_until(lambda: text(root, "artistTitleText") == "Chase")
    chase = workspace.artistInfo("chase")
    assert chase["oneArtistCredits"] == ["Chase & Status"] and chase["splitCredits"] == []


def test_play_and_shuffle_play_the_artist_in_album_order(view) -> None:
    workspace, _root, tracks = view
    workspace.openArtistPage("chase", "")
    model = workspace.trackModelForTab("artist:chase", "artist", "chase", "index", True)
    assert wait_until(lambda: model.count == 3)

    workspace.playArtistRows("chase", model.rows, False)
    assert workspace.playingId == tracks["four"]
    assert workspace._player.playing_source_value() == "artist:chase"

    workspace.playArtistRows("chase", model.rows, True)
    assert workspace.playingId in {tracks["four"], tracks["two"], tracks["one"]}
    assert workspace._player.playing_source_value() == "artist:chase"


def test_this_is_one_artist_opens_the_artist_it_produces(view) -> None:
    workspace, root, _tracks = view
    workspace.openArtistPage("status", "")
    assert active_tab(workspace) == "artist:status"

    workspace.makeArtistOneArtist("status")
    # "Status" disappears: the page of "Chase & Status", which it was cut from, opens.
    assert wait_until(lambda: active_tab(workspace) == "artist:chase & status")
    assert workspace.artistInfo("status")["name"] == ""
    assert "artist:status" not in artist_tabs(workspace)
    assert wait_until(lambda: text(root, "artistTitleText") == "Chase & Status")
    assert "Kept" in workspace.message
    # "Chase" still exists with its own two tracks; the track of "Chase & Status" left it.
    assert workspace.artistInfo("chase")["trackCount"] == 2


def test_split_opens_the_first_artist_of_the_result_and_keeps_the_others_in_the_list(view) -> None:
    workspace, root, _tracks = view
    workspace.openArtistPage("camo & krooked", "")
    assert wait_until(lambda: text(root, "artistTitleText") == "Camo & Krooked")

    workspace.splitArtist("camo & krooked")
    # "Camo & Krooked" disappears; "Camo" and "Krooked" come back and Camo is opened first.
    assert wait_until(lambda: active_tab(workspace) == "artist:camo")
    assert "artist:camo & krooked" not in artist_tabs(workspace)
    assert workspace.artistInfo("krooked")["trackCount"] == 1
    assert wait_until(lambda: text(root, "artistTitleText") == "Camo")
    workspace.setActivity("artists")
    assert wait_until(lambda: _find(root, "artistRow_krooked") is not None)

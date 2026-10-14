"""The plan 112 mock-up model runs the real artist rules on synthetic tags."""

from __future__ import annotations

from mtee.prototypes.artists_112 import ArtistsReviewPrototype


def _keys(prototype: ArtistsReviewPrototype) -> set[str]:
    return {row["key"] for row in prototype.artists}


def test_the_default_list_cuts_only_the_credits_the_rules_allow(qapp) -> None:
    prototype = ArtistsReviewPrototype()
    keys = _keys(prototype)
    # "Chase" is solo, so "Chase & Status" is cut; "Camo & Krooked" has no solo side.
    assert {"chase", "status", "camo & krooked", "burial", "thom yorke"} <= keys
    assert "chase & status" not in keys
    assert "skream" in keys and "remix" not in keys  # a remixer in a title is not credited


def test_one_artist_then_reset_restores_the_cut(qapp) -> None:
    prototype = ArtistsReviewPrototype()
    prototype.selectArtist("status")
    assert prototype.canMakeOneArtist and not prototype.canSplit
    assert prototype.oneArtistCredits == ["Chase & Status"]

    prototype.makeOneArtist()
    assert "status" not in _keys(prototype) and "chase & status" in _keys(prototype)
    assert prototype.artistKey == ""  # the page of a vanished artist closes
    assert len(prototype.choices) == 1

    prototype.resetChoices()
    assert "status" in _keys(prototype) and prototype.choices == []


def test_split_cuts_a_kept_name_and_search_filters_the_list(qapp) -> None:
    prototype = ArtistsReviewPrototype()
    prototype.selectArtist("camo & krooked")
    assert prototype.canSplit and not prototype.canMakeOneArtist
    prototype.splitArtist()
    assert {"camo", "krooked"} <= _keys(prototype)
    assert "camo & krooked" not in _keys(prototype)

    prototype.setSearch("  KROO ")
    assert _keys(prototype) == {"krooked"}
    prototype.setSearch("")
    assert len(prototype.artists) == prototype.totalCount


def test_the_artist_page_lists_each_track_once_sorted_by_title(qapp) -> None:
    prototype = ArtistsReviewPrototype("selected")
    titles = [row["title"] for row in prototype.tracks]
    assert titles == sorted(titles, key=str.casefold)
    assert len(titles) == prototype.trackCount == len(set(titles))


def test_play_and_shuffle_only_report(qapp) -> None:
    prototype = ArtistsReviewPrototype("selected")
    prototype.play()
    assert "not connected" in prototype.message
    prototype.shuffle()
    assert "not connected" in prototype.message

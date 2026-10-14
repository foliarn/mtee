"""Splitting rules and artist index of the core Artists view (step 112)."""

from __future__ import annotations

import time

import pytest

from mtee.domain.artist_index import (
    MODE_ONE_ARTIST,
    MODE_SPLIT,
    build_artist_index,
    has_separator,
    solo_artist_keys,
    split_artist_credit,
    split_credit_parts,
)
from mtee.domain.artists import normalize_key

SOLO = frozenset({"chase", "status", "sub focus", "wilkinson", "camo", "krooked", "sugah"})


def _split(text: str, **kwargs: object) -> list[str]:
    return split_artist_credit(text, **kwargs)  # type: ignore[arg-type]


# ----------------------------------------------------------------- commas and feat./ft.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bou, Hedex", ["Bou", "Hedex"]),
        ("Nikita, the Wicked, Hedex", ["Nikita", "the Wicked", "Hedex"]),
        ("Bou,Hedex", ["Bou", "Hedex"]),
        ("Artist feat. Other", ["Artist", "Other"]),
        ("Artist feat Other", ["Artist", "Other"]),
        ("Artist FEAT. Other", ["Artist", "Other"]),
        ("Artist ft. Other", ["Artist", "Other"]),
        ("Artist Ft Other", ["Artist", "Other"]),
        ("Artist ft.Other", ["Artist", "Other"]),
        ("Artist, feat. Other, ft Third", ["Artist", "Other", "Third"]),
    ],
)
def test_commas_and_feat_or_ft_always_split(text: str, expected: list[str]) -> None:
    assert _split(text) == expected


@pytest.mark.parametrize(
    "text",
    ["Left Hand", "Rift Lab", "Featherweight", "Lift", "Softer Sound", "Loft Party"],
)
def test_feat_and_ft_are_whole_words_only(text: str) -> None:
    assert _split(text) == [text]


def test_empty_names_between_separators_are_dropped() -> None:
    assert _split(" , Bou ,, Hedex, ") == ["Bou", "Hedex"]
    assert _split("   ") == []
    assert _split("") == []


# ----------------------------------------------------------------- ampersand and x


def test_ampersand_stays_one_artist_without_a_solo_side() -> None:
    assert _split("Chase & Status") == ["Chase & Status"]
    assert _split("Camo & Krooked") == ["Camo & Krooked"]
    assert _split("T & Sugah") == ["T & Sugah"]


def test_ampersand_splits_when_one_side_is_solo() -> None:
    assert _split("Chase & Status", solo=frozenset({"chase"})) == ["Chase", "Status"]
    assert _split("Chase & Status", solo=frozenset({"status"})) == ["Chase", "Status"]


def test_ampersand_splits_when_both_sides_are_solo() -> None:
    assert _split("Sub Focus & Wilkinson", solo=SOLO) == ["Sub Focus", "Wilkinson"]


def test_ampersand_stays_whole_when_no_side_is_solo() -> None:
    assert _split("Sub Focus & Wilkinson", solo=frozenset({"camo"})) == ["Sub Focus & Wilkinson"]


def test_x_junction_follows_the_same_rule_in_either_case() -> None:
    assert _split("Ajax x Foo", solo=frozenset({"foo"})) == ["Ajax", "Foo"]
    assert _split("Ajax X Foo", solo=frozenset({"foo"})) == ["Ajax", "Foo"]
    assert _split("Ajax x Foo") == ["Ajax x Foo"]


@pytest.mark.parametrize("text", ["Chase&Status", "Xavier", "Hex-x-Lab", "Mixtape"])
def test_junction_needs_a_space_on_each_side(text: str) -> None:
    assert _split(text, solo=SOLO) == [text]


def test_three_names_decide_each_junction_on_its_own() -> None:
    # Chase is solo: the first junction cuts. Status and Sub Focus are not joined by a solo
    # name in the first place, so their junction stays merged.
    assert _split("Chase & Status & Camo", solo=frozenset({"chase"})) == [
        "Chase",
        "Status & Camo",
    ]
    # Both sides of the second junction are a name cut so far: Sub Focus is solo.
    assert _split("Chase & Status & Sub Focus", solo=frozenset({"sub focus"})) == [
        "Chase & Status",
        "Sub Focus",
    ]
    assert _split("Sub Focus & Wilkinson & Camo", solo=SOLO) == [
        "Sub Focus",
        "Wilkinson",
        "Camo",
    ]


def test_commas_and_junctions_combine() -> None:
    assert _split(
        "Bou, Sub Focus & Wilkinson, Camo & Krooked",
        solo=frozenset({"sub focus", "wilkinson"}),
    ) == ["Bou", "Sub Focus", "Wilkinson", "Camo & Krooked"]


# ----------------------------------------------------------------- overrides


def test_one_artist_override_keeps_the_credit_whole_even_with_solo_names() -> None:
    assert _split("Sub Focus & Wilkinson", solo=SOLO, one_names=["Sub Focus & Wilkinson"]) == [
        "Sub Focus & Wilkinson"
    ]


def test_one_artist_override_protects_a_comma_name_inside_a_longer_credit() -> None:
    assert _split("Bou, Nikita, the Wicked", one_names=["Nikita, the Wicked"]) == [
        "Bou",
        "Nikita, the Wicked",
    ]
    assert _split("Nikita, the Wicked, Hedex", one_names=["Nikita, the Wicked"]) == [
        "Nikita, the Wicked",
        "Hedex",
    ]


def test_one_artist_override_matches_case_and_spacing() -> None:
    assert _split("  chase  &   STATUS ", one_names=["Chase & Status"], solo=SOLO) == [
        "chase & STATUS"
    ]


def test_one_artist_override_does_not_match_inside_another_name() -> None:
    assert _split("Bou & Hedex Plus", one_names=["Hedex"], solo=SOLO) == ["Bou & Hedex Plus"]


def test_longest_one_artist_name_wins() -> None:
    assert _split(
        "Nikita, the Wicked, Hedex",
        one_names=["Nikita", "Nikita, the Wicked"],
    ) == ["Nikita, the Wicked", "Hedex"]


def test_split_override_cuts_every_junction_of_its_credit() -> None:
    keys = frozenset({normalize_key("Chase & Status")})
    assert _split("Chase & Status", split_keys=keys) == ["Chase", "Status"]
    assert _split("Foo, Chase & Status", split_keys=keys) == ["Foo", "Chase", "Status"]


def test_split_override_on_a_whole_tag_cuts_all_its_junctions() -> None:
    keys = frozenset({normalize_key("Foo, Chase & Status")})
    assert _split("Foo, Chase & Status", split_keys=keys) == ["Foo", "Chase", "Status"]


def test_split_override_keeps_the_origin_segment() -> None:
    keys = frozenset({normalize_key("Chase & Status")})
    parts = split_credit_parts("Foo, Chase & Status", split_keys=keys)
    assert [(part.name, part.origin) for part in parts] == [
        ("Foo", "Foo"),
        ("Chase", "Chase & Status"),
        ("Status", "Chase & Status"),
    ]


# ----------------------------------------------------------------- remixers and detection


def test_remixer_in_the_title_is_never_credited() -> None:
    index = build_artist_index(
        [("t1", ["Benga"])],
        {},
    )
    assert [artist.name for artist in index.artists] == ["Benga"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bou, Hedex", True),
        ("Bou & Hedex", True),
        ("Ajax x Foo", True),
        ("feat. Other", True),
        ("Chase&Status", False),
        ("Bou", False),
        ("Left Hand", False),
    ],
)
def test_has_separator(text: str, expected: bool) -> None:
    assert has_separator(text) is expected


# ----------------------------------------------------------------- solo names


def test_solo_names_come_from_single_artist_tags_only() -> None:
    solo = solo_artist_keys(
        [
            ["Chase"],
            ["Chase & Status"],
            ["Bou", "Hedex"],
            ["Camo, Krooked"],
            ["  Sub   Focus  "],
            ["Chase,"],
        ]
    )
    assert solo == frozenset({"chase", "sub focus"})


def test_solo_key_is_whitespace_and_case_insensitive() -> None:
    assert solo_artist_keys([["  CHASE  "]]) == frozenset({"chase"})
    assert _split("chase & status", solo=solo_artist_keys([["Chase"]])) == [
        "chase",
        "status",
    ]


# ----------------------------------------------------------------- index


def _tracks() -> list[tuple[str, list[str]]]:
    return [
        ("t1", ["Chase"]),
        ("t2", ["Chase & Status"]),
        ("t3", ["Sub Focus"]),
        ("t4", ["Sub Focus & Wilkinson"]),
        ("t5", ["Wilkinson"]),
        ("t6", ["Camo & Krooked"]),
        ("t7", ["chase  &  status"]),
        ("t8", ["Bou, Hedex"]),
        ("t9", []),
    ]


def test_index_splits_by_solo_names_and_counts_each_track_once() -> None:
    index = build_artist_index(_tracks(), {})
    names = {artist.key: artist.name for artist in index.artists}
    assert names == {
        "chase": "Chase",
        "status": "Status",
        "sub focus": "Sub Focus",
        "wilkinson": "Wilkinson",
        "camo & krooked": "Camo & Krooked",
        "bou": "Bou",
        "hedex": "Hedex",
    }
    counts = {artist.key: artist.track_count for artist in index.artists}
    # Chase is solo on t1, and cut from the credits of t2 and t7 (case and spacing ignored).
    assert counts["chase"] == 3
    assert counts["status"] == 2
    assert counts["sub focus"] == 2
    assert index.tracks_by_artist["sub focus"] == ("t3", "t4")
    assert "t9" not in index.artists_by_track
    assert index.artists_by_track["t2"] == (normalize_key("Chase"), normalize_key("Status"))


def test_index_is_sorted_case_insensitively_by_name() -> None:
    index = build_artist_index(_tracks(), {})
    names = [artist.name for artist in index.artists]
    assert names == sorted(names, key=str.casefold)


def test_index_keeps_origins_for_the_override_actions() -> None:
    index = build_artist_index(_tracks(), {})
    chase = index.entry("chase")
    status = index.entry("status")
    assert chase is not None and status is not None
    assert "Chase & Status" in status.origins
    assert "Chase & Status" in chase.origins
    assert "Chase" in chase.origins
    camo = index.entry("camo & krooked")
    assert camo is not None and camo.origins == ("Camo & Krooked",)


def test_index_applies_stored_overrides() -> None:
    overrides = {
        normalize_key("Chase & Status"): ("Chase & Status", MODE_ONE_ARTIST),
        normalize_key("Camo & Krooked"): ("Camo & Krooked", MODE_SPLIT),
    }
    index = build_artist_index(_tracks(), overrides)
    keys = {artist.key for artist in index.artists}
    assert "chase & status" in keys
    # Chase is solo on t1, but the one-artist credit of t2 and t7 is not cut.
    assert "chase" in keys and "status" not in keys
    assert {"camo", "krooked"} <= keys and "camo & krooked" not in keys


def test_index_is_stable_for_the_same_input() -> None:
    first = build_artist_index(_tracks(), {})
    second = build_artist_index(list(reversed(_tracks())), {})
    assert [artist.key for artist in first.artists] == [artist.key for artist in second.artists]


def test_index_builds_three_thousand_tracks_quickly() -> None:
    tracks = []
    for number in range(3_000):
        style = number % 6
        if style == 0:
            values = [f"Artist {number % 400}"]
        elif style == 1:
            values = [f"Artist {number % 400} & Guest {number % 97}"]
        elif style == 2:
            values = [f"Artist {number % 400}, Guest {number % 53} feat. Friend {number % 11}"]
        elif style == 3:
            values = [f"Solo {number % 250}"]
        elif style == 4:
            values = [f"Solo {number % 250} x Other {number % 31}"]
        else:
            values = ["Chase & Status", f"Artist {number % 400}"]
        tracks.append((f"track-{number}", values))
    started = time.perf_counter()
    index = build_artist_index(tracks, {})
    elapsed = time.perf_counter() - started
    assert index.artists
    # A generous bound: the measured cost on the development machine is far below it.
    assert elapsed < 2.0

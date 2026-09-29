from __future__ import annotations

import pytest

from mtee.domain.musical_key import MusicalKey, format_key, parse_key

# Camelot wheel as published: number and letter for each major key, then its relative minor.
_MAJOR_WHEEL = {
    "C": "8B",
    "G": "9B",
    "D": "10B",
    "A": "11B",
    "E": "12B",
    "B": "1B",
    "F#": "2B",
    "C#": "3B",
    "G#": "4B",
    "D#": "5B",
    "A#": "6B",
    "F": "7B",
}
_MINOR_WHEEL = {
    "Am": "8A",
    "Em": "9A",
    "Bm": "10A",
    "F#m": "11A",
    "C#m": "12A",
    "G#m": "1A",
    "D#m": "2A",
    "A#m": "3A",
    "Fm": "4A",
    "Cm": "5A",
    "Gm": "6A",
    "Dm": "7A",
}


@pytest.mark.parametrize(("classic", "camelot"), [*_MAJOR_WHEEL.items(), *_MINOR_WHEEL.items()])
def test_every_key_maps_to_its_published_camelot_code(classic: str, camelot: str) -> None:
    key = parse_key(classic)
    assert key is not None
    assert key.camelot == camelot
    assert key.classic == classic
    assert parse_key(camelot) == key


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bb", "A#"),
        ("Ebm", "D#m"),
        ("Db major", "C#"),
        ("A minor", "Am"),
        ("a", "A"),
        ("Gbm", "F#m"),
        ("♯C", None),
        ("F♯m", "F#m"),
        ("B♭", "A#"),
        ("  8a ", "Am"),
        ("08B", "C"),
    ],
)
def test_flats_words_and_spacing_are_understood(text: str, expected: str | None) -> None:
    key = parse_key(text)
    assert (key.classic if key else None) == expected


@pytest.mark.parametrize("text", ["", "xyz", "13A", "0A", "H", "Am7", "8C"])
def test_text_that_is_not_a_key_is_rejected(text: str) -> None:
    assert parse_key(text) is None


def test_formatting_follows_the_notation_and_keeps_unknown_text() -> None:
    assert format_key("Am", "camelot") == "8A"
    assert format_key("8A", "classic") == "Am"
    assert format_key("F#m", "camelot") == "11A"
    assert format_key("", "camelot") == ""
    assert format_key("Some label", "classic") == "Some label"


def test_key_rejects_an_invalid_tonic() -> None:
    with pytest.raises(ValueError):
        MusicalKey(12, False)

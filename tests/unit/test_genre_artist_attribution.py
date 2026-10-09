"""Conservative artist attribution refuses ambiguous versions."""

from mtee.plugins.genre_manager.artist_attribution import choose_artists

MADONNA = {"id": "madonna", "name": "Madonna", "role": "artist"}
REMIXER = {"id": "remixer", "name": "Club Producer", "role": "remixer"}


def test_confirmed_remixer_receives_genre_without_original_artist() -> None:
    assert choose_artists("Song (Club Producer Remix)", [MADONNA, REMIXER]) == (["remixer"], "")
    assert choose_artists("Song (Club Producer Flip)", [MADONNA, REMIXER]) == (["remixer"], "")
    assert choose_artists("Song (Club Producer Bootleg)", [MADONNA, REMIXER]) == (["remixer"], "")


def test_original_requires_positive_original_version_signal() -> None:
    assert choose_artists("Song (Original Mix)", [MADONNA]) == (["madonna"], "")
    assert choose_artists("Song", [MADONNA])[0] == []


def test_missing_or_contradictory_remixer_abstains() -> None:
    assert choose_artists("Song (Unknown Remix)", [MADONNA, REMIXER])[0] == []
    assert choose_artists("Song (Madonna Remix)", [MADONNA, REMIXER])[0] == []
    assert choose_artists("Song (Remix)", [MADONNA])[0] == []
    assert choose_artists("Song", [MADONNA, REMIXER]) == (["remixer"], "")


def test_manual_choice_must_be_from_existing_credits() -> None:
    assert choose_artists("Song", [MADONNA, REMIXER], ["remixer"]) == (["remixer"], "")
    assert choose_artists("Song", [MADONNA], ["stranger"])[0] == []

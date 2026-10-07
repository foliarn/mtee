"""A credit written from the tag editor reaches the artists database and keeps it tidy."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from mtee.domain.artists import split_credit
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tag_values import normalize_date, validate_field
from mtee.domain.tracks import SourceRevision
from mtee.persistence.artist_repository import ArtistRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artist_identification_service import ArtistIdentificationService


class _Setup:
    def __init__(self, base: Path) -> None:
        self.music = base / "music"
        self.music.mkdir(parents=True)
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = self.library.add_root(self.music)["id"]
        self.repository = ArtistRepository(self.database)
        self.service = ArtistIdentificationService(self.library, self.repository)

    def add_track(self, name: str) -> str:
        path = self.music / name
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 800)
        generation = self.library.begin_scan(self.root_id)
        self.library.upsert_locations(
            self.root_id,
            [
                (
                    name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(title=(path.stem,), technical=TechnicalInfo(duration_us=100)),
                )
            ],
            generation,
        )
        owner = self.library.path_owner(path)
        assert owner is not None
        return owner

    def catalog(self) -> dict[str, int]:
        return {item["name"]: item["tracks"] for item in self.repository.catalog()}


@pytest.fixture
def setup(tmp_path: Path):
    value = _Setup(tmp_path)
    yield value
    value.database.close()


def test_a_new_credit_creates_the_artists_and_confirms_the_track(setup: _Setup) -> None:
    track = setup.add_track("a.wav")
    setup.service.sync_tags(track, ["Hedex", "Bou"], "Title")
    assert setup.catalog() == {"Bou": 1, "Hedex": 1}
    assert setup.repository.confirmed_state(track)["credits"][0]["name"] == "Hedex"


def test_a_track_leaves_the_artist_it_no_longer_names(setup: _Setup) -> None:
    first = setup.add_track("a.wav")
    second = setup.add_track("b.wav")
    setup.service.sync_tags(first, ["Hedex", "Bou"], None)
    setup.service.sync_tags(second, ["Hedex"], None)
    setup.service.sync_tags(first, ["Bou"], None)
    assert setup.catalog() == {"Bou": 1, "Hedex": 1}  # Hedex keeps the second track


def test_an_artist_left_without_any_track_is_removed(setup: _Setup) -> None:
    track = setup.add_track("a.wav")
    setup.service.sync_tags(track, ["Hedex", "Bou"], None)
    setup.service.sync_tags(track, ["Bou"], None)
    assert setup.catalog() == {"Bou": 1}
    assert [item["name"] for item in setup.repository.artist_names("")] == ["Bou"]
    setup.service.sync_tags(track, [], None)  # the artist tag was removed
    assert setup.catalog() == {}
    assert setup.repository.artist_names("") == []


def test_a_name_with_a_comma_becomes_protected(setup: _Setup) -> None:
    track = setup.add_track("a.wav")
    assert split_credit("Nikita, the Wicked") == ["Nikita", "the Wicked"]
    setup.service.sync_tags(track, ["Nikita, the Wicked"], None)
    protected = setup.service.protected_names()
    assert protected == ["Nikita, the Wicked"]
    assert split_credit("Nikita, the Wicked, Hedex", protected) == [
        "Nikita, the Wicked",
        "Hedex",
    ]


def test_dates_are_normalized_or_refused() -> None:
    assert normalize_date("2024") == ("2024", "")
    assert normalize_date("2024/3/5") == ("2024-03-05", "")
    assert normalize_date("5.3.2024") == ("2024-03-05", "")
    assert normalize_date("2024-03") == ("2024-03", "")
    assert normalize_date("2024-02-31")[1] != ""
    assert normalize_date("5/3/2024")[1] != ""
    assert normalize_date("March")[1] != ""


def test_other_fields_are_validated() -> None:
    assert validate_field("bpm", "174")[1] == ""
    assert validate_field("bpm", "87,5") == ("87.5", "")
    assert validate_field("bpm", "fast")[1] != ""
    assert validate_field("key", "8A", "classic") == ("Am", "")
    assert validate_field("key", "H#")[1] != ""
    assert validate_field("track_number", "3/12") == ("3/12", "")
    assert validate_field("track_number", "three")[1] != ""
    assert validate_field("title", "  Anything  ") == ("Anything", "")
    assert validate_field("date", "") == ("", "")

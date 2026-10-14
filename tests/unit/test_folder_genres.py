"""Genres from folders: names, remixers, tags added without touching the user's."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.plugins.artist_manager.folder_genre_service import FolderGenreService
from mtee.plugins.artist_manager.folder_genres import (
    Credit,
    folder_genres,
    format_genre,
    marker_names,
    track_targets,
)
from mtee.plugins.artist_manager.identification import ArtistIdentificationService
from mtee.plugins.artist_manager.repository import ArtistRepository


def test_folder_names_get_capitals() -> None:
    assert format_genre("hard techno") == "Hard Techno"
    assert format_genre("d&b") == "Drum & Bass"
    assert format_genre("ukg - speed garage & bangers") == "UKG - Speed Garage & Bangers"
    assert format_genre("chill&atmospheric") == "Chill&Atmospheric"
    assert format_genre("old school (classique, jazz, rock, 80s...)") == (
        "Old School (Classique, Jazz, Rock, 80s...)"
    )
    assert format_genre("dance (electronica - kaytra - french touch)").startswith(
        "Dance (Electronica"
    )


def test_the_top_folder_and_its_sub_folder_give_the_genres() -> None:
    assert folder_genres("hard techno/a.mp3") == ["Hard Techno"]
    assert folder_genres("d&b/jump up/a.mp3") == ["Drum & Bass", "Jump Up"]
    assert folder_genres("d&b\\jump up\\a.mp3") == ["Drum & Bass", "Jump Up"]
    assert folder_genres("a.mp3") == []
    assert folder_genres("zzZ/a.mp3") == []
    assert folder_genres("Artists/Skrillex/a.mp3") == []
    assert folder_genres("dj blc/a.mp3") == []
    assert folder_genres("house/a.mp3", ignored=["house"]) == []


@pytest.mark.parametrize(
    ("title", "names"),
    [
        ("low down (Pola & Bryson Remix)", ["Pola & Bryson"]),
        ("Get Shaky (Macon's HYPERTECHNO Remix) (Extended Mix)", ["Macon's HYPERTECHNO"]),
        ("Song (CODE PANDORUM x CASTER REMIX)", ["CODE PANDORUM x CASTER"]),
        ("Song (Gemi Edit)", ["Gemi"]),
        ("Song (BGZ EXTENDED REWORK)", ["BGZ"]),
        ("Song (CRANKDAT REMIX 2)", ["CRANKDAT"]),
        ("Song [Dyoll's Hardgroove Bootleg]", ["Dyoll's Hardgroove"]),
        ("Song (DISRUPTA EDIT VIP)", ["DISRUPTA"]),
        ("Song (Blanke's ÆON-REMIX)", ["Blanke's ÆON"]),
        ("Song (VIP)", []),
        ("Song (Extended Mix)", []),
        ("Song (Jungle VIP)", []),
        ("Song (DJ Edit)", []),
        ("Song (Drum and Bass Remix)", []),
    ],
)
def test_markers_name_the_remixer_or_nobody(title: str, names: list[str]) -> None:
    assert marker_names(title) == names


def test_a_remix_gives_its_genre_to_the_remixer_only() -> None:
    credits = [Credit("a", "venbee"), Credit("b", "Dan Fable"), Credit("c", "Pola & Bryson")]
    assert track_targets(credits, ["low down (Pola & Bryson Remix)"]).artist_ids == ["c"]
    assert track_targets(credits, ["low down (VIP)"]).artist_ids == ["a", "b", "c"]
    unresolved = track_targets(credits, ["low down (Someone Else Remix)"])
    assert (unresolved.status, unresolved.artist_ids) == ("unresolved", [])
    pair = [
        Credit("a", "BRING ME THE HORIZON"),
        Credit("b", "Code:Pandorum"),
        Credit("c", "CASTER"),
    ]
    assert track_targets(pair, ["X (CODE PANDORUM x CASTER REMIX)"]).artist_ids == ["b", "c"]
    country = [Credit("a", "Sox"), Credit("b", "Jaybee (UK)")]
    assert track_targets(country, ["Brum (Jaybee Remix)"]).artist_ids == ["b"]
    marked = [Credit("a", "X"), Credit("r", "R", "remixer")]
    assert track_targets(marked, ["whatever"]).artist_ids == ["r"]


def test_the_marker_found_in_another_title_still_counts() -> None:
    credits = [Credit("a", "Orig"), Credit("b", "Remixer")]
    targets = track_targets(credits, ["Song", "Orig - Song (Remixer Remix)"])
    assert (targets.status, targets.artist_ids) == ("remix", ["b"])


class _Library:
    def __init__(self, base: Path) -> None:
        self.music = base / "foliarn"
        self.music.mkdir(parents=True)
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = self.library.add_root(self.music)["id"]
        self.repository = ArtistRepository(self.database)
        self.identification = ArtistIdentificationService(self.library, self.repository)
        self.service = FolderGenreService(self.database, self.repository)

    def add(self, relative: str, artists: list[str], title: str | None = None) -> None:
        path = self.music / relative
        path.parent.mkdir(parents=True, exist_ok=True)
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
                    relative,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(title=(path.stem,), technical=TechnicalInfo(duration_us=100)),
                )
            ],
            generation,
        )
        owner = self.library.path_owner(path)
        assert owner is not None
        self.identification.sync_tags(owner, artists, title)

    def artist(self, name: str) -> str:
        return next(item["id"] for item in self.repository.catalog() if item["name"] == name)

    def tags(self, name: str) -> list[str]:
        return list(self.repository.artist_profile(self.artist(name)).tags)


@pytest.fixture
def library(tmp_path: Path):
    value = _Library(tmp_path)
    value.add("hard techno/a.wav", ["Alpha", "Beta"])
    value.add("d&b/jump up/b.wav", ["Alpha"])
    value.add("d&b/c.wav", ["Orig", "Remixer"], "Song (Remixer Remix)")
    value.add("zzZ/d.wav", ["Hidden"])
    value.add("house/e.wav", ["Orig"], "Other (Nobody Edit)")
    yield value
    value.database.close()


def test_the_plan_reads_the_folders_and_applies_the_remix_rule(library: _Library) -> None:
    plan = library.service.plan("foliarn")
    assert plan.tracks == 5
    assert plan.ignored_folders == {"zzZ": 1}
    assert dict(plan.artist_genres[library.artist("Alpha")]) == {
        "Hard Techno": 1,
        "Drum & Bass": 1,
        "Jump Up": 1,
    }
    assert dict(plan.artist_genres[library.artist("Remixer")]) == {"Drum & Bass": 1}
    assert library.artist("Orig") not in plan.artist_genres  # original of a remix, edit unresolved
    assert [item["names"] for item in plan.unresolved] == [["Nobody"]]
    assert library.tags("Alpha") == []  # planning writes nothing


def test_apply_adds_the_tags_and_keeps_the_user_s(library: _Library) -> None:
    alpha = library.artist("Alpha")
    library.repository.save_artist_profile(
        alpha, roles=["DJ"], bass_related=True, tags=["mine", "Jump Up"], hidden=True
    )
    library.service.apply(library.service.plan("foliarn"))
    profile = library.repository.artist_profile(alpha)
    assert profile.tags[:2] == ["mine", "Jump Up"]
    assert set(profile.tags) == {"mine", "Jump Up", "Hard Techno", "Drum & Bass"}
    assert (profile.roles, profile.bass_related, profile.hidden) == (["DJ"], True, True)
    row = (
        library.database.connection()
        .execute(
            "SELECT record_json, tags_json FROM artist_enrichment_reviews WHERE artist_id=?",
            (alpha,),
        )
        .fetchone()
    )
    assert json.loads(row["tags_json"])[0] == "idgaf"
    record = json.loads(row["record_json"])
    assert record["genre_sources"] == {"Drum & Bass": 1, "Hard Techno": 1, "Jump Up": 1}
    assert record["genre_added"] == ["Drum & Bass", "Hard Techno"]  # "Jump Up" was typed
    assert library.tags("Remixer") == ["Drum & Bass"]
    assert library.tags("Orig") == []


def test_a_new_run_replaces_the_earlier_genres_only(library: _Library) -> None:
    library.service.apply(library.service.plan("foliarn"))
    alpha = library.artist("Alpha")
    library.repository.save_artist_profile(
        alpha,
        roles=[],
        bass_related=None,
        tags=[*library.tags("Alpha"), "typed after"],
        hidden=False,
    )
    # The track of hard techno moves away: that genre must go, the typed tag stays.
    library.database.connection().execute(
        "UPDATE root_tracks SET present=0 WHERE relative_path='hard techno/a.wav'"
    )
    library.database.connection().commit()
    outcome = library.service.apply(library.service.plan("foliarn"))
    assert "Hard Techno" not in library.tags("Alpha")
    assert "typed after" in library.tags("Alpha")
    assert outcome["tagged"] >= 1
    # Beta only had the removed track: its earlier genre is cleared.
    assert library.tags("Beta") == []

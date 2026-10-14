"""Core artist index, credit overrides and the Artists view models (step 112).

The library is a real SQLite file with small WAV files, read through the same repositories
the application uses. The index is built by a background job, so each test waits for the
``indexChanged`` signal that the graphical thread receives.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.artist_index_model import ArtistListModel, ArtistPageModel
from mtee.persistence.credit_override_repository import CreditOverrideRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artist_index_service import ArtistIndexService
from mtee.services.jobs import JobService

TRACKS = {
    "chase.wav": "Chase",
    "chase-status.wav": "Chase & Status",
    "sub-focus.wav": "Sub Focus",
    "sub-focus-wilkinson.wav": "Sub Focus & Wilkinson",
    "wilkinson.wav": "Wilkinson",
    "camo-krooked.wav": "Camo & Krooked",
    "bou-hedex.wav": "Bou, Hedex",
    "remix.wav": "Benga",
    "chase-status-again.wav": "chase  &  STATUS",
}


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes(b"\x00\x00" * 8)


@pytest.fixture
def library_setup(tmp_path: Path):
    music = tmp_path / "music"
    music.mkdir()
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(music)
    generation = library.begin_scan(root["id"])
    entries = []
    for name, artist in TRACKS.items():
        path = music / name
        _write_wav(path)
        metadata = MetadataSnapshot(
            title=(path.stem,),
            artist=(artist,),
            technical=TechnicalInfo(duration_us=1_000_000),
        )
        entries.append((name, path, SourceRevision.observe(path), metadata))
    library.upsert_locations(root["id"], entries, generation)
    library.finish_scan(root["id"], generation, complete=True)
    yield database, library, music
    database.close()


def _service(qapp, database: Database, library: LibraryRepository):
    jobs = JobService(qapp, max_thread_count=1)
    service = ArtistIndexService(library, CreditOverrideRepository(database), jobs)
    return jobs, service


def _settle(qapp, service: ArtistIndexService, refresh=True) -> None:
    """Refresh (unless told not to) and wait until the new index reaches the graphical thread."""
    changes: list[int] = []
    service.indexChanged.connect(lambda: changes.append(1))
    if refresh:
        service.refresh()
    deadline = time.monotonic() + 10
    while not changes and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        QTest.qWait(5)
    assert changes, service.last_error


def _names(service: ArtistIndexService) -> dict[str, str]:
    return {artist.key: artist.name for artist in service.artists()}


def test_the_index_follows_the_artist_tag_and_ignores_titles(qapp, library_setup) -> None:
    database, library, _music = library_setup
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    names = _names(service)
    # "chase  &  STATUS" is the same credit as "Chase & Status": case and spacing ignored.
    assert names["chase"] == "Chase"
    assert names["status"].casefold() == "status"
    assert names["sub focus"] == "Sub Focus"
    assert names["wilkinson"] == "Wilkinson"
    assert names["camo & krooked"] == "Camo & Krooked"
    assert names["bou"] == "Bou" and names["hedex"] == "Hedex"
    assert names["benga"] == "Benga"
    assert "skream" not in names  # the remixer in a title is never credited
    assert service.index.tracks_by_artist["chase"]  # Chase is solo on one track
    jobs.shutdown()


def test_one_artist_choice_keeps_the_credit_and_survives_a_restart(qapp, library_setup) -> None:
    database, library, _music = library_setup
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    assert "status" in _names(service)

    # Both spellings of the credit are one choice: they share one key.
    credits = service.one_artist_credits("status")
    assert len(credits) == 1 and credits[0].casefold() == "chase & status"
    assert service.make_one_artist("status") == 1
    _settle(qapp, service)
    names = _names(service)
    assert "status" not in names and "chase & status" in names

    reopened_jobs, reopened = _service(qapp, database, library)
    _settle(qapp, reopened)
    assert "chase & status" in _names(reopened)
    assert [item["mode"] for item in reopened.overrides()] == ["one_artist"]
    reopened_jobs.shutdown()
    jobs.shutdown()


def test_split_choice_cuts_a_name_that_was_kept_whole(qapp, library_setup) -> None:
    database, library, _music = library_setup
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    assert "camo & krooked" in _names(service)
    assert service.split_credits("camo & krooked") == ["Camo & Krooked"]
    assert service.split_credits("chase") == []  # a plain name has nothing to cut

    assert service.split_artist("camo & krooked") == 1
    _settle(qapp, service)
    names = _names(service)
    assert "camo" in names and "krooked" in names and "camo & krooked" not in names
    jobs.shutdown()


def test_removing_a_choice_restores_the_default_cut(qapp, library_setup) -> None:
    database, library, _music = library_setup
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    service.make_one_artist("status")
    _settle(qapp, service)
    key = service.overrides()[0]["key"]
    assert service.remove_override(key) is True
    _settle(qapp, service, refresh=False)
    assert "status" in _names(service)
    assert service.overrides() == []
    assert service.remove_override(key) is False
    jobs.shutdown()


def test_tag_editor_rules_use_the_index_and_the_overrides(qapp, library_setup) -> None:
    database, library, _music = library_setup
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    # Chase is solo, so the ampersand of a typed Chase & Status is cut.
    assert service.split("Chase & Status") == ["Chase", "Status"]
    # Camo and Krooked are never solo: their credit stays whole.
    assert service.split("Camo & Krooked") == ["Camo & Krooked"]
    assert service.needs_choice("Camo & Krooked") is True
    assert service.needs_choice("Camo") is False

    service.record_credit_choice("Camo & Krooked", one_artist=False)
    assert service.needs_choice("Camo & Krooked") is False
    assert service.split("Camo & Krooked") == ["Camo", "Krooked"]

    service.record_credit_choice("Bou, Hedex", one_artist=True)
    assert service.split("Nikita, Bou, Hedex") == ["Nikita", "Bou, Hedex"]
    assert service.split("Bou, Hedex") == ["Bou, Hedex"]

    _settle(qapp, service, refresh=False)
    assert [item["name"] for item in service.suggestions("hed")] == ["Bou, Hedex"]
    assert service.suggestions("   ") == []
    jobs.shutdown()


def test_overrides_are_stored_once_per_credit_whatever_the_spelling(library_setup) -> None:
    database, _library, _music = library_setup
    store = CreditOverrideRepository(database)
    store.set_mode("Bou,  Hedex", "one_artist")
    store.set_mode("bou, hedex", "split")
    rows = store.all()
    assert len(rows) == 1
    assert rows[0]["mode"] == "split" and rows[0]["key"] == "bou, hedex"
    with pytest.raises(ValueError):
        store.set_mode("Anything", "other")
    with pytest.raises(ValueError):
        store.set_mode("   ", "split")


def test_the_artist_list_and_page_models_follow_the_index(qapp, library_setup) -> None:
    database, library, _music = library_setup
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    artists = ArtistListModel(service)
    assert artists.totalCount == len(service.artists())
    assert artists.count == artists.totalCount

    artists.setFilterText("  SUB ")
    assert [artists.data(artists.index(0, 0))["name"]] == ["Sub Focus"]
    assert artists.count == 1
    artists.setFilterText("")
    assert artists.count == artists.totalCount
    assert artists.rowForKey("sub focus") >= 0 and artists.rowForKey("missing") == -1

    page = ArtistPageModel(service, library, jobs)
    page.open("sub focus")
    _wait_rows(qapp, page.tracks, 2)
    titles = [row["title"] for row in page.tracks.rows_snapshot()]
    assert titles == sorted(titles, key=str.casefold)
    assert page.name == "Sub Focus" and page.trackCount == 2
    assert page.oneArtistCredits == ["Sub Focus & Wilkinson"] and page.canSplit is False

    page.open("status")
    assert page.canMakeOneArtist is True
    assert [credit.casefold() for credit in page.oneArtistCredits] == ["chase & status"]
    page.makeOneArtist()
    _settle(qapp, service, refresh=False)
    assert page.artistKey == ""  # "Status" no longer exists: the page is closed
    jobs.shutdown()


def test_a_new_track_appears_after_a_refresh(qapp, library_setup) -> None:
    database, library, music = library_setup
    jobs, service = _service(qapp, database, library)
    _settle(qapp, service)
    assert "newcomer" not in _names(service)
    path = music / "newcomer.wav"
    _write_wav(path)
    root_id = library.roots()[0]["id"]
    library.upsert_location(
        root_id,
        "newcomer.wav",
        path,
        SourceRevision.observe(path),
        MetadataSnapshot(artist=("Newcomer",), technical=TechnicalInfo(duration_us=1_000_000)),
        library.current_generation(root_id),
    )
    _settle(qapp, service)
    assert "newcomer" in _names(service)
    jobs.shutdown()


def _wait_rows(qapp, model, expected: int) -> None:
    deadline = time.monotonic() + 10
    while model.count < expected and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        QTest.qWait(5)
    assert model.count == expected

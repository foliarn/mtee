"""Spotify-style meta line of a playlist header: wording and the data handed to QML."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.domain.durations import format_playlist_meta
from mtee.domain.playlists import LIKED_PLAYLIST_ID
from mtee.models.playlists_model import PlaylistsModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.jobs import JobService
from mtee.services.playlist_service import PlaylistService


@pytest.mark.parametrize(
    ("count", "seconds", "expected"),
    [
        (1, 200, "1 track, 3 min 20 sec"),
        (8, 34 * 60 + 26, "8 tracks, 34 min 26 sec"),
        (3, 10 * 60 + 43, "3 tracks, 10 min 43 sec"),
        (25, 3600 + 12 * 60 + 40, "25 tracks, 1 hr 12 min"),
        (4, 2 * 3600, "4 tracks, 2 hr"),
        (2, 45, "2 tracks, 45 sec"),
        (5, 10 * 60, "5 tracks, 10 min"),
        (0, 0, "0 tracks"),
        (0, 120, "0 tracks"),
        (3, 0, "3 tracks"),
    ],
)
def test_the_meta_line_reads_like_spotify(count: int, seconds: int, expected: str) -> None:
    assert format_playlist_meta(count, seconds) == expected


def test_details_carry_the_track_count_and_the_meta_text(qapp, qtbot, tmp_path: Path) -> None:
    database = Database(tmp_path / "playlists.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    repository = PlaylistsRepository(database)
    identity = repository.create("Night drive")
    jobs = JobService(qapp, max_thread_count=1)
    model = PlaylistsModel(
        PlaylistService(repository, library), SettingsRepository(database), jobs, tmp_path
    )

    # Before the first refresh the Liked tracks fallback already carries the keys.
    assert model.details(LIKED_PLAYLIST_ID)["metaText"] == "0 tracks"
    assert model.details(LIKED_PLAYLIST_ID)["trackCount"] == 0

    model.refresh()
    qtbot.waitUntil(lambda: bool(model.details(identity)), timeout=5_000)

    assert model.details(identity)["trackCount"] == 0
    assert model.details(identity)["metaText"] == "0 tracks"
    assert model.details(identity)["summary"].startswith("0 tracks")  # the sidebar keeps its text
    assert model.details(LIKED_PLAYLIST_ID)["metaText"] == "0 tracks"
    jobs.shutdown(1_000)
    database.close()

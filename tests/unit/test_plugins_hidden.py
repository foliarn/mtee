"""v0.1 ships without plugins: no entry, no service, and a saved Plugins activity falls back.

The Artists activity belongs to the core since step 112 (read-only view built from tags).
"""

from __future__ import annotations

from pathlib import Path

from mtee.models.workspace_model import WorkspaceModel, _known_activity
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.services.jobs import JobService


def _workspace(qapp, tmp_path: Path) -> tuple[WorkspaceModel, JobService, Database]:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    jobs = JobService(qapp, max_thread_count=1)
    workspace = WorkspaceModel(
        library=LibraryRepository(database),
        session=WorkspaceRepository(database),
        jobs=jobs,
    )
    return workspace, jobs, database


def test_v01_offers_no_plugin_activity_but_the_core_artists_one(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)

    assert workspace.pluginUiEnabled is False
    assert workspace.artistManager is None

    workspace.setActivity("artists")
    assert workspace.activity == "artists"
    workspace.setActivity("plugins")
    assert workspace.activity == "artists"
    workspace.setActivity("explorer")
    workspace.setActivity("plugins")
    assert workspace.activity == "explorer"
    workspace.setActivity("playlists")
    assert workspace.activity == "playlists"

    jobs.shutdown(1_000)
    database.close()


def test_artist_and_genre_pages_are_inert_without_their_plugins(qapp, tmp_path: Path) -> None:
    workspace, jobs, database = _workspace(qapp, tmp_path)
    tabs_before = [tab["id"] for group in workspace.groups_snapshot() for tab in group["tabs"]]

    assert workspace.trackArtists("track-a") == []
    workspace.openArtistView("catalog", "Artists")
    workspace.openArtistPage("artist-a", "Artist A")
    workspace.playArtistRows("artist-a", [], False)
    workspace.openGenreManagerView("classify", "Genre Manager")

    tabs_after = [tab["id"] for group in workspace.groups_snapshot() for tab in group["tabs"]]
    assert tabs_after == tabs_before
    assert workspace.genreManager is None

    jobs.shutdown(1_000)
    database.close()


def test_a_saved_plugins_activity_falls_back_to_explorer() -> None:
    assert _known_activity("artists") == "artists"
    assert _known_activity("plugins") == "explorer"
    assert _known_activity("unknown") == "explorer"
    assert _known_activity("playlists") == "playlists"
    # The Profile page is a tab opened from the activity bar, so it is not a saved activity.
    assert _known_activity("profile") == "explorer"

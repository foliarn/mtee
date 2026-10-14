"""v0.1 ships without plugins: no entry, no service, and saved activities fall back to Explorer."""

from __future__ import annotations

from pathlib import Path

from mtee.models.workspace_model import WorkspaceModel, _known_activity
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.services.jobs import JobService


def _workspace(qapp, tmp_path: Path) -> WorkspaceModel:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    return WorkspaceModel(
        library=LibraryRepository(database),
        session=WorkspaceRepository(database),
        jobs=JobService(qapp, max_thread_count=1),
    )


def test_v01_offers_no_plugin_or_artist_activity(qapp, tmp_path: Path) -> None:
    workspace = _workspace(qapp, tmp_path)

    assert workspace.pluginUiEnabled is False
    assert workspace.artistManager is None

    workspace.setActivity("artists")
    assert workspace.activity == "explorer"
    workspace.setActivity("plugins")
    assert workspace.activity == "explorer"
    workspace.setActivity("playlists")
    assert workspace.activity == "playlists"


def test_artist_and_genre_pages_are_inert_without_their_plugins(qapp, tmp_path: Path) -> None:
    workspace = _workspace(qapp, tmp_path)
    tabs_before = [tab["id"] for group in workspace.groups_snapshot() for tab in group["tabs"]]

    assert workspace.trackArtists("track-a") == []
    workspace.openArtistView("catalog", "Artists")
    workspace.openArtistPage("artist-a", "Artist A")
    workspace.playArtistRows("artist-a", [], False)
    workspace.openGenreManagerView("classify", "Genre Manager")

    tabs_after = [tab["id"] for group in workspace.groups_snapshot() for tab in group["tabs"]]
    assert tabs_after == tabs_before
    assert workspace.genreManager is None


def test_saved_plugin_activities_fall_back_to_explorer() -> None:
    assert _known_activity("artists") == "explorer"
    assert _known_activity("plugins") == "explorer"
    assert _known_activity("unknown") == "explorer"
    assert _known_activity("playlists") == "playlists"
    assert _known_activity("profile") == "profile"

"""Artist folders, filters, hidden artists and the profile editor (plan 106)."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_analysis_ui import _centre, _first, _items, _wait_for

from mtee.app import _build_runtime, _shutdown
from mtee.cli import parse_arguments
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.artist_repository import ArtistRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artist_identification_service import ArtistIdentificationService


def _seed(base: Path) -> Path:
    music = base / "music"
    music.mkdir(parents=True)
    database = Database(base / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    repository = ArtistRepository(database)
    identification = ArtistIdentificationService(library, repository)
    root_id = library.add_root(music)["id"]
    for index, artists in enumerate([["Hedex", "Bou"], ["Hedex"], ["Nia"], ["Ghost"]]):
        path = music / f"{index}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 800)
        generation = library.begin_scan(root_id)
        library.upsert_locations(
            root_id,
            [
                (
                    path.name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(title=(path.stem,), technical=TechnicalInfo(duration_us=100)),
                )
            ],
            generation,
        )
        track = library.path_owner(path)
        assert track is not None
        identification.sync_tags(track, artists, None)
    ids = {item["name"]: item["id"] for item in repository.catalog()}
    repository.save_artist_profile(
        ids["Hedex"], roles=["Producer", "DJ"], bass_related=True, tags=[], hidden=False
    )
    repository.save_artist_profile(
        ids["Bou"], roles=["MC"], bass_related=None, tags=[], hidden=False
    )
    repository.save_artist_profile(
        ids["Ghost"], roles=["Singer"], bass_related=None, tags=[], hidden=True
    )
    database.close()
    return base / "data"


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    QTest.mouseClick(
        window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _centre(item)
    )
    QTest.qWait(60)


def test_folders_filters_hidden_artists_and_profile_editor(qapp, tmp_path: Path) -> None:
    data_dir = _seed(tmp_path)
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        manager = cast(Any, workspace)._artist_manager
        workspace.openArtistView("catalog", "Artists")
        everyone = manager.listModel("catalog.all")
        _wait_for(window, lambda: everyone.count == 3 and not everyone.loading)

        # One folder per type, an artist with several types in each of its folders.
        counts = {
            key: manager.listModel(f"catalog.{key}").count
            for key in ("Producer", "DJ", "Singer", "MC", "none")
        }
        _wait_for(window, lambda: manager.listModel("catalog.none").count == 1)
        assert counts["Singer"] == 0  # Ghost is hidden
        for key in ("Producer", "DJ", "MC", "none"):
            assert _first(window.contentItem(), f"artistFolder{key}").isVisible()

        # Type chips filter with OR; the minimum number of tracks narrows further.
        catalog = manager.listModel("catalog")
        _wait_for(window, lambda: catalog.count == 3)
        _click(window, _first(window.contentItem(), "artistsTypeMC"))
        assert catalog.count == 1
        _click(window, _first(window.contentItem(), "artistsTypeDJ"))
        assert catalog.count == 2
        _click(window, _first(window.contentItem(), "artistsClearFilters"))
        assert catalog.count == 3

        # Hidden artists appear with the switch, and stay out of the folders otherwise.
        _click(window, _first(window.contentItem(), "artistsShowHidden"))
        _wait_for(window, lambda: catalog.count == 4)
        assert manager.listModel("catalog.Singer").count == 1
        _click(window, _first(window.contentItem(), "artistsShowHidden"))
        _wait_for(window, lambda: catalog.count == 3)

        # The profile is edited from the artist page and reaches the lists.
        ids = {item["name"]: item["id"] for item in manager.service.repository.catalog()}
        workspace.openArtistPage(ids["Nia"], "Nia")
        _wait_for(window, lambda: bool(_items(window.contentItem(), "artistEditProfile")))
        _click(window, _first(window.contentItem(), "artistEditProfile"))
        _wait_for(window, lambda: bool(_items(window.contentItem(), "profileRoleDJ")))
        _click(window, _first(window.contentItem(), "profileRoleDJ"))
        _click(window, _first(window.contentItem(), "profileSave"))
        _wait_for(window, lambda: manager.artistProfile(ids["Nia"])["roles"] == ["DJ"])
        _wait_for(window, lambda: manager.listModel("catalog.none").count == 0)
        assert manager.listModel("catalog.DJ").count == 2
    finally:
        _shutdown(runtime)

"""A source can be classified and reviewed through the Qt command boundary."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication

from mtee.models.track_list_model import TrackListModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.plugins.genre_manager.models import GenreManagerModel


def _state(model: GenreManagerModel) -> dict[str, Any]:
    return cast(dict[str, Any], model.state)


def _ready(model: GenreManagerModel) -> None:
    deadline = time.monotonic() + 5
    while _state(model)["busy"] and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()
    assert not _state(model)["busy"], _state(model)["error"]
    assert not _state(model)["error"]


def test_classify_review_filter_and_undo_on_a_synthetic_source(qapp, tmp_path: Path) -> None:
    database = Database(tmp_path / "model.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root_path = tmp_path / "music"
    root_id = library.add_root(root_path)["id"]
    source_path = root_path / "House" / "Demo.wav"
    with database.transaction() as connection:
        connection.execute("INSERT INTO tracks(track_id) VALUES('track-a')")
        connection.execute(
            "INSERT INTO track_locations(path_key,track_id,path,size_bytes,mtime_ns,"
            "status,metadata_json) VALUES(?,?,?,?,?,'readable','{}')",
            (str(source_path).casefold(), "track-a", str(source_path), 1, 1),
        )
        connection.execute(
            "INSERT INTO root_tracks(root_id,track_id,relative_path,seen_generation) "
            "VALUES(?,?,?,0)",
            (root_id, "track-a", "House/Demo.wav"),
        )
    model = GenreManagerModel(database, library, PlaylistsRepository(database))
    try:
        _ready(model)
        assert _state(model)["total"] == 0
        model.openSource("folder", "House", root_id, False)
        _ready(model)
        assert _state(model)["sourceLabel"] == "House"
        rows = cast(TrackListModel, model.rowsModel)
        assert rows.track_ids_snapshot() == ["track-a"]
        assert rows.rows_snapshot()[0]["genres"] == []
        house = next(
            item["genre_id"] for item in _state(model)["genres"] if item["name"] == "House"
        )
        model.selectTrack("track-a", False, False)
        model.addGenreToSelection(house)
        _ready(model)
        assert rows.rows_snapshot()[0]["genres"] == [house]
        assert not rows.rows_snapshot()[0]["reviewed"]
        model.markSelectedReviewed()
        _ready(model)
        assert rows.rows_snapshot()[0]["reviewed"]
        model.setViewMode("to_review")
        assert rows.count == 0
        assert _state(model)["selectedIds"] == []
        model.undo()
        _ready(model)
        assert rows.count == 1
        assert not rows.rows_snapshot()[0]["reviewed"]
    finally:
        model.close()
        database.close()

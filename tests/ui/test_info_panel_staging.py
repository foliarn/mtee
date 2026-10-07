"""The Info panel stages edits and writes them, with the artists catalog, on Save."""

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
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.metadata_reader import MetadataReader


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    QTest.mouseClick(
        window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _centre(item)
    )
    QTest.qWait(40)


def _type(window: QQuickWindow, text: str) -> None:
    for character in text:
        QTest.keyClick(window, character)


def _field_input(window: QQuickWindow, index: int) -> QQuickItem:
    inputs = [item for item in _items(window.contentItem(), "fieldEditorInput") if item.isVisible()]
    inputs.sort(key=lambda item: item.mapToScene(item.boundingRect().topLeft()).y())
    return inputs[index]


def test_edits_wait_for_save_and_reach_the_artists_catalog(qapp, tmp_path: Path) -> None:
    music = tmp_path / "music"
    _write(music / "one.wav")
    data_dir = tmp_path / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    root = LibraryRepository(database).add_root(music)
    database.close()
    root_id = str(root["id"])

    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(data_dir)]))
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    try:
        workspace = cast(WorkspaceModel, runtime.workspace)
        library = cast(Any, workspace)._library
        _wait_for(window, lambda: len(library.track_ids_in_tree(root_id, "")) == 1)
        track_id = library.path_owner(music / "one.wav")
        editor = cast(Any, workspace.metadataEditor)
        workspace.openFolder(f"root:{root_id}")
        workspace.selectTrack(track_id, "single", [])
        workspace.showRightPanel("info")
        _wait_for(window, lambda: bool(_items(window.contentItem(), "fieldEditorInput")))
        QTest.qWait(300)

        # Typing a title only stages it: nothing is written, and no field is locked.
        title = _field_input(window, 0)
        _click(window, title)
        _type(window, "Staged title")
        _wait_for(window, lambda: editor.hasChanges)
        assert MetadataReader().read(music / "one.wav").title == ()
        assert "title" in editor.dirtyFields

        # A date that is not a date blocks Save and says why; a real one is normalized.
        date_index = [f["key"] for f in editor.infoFields].index("date") - 1  # artist is a chip
        date = _field_input(window, date_index)
        _click(window, date)
        _type(window, "later")
        _wait_for(window, lambda: not editor.canSave)
        assert "date" in editor.fieldErrors
        for _ in range(5):
            QTest.keyClick(window, Qt.Key.Key_Backspace)
        _type(window, "2024/3/5")
        _wait_for(window, lambda: editor.canSave)

        # The artist is one chip each, and "Nikita, the Wicked" stays a single artist.
        artist_input = _first(window.contentItem(), "artistInput")
        _click(window, artist_input)
        _type(window, "Nikita, the Wicked")
        QTest.keyClick(window, Qt.Key.Key_Return)
        QTest.qWait(60)
        assert _first(window.contentItem(), "keepAsOneArtist").isVisible()
        _click(window, _first(window.contentItem(), "keepAsOneArtist"))
        assert [chip["name"] for chip in editor.artistChips] == ["Nikita, the Wicked"]

        _click(window, _first(window.contentItem(), "saveChanges"))
        _wait_for(window, lambda: editor.saveState == "saved", 20)
        assert runtime.jobs.wait_for_done(20_000)
        saved = MetadataReader().read(music / "one.wav")
        assert saved.title == ("Staged title",)
        assert saved.date == ("2024-03-05",)
        assert saved.artist == ("Nikita, the Wicked",)
        assert editor.changeCount == 0

        # The artists catalog follows, and the new revision does not lock the fields.
        catalog = cast(Any, workspace)._artist_manager
        repository = cast(Any, catalog)._service._repository
        assert [item["name"] for item in repository.catalog()] == ["Nikita, the Wicked"]
        assert "Nikita, the Wicked" in repository.protected_names()
        fields = {field["key"]: field for field in editor.infoFields}
        assert all(field["editable"] for field in fields.values())

        # Replacing the credit removes the former artist, who had only this track.
        editor.stageArtistRemove("Nikita, the Wicked")
        editor.stageArtistAdd("Hedex")
        editor.saveChanges()
        _wait_for(window, lambda: [i["name"] for i in repository.catalog()] == ["Hedex"], 20)
        assert [item["name"] for item in repository.artist_names("")] == ["Hedex"]
    finally:
        _shutdown(runtime)

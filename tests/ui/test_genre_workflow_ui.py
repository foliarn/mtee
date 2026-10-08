from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.integration.test_genre_seed import fixture_library, genre_id
from tests.ui.test_analysis_ui import _click, _items, _wait_for
from tests.unit.test_player_service import FakeBackend

from mtee.app import _build_runtime, _destroy_windows, _shutdown
from mtee.cli import parse_arguments
from mtee.models.workspace_model import WorkspaceModel
from mtee.services.genre_seed_service import GenreSeedService


@pytest.fixture(scope="module")
def shared_ui(qapp, tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setattr("mtee.app.MpvBackend", FakeBackend)
    tmp_path = tmp_path_factory.mktemp("genre-ui")
    path, root, ids = fixture_library(tmp_path)
    service = GenreSeedService(path)
    service.apply(service.preview(root))
    runtime = _build_runtime(qapp, parse_arguments(["--data-dir", str(path.parent)]))
    assert runtime
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    workspace = cast(WorkspaceModel, runtime.workspace)
    tab = f"folder:{root}/house"
    workspace.openFolder(tab)
    model = workspace.trackModelForTab(tab, "folder", f"{root}/house", "filename", True, 0)
    _wait_for(window, lambda: len(model.rows_snapshot()) == 2 and not workspace._genres._busy)
    try:
        yield window, workspace, model, tab, ids
    finally:
        _shutdown(runtime)
        _destroy_windows(runtime)
        patch.undo()


@pytest.fixture
def ui(shared_ui):
    window, workspace, model, tab, _ids = shared_ui
    QTest.keyClick(window, Qt.Key_Escape)
    genres = workspace._genres
    _wait_for(window, lambda: not genres._busy)
    for key in list(genres._preferences["views"]):
        genres.setFilter(key, {"version": 1, "mode": "all", "criteria": []})
        _wait_for(window, lambda: not genres._busy)
    while genres._undo:
        genres.undo()
        _wait_for(window, lambda: not genres._busy)
        assert not genres._message.startswith("Could not save")
    genres.setBrush("0:" + tab, genre_id("House"))
    _wait_for(window, lambda: not genres._busy and len(model.rows_snapshot()) == 2)
    workspace.setActiveGroup(0)
    yield shared_ui


def test_brush_checkbox_is_independent_from_selection_and_player(ui):
    window, workspace, model, tab, _ids = ui
    workspace._genres.setBrush("0:" + tab, genre_id("House \u203a Deep"))
    _wait_for(
        window,
        lambda: (
            not workspace._genres._busy
            and any(i.isVisible() for i in _items(window.contentItem(), "trackGenreCheckbox"))
        ),
    )
    checkbox = next(i for i in _items(window.contentItem(), "trackGenreCheckbox") if i.isVisible())
    before = workspace.selected_ids_snapshot()
    _click(window, checkbox)
    _wait_for(
        window,
        lambda: (
            all(
                r["genreIds"] == [genre_id("House \u203a Deep")]
                for r in model.rows_snapshot()
                if r.get("genreRevision") == 2
            )
            and any(r["genreIds"] == [genre_id("House \u203a Deep")] for r in model.rows_snapshot())
        ),
    )
    assert workspace.selected_ids_snapshot() == before
    assert not workspace.isPlaying
    workspace._genres.undo()
    _wait_for(
        window,
        lambda: (
            not workspace._genres._busy
            and all(r["mteeGenres"] == ["House"] for r in model.rows_snapshot())
        ),
    )


def test_filter_retains_changed_rows_until_refresh(ui):
    window, workspace, model, tab, _ids = ui
    deep = genre_id("House \u203a Deep")
    workspace._genres.setBrush("0:" + tab, deep)
    _wait_for(window, lambda: not workspace._genres._busy)
    workspace._genres.setFilter(
        "0:" + tab, {"version": 1, "mode": "all", "criteria": [{"kind": "without_brush", "id": ""}]}
    )
    _wait_for(window, lambda: not workspace._genres._busy and len(model.rows_snapshot()) == 2)
    visible = model.track_ids_snapshot()
    workspace.applyGenreBrush(tab, 0, visible, True)
    _wait_for(
        window,
        lambda: (
            len(model.rows_snapshot()) == 2
            and all(r.get("genreRetained") for r in model.rows_snapshot())
        ),
    )
    assert model.track_ids_snapshot() == visible
    assert not workspace.isPlaying
    workspace.refreshGenreFilter(tab, 0)
    _wait_for(window, lambda: not model.rows_snapshot())
    workspace._genres.setFilter(
        "0:" + tab, {"version": 1, "mode": "all", "criteria": [{"kind": "genre", "id": "missing"}]}
    )
    _wait_for(window, lambda: "Unknown genre" in workspace.message)
    assert not model.rows_snapshot()


def test_manager_quick_create_and_preferences_survive_reload(ui):
    window, workspace, _model, tab, _ids = ui
    genres = workspace._genres
    genres.quickCreate("0:" + tab, "Forgotten", genre_id("House"))
    _wait_for(
        window,
        lambda: (
            not genres._busy
            and any(g["name"] == "Forgotten" for g in genres.catalog_snapshot()["genres"])
        ),
    )
    node = next(g for g in genres.catalog_snapshot()["genres"] if g["name"] == "Forgotten")
    assert node["path"] == "House \u203a Forgotten"
    assert genres.view_state("0:" + tab)["brush"] == node["genre_id"]
    genres.reload()
    _wait_for(window, lambda: not genres._busy)
    assert genres.view_state("0:" + tab)["brush"] == node["genre_id"]
    button = next(i for i in _items(window.contentItem(), "genreBrushBar") if i.isVisible())
    # Load the real manager from the same source component.
    buttons = [i for i in button.childItems()]
    assert buttons
    open_button = next(i for i in _items(window.contentItem(), "openGenreManager") if i.isVisible())
    _click(window, open_button)
    _wait_for(
        window, lambda: any(i.isVisible() for i in _items(window.contentItem(), "genreNameInput"))
    )
    capture = Path(".local/validation/109/ui-manager.png")
    capture.parent.mkdir(parents=True, exist_ok=True)
    assert window.grabWindow().save(str(capture))
    assert not workspace.isPlaying


def test_two_views_refresh_without_changing_playback_queue(ui):
    window, workspace, model, tab, _ids = ui
    source = tab.partition(":")[2]
    workspace.toggleSplit()
    second = workspace.trackModelForTab(tab, "folder", source, "filename", True, 1)
    _wait_for(window, lambda: len(second.rows_snapshot()) == 2)
    genres = workspace._genres
    genres.setBrush("0:" + tab, genre_id("House \u203a Deep"))
    _wait_for(window, lambda: not genres._busy)
    genres.setBrush("1:" + tab, genre_id("House \u203a Minimal"))
    _wait_for(window, lambda: not genres._busy)
    assert genres.view_state("0:" + tab)["brush"] != genres.view_state("1:" + tab)["brush"]
    workspace.setActiveGroup(0)
    rows = model.rows_snapshot()
    workspace.playTrackFromRows(rows[0]["id"], tab, rows)
    _wait_for(window, lambda: workspace.isPlaying)
    player = workspace._player._service
    queue = player.queue_state
    playing = workspace.playingId
    workspace.applyGenreBrush(tab, 0, model.track_ids_snapshot(), True)
    _wait_for(
        window,
        lambda: all(r["mteeGenres"] == ["House \u203a Deep"] for r in second.rows_snapshot()),
    )
    assert player.queue_state == queue
    assert workspace.isPlaying and workspace.playingId == playing
    workspace.undoSave()
    _wait_for(
        window,
        lambda: (
            not genres._busy and all(r["mteeGenres"] == ["House"] for r in model.rows_snapshot())
        ),
    )
    assert player.queue_state == queue


def test_failed_write_resets_checkbox_and_can_retry(ui, monkeypatch):
    window, workspace, model, tab, _ids = ui
    genres = workspace._genres
    genres.setBrush("0:" + tab, genre_id("House \u203a Deep"))
    _wait_for(window, lambda: not genres._busy)
    playing_before = workspace.isPlaying
    original = genres.repository.change_membership

    def fail(*args, **kwargs):
        raise OSError("Disk unavailable")

    monkeypatch.setattr(genres.repository, "change_membership", fail)
    checkbox = next(
        i
        for i in _items(window.contentItem(), "trackGenreCheckbox")
        if i.isVisible() and i.parentItem().property("groupIndex") == 0
    )
    _click(window, checkbox)
    _wait_for(window, lambda: genres._message.startswith("Could not save"))
    assert not checkbox.property("checked")
    assert all(r["mteeGenres"] == ["House"] for r in model.rows_snapshot())
    monkeypatch.setattr(genres.repository, "change_membership", original)
    genres.retry()
    _wait_for(
        window,
        lambda: (
            not genres._busy
            and any(r["mteeGenres"] == ["House \u203a Deep"] for r in model.rows_snapshot())
        ),
    )
    assert workspace.isPlaying == playing_before


def test_advanced_subtree_delete_controls_are_in_settings(ui):
    window, workspace, _model, _tab, _ids = ui
    workspace.openSettings()
    _wait_for(
        window,
        lambda: any(i.isVisible() for i in _items(window.contentItem(), "settingsGenreManager")),
    )
    _click(
        window,
        next(i for i in _items(window.contentItem(), "settingsGenreManager") if i.isVisible()),
    )
    _wait_for(
        window,
        lambda: any(i.isVisible() for i in _items(window.contentItem(), "genreAdvancedControls")),
    )
    assert any(i.isVisible() for i in _items(window.contentItem(), "genreManagerTable"))


def test_manager_drag_moves_genre_and_keeps_identity(ui):
    window, workspace, _model, _tab, _ids = ui
    workspace.openFolder(_tab)
    _wait_for(
        window, lambda: any(i.isVisible() for i in _items(window.contentItem(), "openGenreManager"))
    )
    _click(
        window, next(i for i in _items(window.contentItem(), "openGenreManager") if i.isVisible())
    )
    _wait_for(
        window,
        lambda: any(i.isVisible() for i in _items(window.contentItem(), "genreManagerSearch")),
    )
    search = next(i for i in _items(window.contentItem(), "genreManagerSearch") if i.isVisible())
    search.setProperty("text", "house")
    QTest.qWait(100)
    tech, bass = genre_id("House \u203a Tech"), genre_id("House \u203a Bass")
    source = next(
        i for i in _items(window.contentItem(), "genreCatalogRow_" + tech) if i.isVisible()
    )
    target = next(
        i for i in _items(window.contentItem(), "genreCatalogRow_" + bass) if i.isVisible()
    )
    start = source.mapToScene(source.boundingRect().center()).toPoint()
    end = target.mapToScene(target.boundingRect().center()).toPoint()
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 11):
        QTest.mouseMove(window, start + (end - start) * (step / 10), 30)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    _wait_for(
        window,
        lambda: any(
            g["genre_id"] == tech and g["parent_id"] == bass
            for g in workspace._genres.catalog_snapshot()["genres"]
        ),
    )
    workspace._genres.undo()
    _wait_for(window, lambda: not workspace._genres._busy)
    assert (
        next(g for g in workspace._genres.catalog_snapshot()["genres"] if g["genre_id"] == tech)[
            "path"
        ]
        == "House \u203a Tech"
    )

"""The UI contributions of plugins (plan 121.5), in the live QML window.

A tiny plugin (``tests/helpers/ui_plugin.py``) makes one of each contribution. Each one must
appear while the plugin runs and be absent when it is off or when no plugin folder is set.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QObject, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.helpers.ui_plugin import LIST_KIND, PAGE_KIND, PLUGIN_ID, write_ui_plugin
from tests.ui.track_list_fixtures import add_folder_tracks

import mtee.plugins
from mtee.app import _build_runtime, _Runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.loader import PluginPreferences
from mtee.services.app_paths import resolve_app_paths


@pytest.fixture(autouse=True)
def restore_plugin_path() -> Iterator[None]:
    """A test that loads the plugin leaves the import path and modules as it found them."""
    before = list(mtee.plugins.__path__)
    yield
    mtee.plugins.__path__[:] = before
    for name in [key for key in sys.modules if key.startswith(f"mtee.plugins.{PLUGIN_ID}")]:
        del sys.modules[name]


def _find(window: QQuickWindow, name: str) -> QQuickItem | None:
    pending = [window.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def _texts(window: QQuickWindow) -> list[str]:
    found: list[str] = []
    pending = [window.contentItem()]
    while pending:
        item = pending.pop()
        text = item.property("text")
        if isinstance(text, str) and item.isVisible():
            found.append(text)
        pending.extend(item.childItems())
    return found


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    centre = item.mapToScene(item.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    QTest.qWait(30)


def _settle(runtime: _Runtime) -> None:
    for _ in range(30):
        runtime.jobs.wait_for_done(500)
        QCoreApplication.processEvents()
        QTest.qWait(20)


def _start(tmp_path: Path, *, folder: bool = True, enabled: bool = True) -> tuple[_Runtime, Any]:
    """Start the real application, optionally with the probe plugin folder and its switch."""
    data = tmp_path / "data"
    plugins = tmp_path / "plugins"
    write_ui_plugin(plugins)
    if enabled:
        paths = resolve_app_paths(data).ensure()
        database = Database(paths.database_path)
        database.migrate()
        PluginPreferences(SettingsRepository(database)).set_enabled(PLUGIN_ID, True)
        database.close()
    application = create_application(["mtee"])
    options = AppOptions(
        data_dir=data, demo=False, scenario="explorer", plugin_dirs=(plugins,) if folder else ()
    )
    runtime = _build_runtime(application, options)
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    return runtime, sys.modules.get(f"mtee.plugins.{PLUGIN_ID}")


def _plugin_ui(workspace: WorkspaceModel) -> Any:
    """The plugin contributions model; QML-facing members are untyped for pyright."""
    return cast(Any, workspace).pluginUi


def _workspace(runtime: _Runtime) -> WorkspaceModel:
    return cast(WorkspaceModel, runtime.workspace)


def _window(runtime: _Runtime) -> QQuickWindow:
    return cast(QQuickWindow, runtime.engine.rootObjects()[0])


def test_without_a_plugin_folder_nothing_is_added(qapp, tmp_path: Path) -> None:
    runtime, _module = _start(tmp_path, folder=False, enabled=False)
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        ui = _plugin_ui(workspace)
        assert ui.property("active") is False
        assert ui.property("activities") == []
        assert ui.property("columnOptions") == []
        assert workspace.pluginSettings is None
        workspace.openSettings()
        _settle(runtime)
        assert _find(window, "settingsTab_plugins") is None
        assert _find(window, "settingsTab_about") is not None
        assert _find(window, "activity-ui_probe.main") is None
        assert _find(window, "pluginSections") is not None  # the empty footer takes no space
        footer = cast(QQuickItem, _find(window, "pluginSections"))
        assert footer.height() == 0
    finally:
        _shutdown(runtime)


def test_a_folder_without_the_switch_lists_the_plugin_but_adds_nothing(
    qapp, tmp_path: Path
) -> None:
    runtime, module = _start(tmp_path, enabled=False)
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        assert module is None  # the plugin's code is not imported until it is enabled
        assert _plugin_ui(workspace).property("active") is False
        assert _find(window, "activity-ui_probe.main") is None
        workspace.openSettings()
        workspace.setSettingsPage("plugins")
        _settle(runtime)
        assert _find(window, "settingsTab_plugins") is not None
        row = cast(QQuickItem, _find(window, "pluginRow_ui_probe"))
        assert row.isVisible()
        texts = _texts(window)
        assert "UI probe" in texts
        assert "v1.2.3" in texts
        assert "Uses network" in texts
        assert "Disabled" in texts
        assert "1 plugin found" in texts
    finally:
        _shutdown(runtime)


def test_the_switch_is_saved_and_applies_after_a_restart(qapp, tmp_path: Path) -> None:
    runtime, _module = _start(tmp_path, enabled=False)
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.openSettings()
        workspace.setSettingsPage("plugins")
        _settle(runtime)
        _click(window, cast(QQuickItem, _find(window, "pluginSwitch")))
        _settle(runtime)
        settings = SettingsRepository(runtime.database)
        assert PluginPreferences(settings).enabled() == [PLUGIN_ID]
        # Still not running: the change applies at the next start, and the row says so.
        assert "Disabled" in _texts(window)
        assert any("next time MTEE starts" in text for text in _texts(window))
    finally:
        _shutdown(runtime)


def test_a_plugin_folder_can_be_removed_and_the_page_goes_with_the_last_one(
    qapp, tmp_path: Path
) -> None:
    runtime, _module = _start(tmp_path, enabled=False)
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.openSettings()
        workspace.setSettingsPage("plugins")
        _settle(runtime)
        _click(window, cast(QQuickItem, _find(window, "removePluginFolder")))
        _settle(runtime)
        assert _find(window, "settingsTab_plugins") is None
        assert workspace.settingsPage == "general"
    finally:
        _shutdown(runtime)


def test_a_running_plugin_adds_its_activity_sections_and_foot(qapp, tmp_path: Path) -> None:
    runtime, module = _start(tmp_path)
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        assert module is not None
        assert "startup" in _after_jobs(runtime, module)
        button = cast(QQuickItem, _find(window, "activity-ui_probe.main"))
        _click(window, button)
        _settle(runtime)
        assert workspace.activity == "ui_probe.main"
        texts = _texts(window)
        assert "Alpha list" in texts and "Beta list" in texts
        assert "Connected as probe" in texts
        # A single section of a plugin activity has no header of its own; the pane has one.
        assert "PROBE" in [text.upper() for text in texts]
        _click(window, cast(QQuickItem, _find(window, "pluginPaneAction_refresh")))
        assert module.EVENTS[-1] == "refresh"
        # The section of the Playlists activity sits below the local playlists.
        workspace.setActivity("playlists")
        _settle(runtime)
        assert "PROBE SIDE" in [text.upper() for text in _texts(window)]
        assert "Gamma" in _texts(window)
    finally:
        _shutdown(runtime)


def _after_jobs(runtime: _Runtime, module: Any) -> list[str]:
    _settle(runtime)
    return list(module.EVENTS)


def test_a_row_of_a_section_opens_the_tab_the_plugin_names(qapp, tmp_path: Path) -> None:
    runtime, _module = _start(tmp_path)
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.setActivity("ui_probe.main")
        _settle(runtime)
        _click(window, cast(QQuickItem, _find(window, "pluginRow_alpha")))
        _settle(runtime)
        tabs = [tab for group in workspace.groups_snapshot() for tab in group["tabs"]]
        assert [tab["id"] for tab in tabs] == [f"{LIST_KIND}:alpha"]
        assert tabs[0]["title"] == "Probe alpha"
        # The group row folds; it opens nothing.
        _click(window, cast(QQuickItem, _find(window, "pluginRow_group")))
        assert len([tab for g in workspace.groups_snapshot() for tab in g["tabs"]]) == 1
        # A tab whose content is a QML file of the plugin, which imports Mtee.
        workspace.openPluginTab(PAGE_KIND, "x")
        _settle(runtime)
        assert _find(window, "probePage") is not None
        assert _find(window, "probeChip") is not None
    finally:
        _shutdown(runtime)


def test_the_plugin_list_has_unavailable_rows_a_column_and_header_buttons(
    qapp, tmp_path: Path
) -> None:
    runtime, module = _start(tmp_path)
    try:
        add_folder_tracks(runtime, tmp_path / "audio", 2)
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.openPluginTab(LIST_KIND, "alpha")
        _settle(runtime)
        rows = _rows(workspace, f"{LIST_KIND}:alpha")
        assert [row["id"] for row in rows] == ["r1", "r2", "r3"]
        assert [row["available"] for row in rows] == [True, False, False]
        assert rows[1]["plugin"]["ui_probe.status"] == {"text": "Missing", "tone": "secondary"}
        assert rows[1]["rowAction"] == "Download"
        assert rows[0]["plugin"]["ui_probe.status"]["text"] == "Local"
        # The column starts visible in this tab kind (default_visible_for).
        texts = _texts(window)
        assert "Probe status" in texts
        assert "Missing" in texts and "Local" in texts
        # Header: the plugin's kind label and its buttons beside Play and Shuffle.
        assert "Probe playlist" in texts
        assert "Download missing (2)" in texts
        assert "Watch" in texts
        # An unavailable row has no play and no add button; its inline button is shown.
        missing = cast(QQuickItem, _find(window, "trackRow_2"))
        assert _find_child(missing, "trackAdd_r2") is not None
        assert not cast(QQuickItem, _find_child(missing, "trackAdd_r2")).isVisible()
        assert cast(QQuickItem, _find_child(missing, "trackRowAction")).isVisible()
        local = cast(QQuickItem, _find(window, "trackRow_1"))
        assert cast(QQuickItem, _find_child(local, "trackAdd_r1")).isVisible()
        assert not cast(QQuickItem, _find_child(local, "trackRowAction")).isVisible()
        # The buttons run the plugin's functions with the ref of the tab.
        _click(window, cast(QQuickItem, _find(window, "pluginHeaderAction_ui_probe.download")))
        assert module.EVENTS[-1] == "download alpha"
        _click(window, cast(QQuickItem, _find_child(missing, "trackRowAction")))
        assert module.EVENTS[-1] == "row action r2"
        _click(window, cast(QQuickItem, _find(window, "pluginHeaderAction_ui_probe.watch")))
        assert module.EVENTS[-1] == "watch"
    finally:
        _shutdown(runtime)


def _rows(workspace: WorkspaceModel, source: str) -> list[dict[str, Any]]:
    model = workspace._active_track_model(source)
    assert model is not None
    return model.rows_snapshot()


def _find_child(root: QQuickItem, name: str) -> QQuickItem | None:
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    return None


def test_play_skips_the_rows_without_a_local_file(qapp, tmp_path: Path) -> None:
    runtime, _module = _start(tmp_path)
    try:
        _root, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 2)
        workspace = _workspace(runtime)
        played: list[tuple[Any, ...]] = []

        player = cast(Any, workspace._player)
        assert player is not None
        player.playQueueWithRows = lambda *arguments: played.append(arguments)
        workspace.openPluginTab(LIST_KIND, "alpha")
        _settle(runtime)
        source = f"{LIST_KIND}:alpha"
        rows = _rows(workspace, source)

        workspace.playPluginRows(LIST_KIND, "alpha", rows, False)
        assert [row["id"] for row in played[-1][4]] == [track_ids[0]]
        assert played[-1][3] == "Probe alpha"

        # A row with no file is not played, and says why.
        workspace.playTrack("r2", source)
        assert len(played) == 1
        assert "no local file" in cast(Any, workspace).message

        # The row with a file plays, through the track it names.
        workspace.playTrack("r1", source)
        assert played[-1][0] == [track_ids[0]]
    finally:
        _shutdown(runtime)


def test_the_context_menu_shows_the_plugin_group_for_the_selected_rows(
    qapp, tmp_path: Path
) -> None:
    runtime, module = _start(tmp_path)
    try:
        add_folder_tracks(runtime, tmp_path / "audio", 1)
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.openPluginTab(LIST_KIND, "alpha")
        _settle(runtime)
        source = f"{LIST_KIND}:alpha"

        missing = workspace.pluginTrackActions(source, ["r2"])
        assert missing == [
            {"header": True, "label": "Probe", "key": ""},
            {"header": False, "key": f"{PLUGIN_ID}.link", "label": "Link to a local track"},
            {"header": False, "key": f"{PLUGIN_ID}.better", "label": "Get a better copy"},
        ]
        local = workspace.pluginTrackActions(source, ["r1"])
        assert [item["label"] for item in local] == ["Probe", "Get a better copy"]

        workspace.runPluginTrackAction(source, ["r2", "r3"], f"{PLUGIN_ID}.link")
        assert module.EVENTS[-1] == "link r2,r3"

        # In the open window: a row without a file hides what needs one, and offers the group.
        menu_labels = _open_menu_labels(window, 2)
        assert "Play" not in menu_labels and "Analyze" not in menu_labels
        assert "File actions" not in menu_labels
        assert "PROBE" in menu_labels and "Link to a local track" in menu_labels
        local_labels = _open_menu_labels(window, 1)
        assert "Play" in local_labels and "Add to playlist…" in local_labels
        assert local_labels.index("PROBE") < local_labels.index("File actions")
    finally:
        _shutdown(runtime)


_KEEP_ALIVE: list[Any] = []


def _object(window: QQuickWindow, name: str) -> QObject:
    """Find a live QML object that is not an item (a menu, a menu entry) below the window."""
    pending = [window.contentItem()]
    while pending:
        item = pending.pop()
        candidates = item.findChildren(QObject, name)
        # PySide drops the wrappers of the children with the wrapper of their parent.
        _KEEP_ALIVE.extend([item, candidates])
        for found in candidates:
            if shiboken6.isValid(found):
                return found
        pending.extend(item.childItems())
    raise AssertionError(f"no QML object named {name}")


def _menu(window: QQuickWindow) -> QObject:
    """Return the track context menu of the open list."""
    return _object(window, "trackContextMenu")


def _open_menu_labels(window: QQuickWindow, row_number: int) -> list[str]:
    """Right-click a row and return the visible entries of the menu, then close it."""
    row = cast(QQuickItem, _find(window, f"trackRow_{row_number}"))
    QTest.mouseClick(
        window,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
        row.mapToScene(row.boundingRect().center()).toPoint(),
    )
    QTest.qWait(100)
    content = cast(QQuickItem, _menu(window).property("contentItem"))
    # The children of the list are in creation order: the position gives the order of the menu.
    entries = sorted(content.childItems()[0].childItems(), key=lambda item: item.y())
    labels = [
        str(item.property("text"))
        for item in entries
        if item.property("text") and item.isVisible() and item.height() > 0
    ]
    QTest.keyClick(window, Qt.Key.Key_Escape)
    QTest.qWait(50)
    return labels


def test_a_plugin_column_is_in_the_picker_and_saved_like_the_others(qapp, tmp_path: Path) -> None:
    runtime, _module = _start(tmp_path)
    try:
        workspace = _workspace(runtime)
        options = _plugin_ui(workspace).property("columnOptions")
        assert options == [
            {"key": "ui_probe.status", "label": "Probe status", "plugin": "UI probe", "width": 112}
        ]
        ui = _plugin_ui(workspace)
        key = "ui_probe.status"
        # In a plugin list the column starts visible; in a local playlist it starts hidden.
        assert key not in ui.hiddenColumns(LIST_KIND, ui.tabColumns(LIST_KIND, 0))
        playlist_layout = {"order": ["title"], "hidden": [], "widths": {}}
        assert key in ui.hiddenColumns("playlist", playlist_layout)
        shown = ui.toggledColumns("playlist", playlist_layout, key)
        assert key not in ui.hiddenColumns("playlist", shown)
        assert key in shown["order"]
        hidden = ui.toggledColumns(LIST_KIND, ui.tabColumns(LIST_KIND, 0), key)
        ui.setTabColumns(LIST_KIND, hidden)
        assert key in ui.tabColumns(LIST_KIND, 1)["hidden"]
        workspace.resizeColumn(f"{LIST_KIND}:alpha", key, 140)
        assert ui.tabColumns(LIST_KIND, 2)["widths"][key] == 140
        saved = SettingsRepository(runtime.database).get_json(f"tabs.columns.{LIST_KIND}")
        assert saved["widths"][key] == 140
    finally:
        _shutdown(runtime)


def test_the_plugin_column_is_in_the_open_picker_menu(qapp, tmp_path: Path) -> None:
    runtime, _module = _start(tmp_path)
    try:
        add_folder_tracks(runtime, tmp_path / "audio", 1)
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.openPluginTab(LIST_KIND, "alpha")
        _settle(runtime)
        _click(window, cast(QQuickItem, _find(window, "chooseColumnsButton")))
        QTest.qWait(80)
        item = _object(window, "columnOption_ui_probe.status")
        assert item.property("text") == "Probe status"
        assert item.property("hint") == "UI probe plugin"
        assert item.property("checked") is True
    finally:
        _shutdown(runtime)


def test_a_plugin_settings_page_follows_the_plugins_tab_before_about(qapp, tmp_path: Path) -> None:
    runtime, _module = _start(tmp_path)
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.openSettings()
        _settle(runtime)
        keys = ["plugins", "plugin:ui_probe.accounts", "about"]
        tabs = [_find(window, f"settingsTab_{key}") for key in keys]
        assert all(tab is not None for tab in tabs)
        xs = [
            cast(QQuickItem, tab).mapToScene(cast(QQuickItem, tab).position()).x() for tab in tabs
        ]
        assert xs == sorted(xs)
        workspace.setSettingsPage("plugin:ui_probe.accounts")
        _settle(runtime)
        assert "hello from the backend" in _texts(window)
        # The running plugin shows as Running.
        workspace.setSettingsPage("plugins")
        _settle(runtime)
        assert "Running" in _texts(window)
    finally:
        _shutdown(runtime)


def test_a_failing_plugin_is_shown_failed_with_its_error(qapp, tmp_path: Path) -> None:
    data = tmp_path / "data"
    plugins = tmp_path / "plugins"
    package = write_ui_plugin(plugins)
    (package / "__init__.py").write_text(
        "def create(context):\n    raise RuntimeError('no network library')\n", encoding="utf-8"
    )
    paths = resolve_app_paths(data).ensure()
    database = Database(paths.database_path)
    database.migrate()
    PluginPreferences(SettingsRepository(database)).set_enabled(PLUGIN_ID, True)
    database.close()
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application,
        AppOptions(data_dir=data, demo=False, scenario="explorer", plugin_dirs=(plugins,)),
    )
    assert runtime is not None
    try:
        workspace = _workspace(runtime)
        window = _window(runtime)
        workspace.openSettings()
        workspace.setSettingsPage("plugins")
        _settle(runtime)
        texts = _texts(window)
        assert "Failed" in texts
        assert any("no network library" in text and "kept running" in text for text in texts)
        assert _find(window, "activity-ui_probe.main") is None
        # The switch of a failed plugin stays on: it is the user's choice.
        assert cast(QQuickItem, _find(window, "pluginSwitch")).property("checked") is True
    finally:
        _shutdown(runtime)

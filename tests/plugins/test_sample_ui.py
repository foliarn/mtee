"""The sample plugin in the real window (plan 121.7), started as ``--plugin-dir tests/plugins``.

These tests drive the real ``Main.qml`` offscreen, which is the closest to starting MTEE by
hand that a test can get: no Plugins page without a folder, the sample listed and switched on
and off in Settings > Plugins across restarts, every contribution drawn while it runs and gone
once it is off, and the failing sample shown as Failed while the application keeps running.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.helpers.ui_plugin import (
    click,
    find_child,
    find_item,
    need_item,
    plugin_module,
    plugin_ui_of,
    settle,
    start_app,
    visible_texts,
    window_of,
    workspace_of,
)
from tests.plugins.test_contract import FAILING, SAMPLE
from tests.ui.track_list_fixtures import add_folder_tracks

from mtee.app import _Runtime, _shutdown
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.loader import PluginPreferences

FOLDER = SAMPLE.folder  # what --plugin-dir tests/plugins gives
SAMPLE_ID = SAMPLE.plugin_id
SAMPLE_KIND = "sample.list"
SAMPLE_PAGE = f"plugin:{SAMPLE_ID}.settings"
ACTIVITY = f"activity-{SAMPLE_ID}.main"


def _open_plugins_page(runtime: _Runtime) -> QQuickWindow:
    workspace = workspace_of(runtime)
    workspace.openSettings()
    workspace.setSettingsPage("plugins")
    settle(runtime)
    return window_of(runtime)


def _switch(window: QQuickWindow, plugin_id: str) -> QQuickItem:
    row = need_item(window, f"pluginRow_{plugin_id}")
    return cast(QQuickItem, find_child(row, "pluginSwitch"))


def _row_status(window: QQuickWindow, plugin_id: str) -> str:
    row = need_item(window, f"pluginRow_{plugin_id}")
    return str(cast(QQuickItem, find_child(row, "pluginStatus")).property("text"))


def _flip_and_restart(runtime: _Runtime, data: Path, plugin_id: str) -> _Runtime:
    """Click the switch of a plugin in Settings > Plugins, quit, and start MTEE again."""
    window = _open_plugins_page(runtime)
    before = PluginPreferences(SettingsRepository(runtime.database)).is_enabled(plugin_id)
    click(window, _switch(window, plugin_id))
    settle(runtime)
    saved = PluginPreferences(SettingsRepository(runtime.database)).is_enabled(plugin_id)
    assert saved is not before  # the switch was saved
    _shutdown(runtime)
    return start_app(data, (FOLDER,))


def _contributions_are_drawn(window: QQuickWindow, workspace: Any) -> bool:
    ui = plugin_ui_of(workspace)
    return bool(
        find_item(window, ACTIVITY) is not None
        and ui.property("settingsPages")
        and ui.property("columnOptions")
        and ui.is_plugin_kind(SAMPLE_KIND)
        and find_item(window, f"settingsTab_{SAMPLE_PAGE}") is not None
    )


def test_there_is_no_plugins_page_without_a_plugin_folder(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.openSettings()
        settle(runtime)
        assert find_item(window, "settingsTab_plugins") is None
        assert find_item(window, f"settingsTab_{SAMPLE_PAGE}") is None
        assert find_item(window, "settingsTab_about") is not None
        assert find_item(window, ACTIVITY) is None
        assert plugin_ui_of(workspace).property("active") is False
        assert plugin_module(SAMPLE_ID) is None
    finally:
        _shutdown(runtime)


def test_the_sample_is_listed_in_settings_plugins_before_it_is_enabled(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,))
    try:
        window = _open_plugins_page(runtime)
        texts = visible_texts(window)
        assert "Sample plugin" in texts and "v0.1.0" in texts
        assert "Sample plugin (fails)" in texts
        assert _row_status(window, SAMPLE_ID) == "Disabled"
        assert _row_status(window, FAILING.plugin_id) == "Disabled"
        assert "2 plugins found" in texts
        # Listed from its manifest alone: the code of the plugin was not imported.
        assert plugin_module(SAMPLE_ID) is None and plugin_module(FAILING.plugin_id) is None
        assert find_item(window, ACTIVITY) is None
        assert find_item(window, f"settingsTab_{SAMPLE_PAGE}") is None
    finally:
        _shutdown(runtime)


def test_the_switch_adds_and_removes_the_contributions_after_a_restart(
    qapp, tmp_path: Path
) -> None:
    data = tmp_path / "data"
    runtime = start_app(data, (FOLDER,))
    try:
        # Off at the start. Switch on: saved at once, but nothing runs until the next start.
        window = _open_plugins_page(runtime)
        click(window, _switch(window, SAMPLE_ID))
        settle(runtime)
        assert _row_status(window, SAMPLE_ID) == "Disabled"
        assert any("next time MTEE starts" in text for text in visible_texts(window))
        _shutdown(runtime)

        # Restart: running, with every contribution drawn.
        runtime = start_app(data, (FOLDER,))
        window = _open_plugins_page(runtime)
        assert _row_status(window, SAMPLE_ID) == "Running"
        assert plugin_module(SAMPLE_ID) is not None
        assert _contributions_are_drawn(window, workspace_of(runtime))

        # Switch off, restart: everything is gone and the code is not imported again.
        runtime = _flip_and_restart(runtime, data, SAMPLE_ID)
        window = _open_plugins_page(runtime)
        assert _row_status(window, SAMPLE_ID) == "Disabled"
        assert plugin_module(SAMPLE_ID) is None
        workspace = workspace_of(runtime)
        ui = plugin_ui_of(workspace)
        assert ui.property("active") is False
        assert ui.property("activities") == [] and ui.property("settingsPages") == []
        assert ui.property("columnOptions") == [] and not ui.is_plugin_kind(SAMPLE_KIND)
        assert find_item(window, ACTIVITY) is None
        assert find_item(window, f"settingsTab_{SAMPLE_PAGE}") is None
        assert find_item(window, "settingsTab_plugins") is not None  # the folder is still set
    finally:
        _shutdown(runtime)


def test_an_enabled_sample_draws_its_section_tab_column_actions_and_page(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        add_folder_tracks(runtime, tmp_path / "audio", 2)
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        settle(runtime)
        module = plugin_module(SAMPLE_ID)
        assert module is not None
        assert "startup" in module.EVENTS  # the StartupTask ran as a job

        # The activity, its pane action, its section and its foot.
        click(window, need_item(window, ACTIVITY))
        settle(runtime)
        texts = visible_texts(window)
        assert "All samples" in texts and "Missing only" in texts
        assert "Sample is connected" in texts
        click(window, need_item(window, "pluginPaneAction_refresh"))
        assert module.EVENTS[-1] == "refresh"

        # A row of the section opens the tab; the track list has an unavailable row.
        click(window, need_item(window, "pluginRow_all"))
        settle(runtime)
        source = f"{SAMPLE_KIND}:all"
        model = workspace._active_track_model(source)
        assert model is not None
        rows = model.rows_snapshot()
        assert [row["id"] for row in rows] == ["one", "two", "three"]
        assert [row["available"] for row in rows] == [True, False, False]
        assert rows[1]["plugin"][f"{SAMPLE_ID}.status"]["text"] == "Missing"

        # The column, the header and the tab actions.
        texts = visible_texts(window)
        assert "Sample status" in texts and "Missing" in texts and "Local" in texts
        assert "Sample list" in texts and "Fetch missing (2)" in texts and "Watch" in texts
        click(window, need_item(window, f"pluginHeaderAction_{SAMPLE_ID}.fetch_all"))
        assert module.EVENTS[-1] == "fetch_all all"
        click(window, need_item(window, f"pluginHeaderAction_{SAMPLE_ID}.watch"))
        assert module.EVENTS[-1] == "watch"
        missing = need_item(window, "trackRow_2")
        click(window, cast(QQuickItem, find_child(missing, "trackRowAction")))
        assert module.EVENTS[-1] == "fetch two"

        # The track action is offered for rows without a file only.
        offered = workspace.pluginTrackActions(source, ["two"])
        assert [item["label"] for item in offered] == ["Sample", "Mark as wanted"]
        assert workspace.pluginTrackActions(source, ["one"]) == []
        workspace.runPluginTrackAction(source, ["two", "three"], f"{SAMPLE_ID}.mark")
        assert module.EVENTS[-1] == "mark two,three"

    finally:
        _shutdown(runtime)


def test_the_sample_settings_page_uses_the_shared_rows_and_saves_its_values(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.openSettings()
        workspace.setSettingsPage(SAMPLE_PAGE)
        settle(runtime)
        texts = visible_texts(window)
        for expected in (
            "Sample plugin",
            "Label",
            "Loud mode",
            "Copies",
            "Account",
            "Not signed in.",
        ):
            assert expected in texts
        assert "3" in texts  # the migration seeded three rows into sample_items
        assert (
            find_item(window, "sampleNotice") is None
            or not need_item(window, "sampleNotice").isVisible()
        )

        # Field row: type and press Enter.
        field = cast(QQuickItem, find_child(need_item(window, "sampleLabel"), "field_sampleLabel"))
        click(window, field)
        for character in "mine":
            QTest.keyClick(window, Qt.Key(ord(character.upper())))
        QTest.keyClick(window, Qt.Key.Key_Return)
        # Toggle row, stepper row and action row.
        click(
            window,
            cast(QQuickItem, find_child(need_item(window, "sampleLoud"), "toggle_sampleLoud")),
        )
        click(window, cast(QQuickItem, find_child(need_item(window, "sampleCopies"), "stepUp")))
        click(window, need_item(window, "action_sampleSignIn"))
        settle(runtime)

        stored = SettingsRepository(runtime.database)
        assert stored.get("plugins.sample.label") == "mine"
        assert stored.get_json("plugins.sample.loud") is True
        assert stored.get_json("plugins.sample.copies") == 2
        assert stored.get_json("plugins.sample.signed_in") is True
        texts = visible_texts(window)
        assert "KQ4-7ZPM" in texts  # the code badge
        assert "Sign out" in texts
        assert need_item(window, "sampleNotice").isVisible()
    finally:
        _shutdown(runtime)


def test_the_failing_sample_is_shown_failed_and_mtee_keeps_running(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID, FAILING.plugin_id))
    try:
        workspace = workspace_of(runtime)
        window = _open_plugins_page(runtime)
        assert _row_status(window, FAILING.plugin_id) == "Failed"
        error = cast(
            QQuickItem, find_child(need_item(window, "pluginRow_sample_failing"), "pluginError")
        )
        assert "The sample plugin was made to fail." in str(error.property("text"))
        # The notice names the plugin; the application and the other plugin work.
        assert "Sample plugin (fails)" in str(cast(Any, workspace).message)
        assert _row_status(window, SAMPLE_ID) == "Running"
        assert _contributions_are_drawn(window, workspace)
        assert plugin_module(FAILING.plugin_id) is None
        # The switch of a failed plugin stays on: it is the user's choice.
        assert _switch(window, FAILING.plugin_id).property("checked") is True
        workspace.setActivity("explorer")
        settle(runtime)
    finally:
        _shutdown(runtime)

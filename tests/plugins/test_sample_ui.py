"""The sample plugin in the real window (plan 121.7), started as ``--plugin-dir tests/plugins``.

These tests drive the real ``Main.qml`` offscreen, which is the closest to starting MTEE by
hand that a test can get: no Plugins page without a folder, the sample listed and switched on
and off in the Plugins view across restarts, every contribution drawn while it runs and gone
once it is off, and the failing sample shown as Failed while the application keeps running.
The rows and the switches are read from ``workspace.pluginsView``, the model of the Plugins view.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QPointF, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.helpers.ui_plugin import (
    click,
    find_child,
    find_item,
    find_items,
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


def _view(runtime: _Runtime) -> Any:
    """The model of the Plugins view: its rows and its switches."""
    return cast(Any, workspace_of(runtime)).pluginsView


def _row(runtime: _Runtime, plugin_id: str) -> dict[str, Any]:
    return next(row for row in _view(runtime).property("installed") if row["id"] == plugin_id)


def _row_status(runtime: _Runtime, plugin_id: str) -> str:
    return str(_row(runtime, plugin_id)["statusText"])


def _set_switch(runtime: _Runtime, plugin_id: str, on: bool) -> None:
    _view(runtime).setEnabled(plugin_id, on)
    settle(runtime)


def _flip_and_restart(runtime: _Runtime, data: Path, plugin_id: str) -> _Runtime:
    """Switch a plugin in the Plugins view, quit, and start MTEE again."""
    before = PluginPreferences(SettingsRepository(runtime.database)).is_enabled(plugin_id)
    _set_switch(runtime, plugin_id, not before)
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
    )


def test_there_is_no_plugins_page_without_a_plugin_folder(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.openSettings()
        settle(runtime)
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
        window = window_of(runtime)
        sample = _row(runtime, SAMPLE_ID)
        assert sample["title"] == "Sample plugin" and sample["version"] == "0.1.0"
        assert _row(runtime, FAILING.plugin_id)["title"] == "Sample plugin (fails)"
        assert _row_status(runtime, SAMPLE_ID) == "Disabled"
        assert _row_status(runtime, FAILING.plugin_id) == "Disabled"
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
        _set_switch(runtime, SAMPLE_ID, True)
        assert _row_status(runtime, SAMPLE_ID) == "Restart needed"
        _shutdown(runtime)

        # Restart: running, with every contribution drawn.
        runtime = start_app(data, (FOLDER,))
        window = window_of(runtime)
        assert _row_status(runtime, SAMPLE_ID) == "Running"
        assert plugin_module(SAMPLE_ID) is not None
        assert _contributions_are_drawn(window, workspace_of(runtime))

        # Switch off, restart: everything is gone and the code is not imported again.
        runtime = _flip_and_restart(runtime, data, SAMPLE_ID)
        window = window_of(runtime)
        assert _row_status(runtime, SAMPLE_ID) == "Disabled"
        assert plugin_module(SAMPLE_ID) is None
        workspace = workspace_of(runtime)
        ui = plugin_ui_of(workspace)
        assert ui.property("active") is False
        assert ui.property("activities") == [] and ui.property("settingsPages") == []
        assert ui.property("columnOptions") == [] and not ui.is_plugin_kind(SAMPLE_KIND)
        assert find_item(window, ACTIVITY) is None
        assert find_item(window, f"settingsTab_{SAMPLE_PAGE}") is None
        assert _row(runtime, SAMPLE_ID)["statusText"] == "Disabled"  # the plugin is still found
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
        window = window_of(runtime)
        assert _row_status(runtime, FAILING.plugin_id) == "Failed"
        error = str(_row(runtime, FAILING.plugin_id)["error"])
        assert "The sample plugin was made to fail." in error
        # The notice names the plugin; the application and the other plugin work.
        assert "Sample plugin (fails)" in str(cast(Any, workspace).message)
        assert _row_status(runtime, SAMPLE_ID) == "Running"
        assert _contributions_are_drawn(window, workspace)
        assert plugin_module(FAILING.plugin_id) is None
        # The switch of a failed plugin stays on: it is the user's choice.
        assert _row(runtime, FAILING.plugin_id)["enabled"] is True
        workspace.setActivity("explorer")
        settle(runtime)
    finally:
        _shutdown(runtime)


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)


def test_the_sample_uses_the_optional_capabilities_of_the_plugin_interface(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        module = plugin_module(SAMPLE_ID)
        assert module is not None
        settle(runtime)
        # run_on_gui: the startup job ran on a worker and handed its last step to the GUI.
        assert "startup" in module.EVENTS and "gui" in module.EVENTS

        # The scan hook: adding a library folder scans it, and the plugin hears about it.
        audio = tmp_path / "audio"
        audio.mkdir()
        for name in ("one.wav", "two.wav"):
            _write_wav(audio / name)
        assert workspace.addRoot(str(audio))
        settle(runtime)
        assert module.EVENTS.count("scanned audio") == 1

        # import_file: a new file lands in a folder of the library and is picked up by the
        # rescan the plugin asks for; a second import never replaces the first.
        click(window, need_item(window, ACTIVITY))
        settle(runtime)
        click(window, need_item(window, "pluginPaneAction_import"))
        settle(runtime)
        first = audio / "Imported" / "imported.wav"
        assert "imported imported.wav" in module.EVENTS
        assert first.is_file()
        taken = first.read_bytes()
        assert module.EVENTS.count("scanned audio") == 2  # the plugin's own rescan finished
        click(window, need_item(window, "pluginPaneAction_import"))
        settle(runtime)
        assert "imported imported (2).wav" in module.EVENTS
        assert (audio / "Imported" / "imported (2).wav").is_file()
        assert first.read_bytes() == taken

        # PlaylistAccess.name and .exists.
        click(window, need_item(window, "pluginPaneAction_playlist"))
        settle(runtime)
        assert "playlist Sample playlist True None False" in module.EVENTS
    finally:
        _shutdown(runtime)


def _inside(item: QQuickItem, name: str) -> bool:
    """Whether ``item`` is a descendant of the item named ``name``."""
    parent = item.parentItem()
    while parent is not None:
        if parent.objectName() == name:
            return True
        parent = parent.parentItem()
    return False


def _texts_under(item: QQuickItem) -> list[str]:
    found: list[str] = []
    pending = [item]
    while pending:
        current = pending.pop()
        text = current.property("text")
        if isinstance(text, str) and current.isVisible():
            found.append(text)
        pending.extend(current.childItems())
    return found


def _rows_in(window: QQuickWindow, place: str) -> list[QQuickItem]:
    return [item for item in find_items(window, "taskChoiceRow") if _inside(item, place)]


def _button_of(row: QQuickItem, name: str) -> QQuickItem:
    return cast(QQuickItem, find_child(row, name))


def test_the_sample_waiting_items_are_drawn_in_the_tasks_pane_and_page(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        module = plugin_module(SAMPLE_ID)
        assert module is not None
        settle(runtime)

        # The pane: a titled group with a count, a row per item, the label the plugin gave
        # (or "Open"), and the count in the badge of the Tasks activity.
        workspace.setActivity("tasks")
        settle(runtime)
        group = [item for item in find_items(window, "waitingGroup") if _inside(item, "tasksPane")]
        assert len(group) == 1 and group[0].isVisible()
        texts = visible_texts(window)
        assert "Waiting for you (2)" in texts
        assert "Two Step Theory" in texts and "Skank Rhythm" in texts
        assert "Pick a match: 2 candidates." in texts
        assert "No background tasks in this session." not in texts
        rows = _rows_in(window, "tasksPane")
        assert len(rows) == 2
        labels = sorted(str(_button_of(row, "answerWaiting").property("text")) for row in rows)
        assert labels == ["Open", "Pick…"]
        assert "2" in _texts_under(need_item(window, "activity-tasks"))

        # The primary button asks the plugin, which names the tab to open.
        pick = next(
            row for row in rows if _button_of(row, "answerWaiting").property("text") == "Pick…"
        )
        click(window, _button_of(pick, "answerWaiting"))
        settle(runtime)
        assert "pick w1" in module.EVENTS
        active = cast(Any, workspace).activeTabId
        assert active == f"{SAMPLE_KIND}:missing"

        # The page lists the same items as cards; the cross dismisses through the plugin.
        workspace.openTasks()
        settle(runtime)
        page_rows = _rows_in(window, "tasksView")
        assert len(page_rows) == 2
        cross = next(
            _button_of(row, "dismissWaiting")
            for row in page_rows
            if "Skank Rhythm" in _texts_under(row)
        )
        click(window, cross)
        settle(runtime)
        assert "dismiss w2" in module.EVENTS
        assert len(_rows_in(window, "tasksView")) == 1 and len(_rows_in(window, "tasksPane")) == 1
        assert "Waiting for you (1)" in visible_texts(window)
        assert "1" in _texts_under(need_item(window, "activity-tasks"))

        # Nothing left: the group is hidden and the empty message comes back.
        last = _rows_in(window, "tasksPane")[0]
        click(window, _button_of(last, "dismissWaiting"))
        settle(runtime)
        assert "dismiss w1" in module.EVENTS
        assert not any(item.isVisible() for item in find_items(window, "waitingGroup"))
        texts = visible_texts(window)
        assert "No background tasks in this session." in texts
        assert not any(text.startswith("Waiting for you") for text in texts)
        assert "1" not in _texts_under(need_item(window, "activity-tasks"))
    finally:
        _shutdown(runtime)


def test_a_sample_that_is_off_shows_no_waiting_group(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.setActivity("tasks")
        workspace.openTasks()
        settle(runtime)
        assert not any(item.isVisible() for item in find_items(window, "waitingGroup"))
        assert find_items(window, "taskChoiceRow") == []
        assert not any(text.startswith("Waiting for you") for text in visible_texts(window))
    finally:
        _shutdown(runtime)


def test_the_sample_opens_its_dialog_in_a_core_popup_and_closes_it(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        click(window, need_item(window, ACTIVITY))
        settle(runtime)
        assert find_item(window, "sampleDialog") is None

        # The pane action asks the core; the popup loads the plugin file with the given ref.
        click(window, need_item(window, "pluginPaneAction_note"))
        settle(runtime)
        title = need_item(window, "sampleDialogTitle")
        assert title.property("text") == "Sample dialog: from the pane"
        assert title.isVisible()

        # The plugin file closes the popup through the ``dialog`` the core gave it.
        click(window, need_item(window, "sampleDialogClose"))
        settle(runtime)
        assert find_item(window, "sampleDialog") is None
    finally:
        _shutdown(runtime)


def _menu_entry(window: QQuickWindow, name: str) -> dict[str, Any] | None:
    """The ``text`` and ``hint`` of a menu entry (a QObject, not an item) below the window.

    The properties are read here: the wrapper of an entry is gone once the helper returns.
    """
    pending: list[QQuickItem] = [window.contentItem()]
    while pending:
        item = pending.pop()
        found = item.findChildren(QObject, name)
        if found:
            entry = found[0]
            return {"text": entry.property("text"), "hint": entry.property("hint")}
        pending.extend(item.childItems())
    return None


def test_the_column_picker_names_the_sample_plugin_once(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        add_folder_tracks(runtime, tmp_path / "audio", 2)
        window = window_of(runtime)
        settle(runtime)
        click(window, need_item(window, ACTIVITY))
        settle(runtime)
        click(window, need_item(window, "pluginRow_all"))
        settle(runtime)

        click(window, need_item(window, "chooseColumnsButton"))
        QTest.qWait(80)
        entry = _menu_entry(window, f"columnOption_{SAMPLE_ID}.status")
        assert entry is not None, "the sample column is not in the open picker"
        assert entry["text"] == "Sample status"
        # The title already ends with "plugin": it is shown once, not as "Sample plugin plugin".
        assert entry["hint"] == "Sample plugin"
        QTest.keyClick(window, Qt.Key.Key_Escape)
    finally:
        _shutdown(runtime)


# ------------------------------------------- the sidebar fields: text, counts, fold, warning


def _drawn(item: QQuickItem | None) -> bool:
    """Whether an item and every parent of it is visible, as the eye sees it."""
    current = item
    while current is not None:
        if not current.isVisible():
            return False
        current = current.parentItem()
    return item is not None


def _click_at(window: QQuickWindow, item: QQuickItem, x: float, y: float) -> None:
    """Click a point given in the item's own coordinates, with the left mouse button."""
    point = item.mapToScene(QPointF(x, y)).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    QTest.qWait(30)


def _text_of(item: QQuickItem) -> str:
    """The text of an item, or of its first child that has one."""
    if isinstance(item.property("text"), str):
        return str(item.property("text"))
    return next(
        str(child.property("text")) for child in item.childItems() if child.property("text")
    )


def test_a_text_action_is_drawn_with_its_label_and_hidden_until_the_library_has_tracks(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        click(window, need_item(window, ACTIVITY))
        settle(runtime)
        # An empty library: the Import text button is not drawn, nor its icon-button twin.
        assert not _drawn(find_item(window, "pluginPaneLabelAction_import"))
        assert not _drawn(find_item(window, "pluginPaneAction_import"))
        assert _drawn(find_item(window, "pluginPaneAction_refresh"))

        # Once the library has tracks, the plugin asks for its counts again (its Refresh button).
        add_folder_tracks(runtime, tmp_path / "audio", 2)
        click(window, need_item(window, "pluginPaneAction_refresh"))
        settle(runtime)
        text_button = find_item(window, "pluginPaneLabelAction_import")
        assert _drawn(text_button)
        assert text_button is not None and text_button.property("text") == "Import"
        assert not _drawn(find_item(window, "pluginPaneAction_import"))
    finally:
        _shutdown(runtime)


def test_the_sample_draws_its_section_count_activity_badge_and_warning_row(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        click(window, need_item(window, ACTIVITY))
        settle(runtime)

        # The activity badge is the number of waiting rows (two in the sample).
        assert need_item(window, ACTIVITY).property("badge") == 2

        # The section count is the number of items without a local file.
        missing = (
            runtime.database.connection()
            .execute("SELECT COUNT(*) FROM sample_items WHERE state = 'missing'")
            .fetchone()[0]
        )
        count = need_item(window, f"pluginSectionCount_{SAMPLE_ID}.lists")
        assert _drawn(count)
        assert _text_of(count) == str(missing)

        # A warning row: its name is drawn in the warning colour (Theme.warning, #FFB020).
        broken = need_item(window, "pluginRow_broken")
        name = next(
            child for child in broken.childItems() if child.property("text") == "Broken sample"
        )
        assert name.property("color").name().upper() == "#FFB020"
        assert _drawn(name)
    finally:
        _shutdown(runtime)


def test_a_group_name_click_activates_and_its_chevron_only_folds(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        module = plugin_module(SAMPLE_ID)
        assert module is not None
        click(window, need_item(window, ACTIVITY))
        settle(runtime)
        group = need_item(window, "pluginRow_group")

        # The name of the group calls activate; no tab opens for it.
        name = next(child for child in group.childItems() if child.property("text") == "Groups")
        name_x = name.x() + 2
        _click_at(window, group, name_x, group.height() / 2)
        settle(runtime)
        assert module.EVENTS[-1] == "activate group"
        assert _drawn(find_item(window, "pluginRow_missing"))

        # The chevron folds the group and tells the plugin; the child row goes away.
        _click_at(window, group, 10, group.height() / 2)
        settle(runtime)
        assert module.EVENTS[-1] == "fold group folded"
        assert module.EVENTS[-2] == "activate group"
        assert not _drawn(find_item(window, "pluginRow_missing"))
    finally:
        _shutdown(runtime)


def test_a_section_that_starts_collapsed_is_drawn_folded_until_its_header_is_clicked(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), (SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        click(window, need_item(window, ACTIVITY))
        settle(runtime)

        assert "SAMPLE ARCHIVE" in [text.upper() for text in visible_texts(window)]
        assert find_item(window, "pluginRow_old") is None

        section = need_item(window, f"pluginSection_{SAMPLE_ID}.archive")
        header = section.childItems()[0]
        _click_at(window, header, 60, header.height() / 2)
        settle(runtime)
        assert _drawn(find_item(window, "pluginRow_old"))
    finally:
        _shutdown(runtime)

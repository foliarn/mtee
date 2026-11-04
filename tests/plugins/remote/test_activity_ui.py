"""The Remote activity and Explorer > Server in the real window (plan 126.9).

Started with ``--plugin-dir plugins`` and the remote plugin switched on, as Settings > Plugins
would leave it. Nothing is connected, so the sections show their empty states.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtQuick import QQuickItem
from tests.helpers.ui_plugin import (
    click,
    find_item,
    need_item,
    settle,
    start_app,
    visible_texts,
    window_of,
    workspace_of,
)
from tests.plugins.remote.conftest import PLUGIN_DIR

from mtee.app import _shutdown
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.context import SETTINGS_PREFIX
from mtee.services.app_paths import resolve_app_paths

ACTIVITY = "activity-remote.remote"
SECTIONS = ("changes", "conflicts", "backups", "log")


def _drawn(item: QQuickItem | None) -> bool:
    """Whether an item and every parent of it is visible, as the eye sees it."""
    current = item
    while current is not None:
        if not current.isVisible():
            return False
        current = current.parentItem()
    return item is not None


def _set_sync_mode(data_dir: Path, mode: str) -> None:
    """Save the sync mode of the Remote plugin, as its Settings page would, before the start."""
    paths = resolve_app_paths(data_dir).ensure()
    database = Database(paths.database_path)
    database.migrate()
    SettingsRepository(database).set(f"{SETTINGS_PREFIX}.remote.sync_mode", mode)
    database.close()


def test_the_remote_activity_button_draws_its_sections(qapp: object, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        window = window_of(runtime)
        settle(runtime)
        click(window, need_item(window, ACTIVITY))
        settle(runtime)

        texts = visible_texts(window)
        for title in ("CHANGES", "CONFLICTS", "BACKUPS", "ACTIVITY LOG"):
            assert title in texts, title
        for section in SECTIONS:
            assert find_item(window, f"pluginSection_remote.{section}") is not None, section
        assert "Everything is up to date" in texts
        # The foot of the tool window says where the sync stands (the header icon only on hover).
        assert "Not connected." in texts
        assert "Connect in Settings > Remote." in texts
        assert find_item(window, "pluginPaneAction_sync") is not None
        assert find_item(window, "pluginPaneAction_fetch") is not None
        # Auto is the default: Apply is not drawn, and the empty sections show no count.
        assert not _drawn(find_item(window, "pluginSectionLabelAction_apply"))
        assert not _drawn(find_item(window, "pluginSectionCount_remote.changes"))
        assert not _drawn(find_item(window, "pluginSectionCount_remote.conflicts"))
    finally:
        _shutdown(runtime)


def test_apply_is_a_text_button_in_manual_mode(qapp: object, tmp_path: Path) -> None:
    _set_sync_mode(tmp_path / "data", "manual")
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        window = window_of(runtime)
        settle(runtime)
        click(window, need_item(window, ACTIVITY))
        settle(runtime)

        apply = find_item(window, "pluginSectionLabelAction_apply")
        assert _drawn(apply)
        assert apply is not None and apply.property("text") == "Apply"
        assert not _drawn(find_item(window, "pluginSectionAction_apply"))
    finally:
        _shutdown(runtime)


def test_the_server_section_is_drawn_under_the_explorer(qapp: object, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.setActivity("explorer")
        settle(runtime)

        assert find_item(window, "pluginSection_remote.server") is not None
        assert "SERVER" in visible_texts(window)
    finally:
        _shutdown(runtime)

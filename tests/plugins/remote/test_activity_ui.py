"""The Remote activity and Explorer > Server in the real window (plan 126.9).

Started with ``--plugin-dir plugins`` and the remote plugin switched on, as Settings > Plugins
would leave it. Nothing is connected, so the sections show their empty states.
"""

from __future__ import annotations

from pathlib import Path

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

ACTIVITY = "activity-remote.remote"
SECTIONS = ("changes", "conflicts", "backups", "log")


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
        assert find_item(window, "pluginPaneAction_sync") is not None
        assert find_item(window, "pluginPaneAction_fetch") is not None
        assert find_item(window, "pluginSectionAction_apply") is not None
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

"""The status bar under the player bar (plan 125.5), in the live window.

With the sample plugin the strip shows its item and a click runs the sample's action. Without a
plugin the strip is not drawn and the body of the window keeps the whole height, as before.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

from PySide6.QtQuick import QQuickItem
from tests.helpers.ui_plugin import (
    click,
    find_items,
    need_item,
    settle,
    start_app,
    window_of,
    workspace_of,
)
from tests.plugins.test_contract import SAMPLE

from mtee.app import _shutdown

FOLDER = SAMPLE.folder  # what --plugin-dir tests/plugins gives
SAMPLE_ID = SAMPLE.plugin_id
STRIP_HEIGHT = 24


def _sample_events() -> list[str]:
    return cast(list[str], sys.modules[f"mtee.plugins.{SAMPLE_ID}"].EVENTS)


def _body_bottom_gap(window: Any) -> float:
    """The gap between the bottom of the body and the bottom of the window."""
    body = cast(QQuickItem, need_item(window, "mainBody"))
    content = cast(QQuickItem, window.contentItem())
    return content.height() - (body.y() + body.height())


def test_without_a_plugin_the_strip_is_absent_and_the_body_keeps_the_height(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        window = window_of(runtime)
        settle(runtime)
        strip = need_item(window, "statusBar")
        assert strip.isVisible() is False
        assert cast(Any, workspace_of(runtime)).statusBar.property("count") == 0
        assert find_items(window, "statusItem") == []
        assert _body_bottom_gap(window) == 0  # the body reaches the bottom of the window
    finally:
        _shutdown(runtime)


def test_with_the_sample_the_strip_shows_its_item_under_the_player_bar(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), enabled=(SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        strip = need_item(window, "statusBar")
        assert strip.isVisible() is True
        assert strip.height() == STRIP_HEIGHT
        assert _body_bottom_gap(window) == STRIP_HEIGHT  # the body gives the strip its 24 px
        items = find_items(window, "statusItem")
        assert len(items) == 1
        text = need_item(window, "statusItemText")
        assert text.property("text") == "Sample: ready"
    finally:
        _shutdown(runtime)


def test_a_click_on_the_item_runs_the_plugin_action(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), enabled=(SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        _sample_events().clear()

        click(window, find_items(window, "statusItem")[0])
        settle(runtime)

        assert "status click" in _sample_events()
    finally:
        _shutdown(runtime)

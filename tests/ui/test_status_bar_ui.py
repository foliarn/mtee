"""The plugin status items in the header of the live window (plan 125.5, moved by plan 131.5).

With the sample plugin one icon shows in the header, its text in the tooltip, and a click runs the
sample's action. Without a plugin nothing is drawn there and the body of the window keeps the whole
height, as before. The strip under the player bar is gone.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject
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
HEADER_HEIGHT = 40  # Theme.frameSize


def _sample_events() -> list[str]:
    return cast(list[str], sys.modules[f"mtee.plugins.{SAMPLE_ID}"].EVENTS)


def _body_bottom_gap(window: Any) -> float:
    """The gap between the bottom of the body and the bottom of the window."""
    body = cast(QQuickItem, need_item(window, "mainBody"))
    content = cast(QQuickItem, window.contentItem())
    return content.height() - (body.y() + body.height())


def _tooltip_text(item: QQuickItem) -> str:
    """The text of the hover tip declared inside a status item (a popup, not an item)."""
    for child in cast(list[QObject], item.children()):
        if child.objectName() == "statusItemText":
            return str(child.property("text"))
    return ""


def test_without_a_plugin_the_header_has_no_status_item_and_the_body_keeps_the_height(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        window = window_of(runtime)
        settle(runtime)
        assert find_items(window, "statusBar") == []  # the strip under the player is gone
        assert find_items(window, "statusItem") == []
        assert cast(Any, workspace_of(runtime)).statusBar.property("count") == 0
        assert _body_bottom_gap(window) == 92  # the body stops above the player bar (131.8)
    finally:
        _shutdown(runtime)


def test_with_the_sample_the_header_shows_its_icon_and_the_text_in_the_tooltip(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (FOLDER,), enabled=(SAMPLE_ID,))
    try:
        window = window_of(runtime)
        settle(runtime)
        items = find_items(window, "statusItem")
        assert len(items) == 1
        item = items[0]
        assert item.isVisible() is True
        assert item.mapToScene(item.boundingRect().topLeft()).y() < HEADER_HEIGHT
        assert _tooltip_text(item) == "Sample: ready"
        assert _body_bottom_gap(window) == 92  # no strip: only the player bar (131.8)
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

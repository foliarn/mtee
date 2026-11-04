"""Fix 137: a header button that opens a menu closes that menu when clicked again."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_components_130 import _settle
from tests.ui.test_player_views import _find as _find_named
from tests.ui.test_player_views import _UiPlayerBackend

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions


def _click_again(root: QQuickWindow, item: QQuickItem) -> None:
    point = item.mapToScene(item.boundingRect().center())
    pos = QPoint(round(point.x()), round(point.y()))
    QTest.mouseMove(root, pos)
    QTest.mousePress(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)
    QTest.mouseRelease(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)


def test_the_hamburger_menu_closes_when_its_button_is_clicked_while_open(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    try:
        qtbot.waitUntil(lambda: _find_named(root, "hamburgerButton") is not None, timeout=5000)
        button = _find_named(root, "hamburgerButton")
        assert button is not None and button.isVisible()
        menu = cast(Any, root.findChild(QObject, "appMenu"))
        assert menu is not None
        QTest.qWait(450)

        _click_again(root, button)
        _settle(qapp)
        assert menu.property("visible") is True

        # The second click on the same button must close the menu and leave it closed.
        _click_again(root, button)
        _settle(qapp)
        QTest.qWait(300)
        assert menu.property("visible") is False
    finally:
        _shutdown(runtime)
        application.processEvents()

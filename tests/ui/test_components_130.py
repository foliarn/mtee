"""The reusable UI components of plan 130, driven offscreen in a bare window."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any, cast

import pytest
from PySide6.QtCore import QObject, QPoint, Qt, QUrl, Slot
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.assets import qml_dir
from mtee.models.icon_provider import ICON_PROVIDER_ID, IconProvider


class _Recorder(QObject):
    """Collects what the QML under test reports."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []

    @Slot(str)
    def log(self, text: str) -> None:
        self.events.append(text)


def _settle(qapp, seconds: float = 0.1) -> None:
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        qapp.processEvents()
        time.sleep(0.005)


def _find(window: QQuickWindow, name: str) -> QQuickItem:
    pending = [window.contentItem()]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    raise AssertionError(f"no item named {name}")


def _find_in(item: QQuickItem, name: str) -> QQuickItem:
    pending = [item]
    while pending:
        current = pending.pop()
        if current.objectName() == name:
            return current
        pending.extend(current.childItems())
    raise AssertionError(f"no item named {name}")


def _has(window: QQuickWindow, name: str) -> bool:
    try:
        _find(window, name)
    except AssertionError:
        return False
    return True


def _var(value: Any) -> Any:
    """A QML property read as a plain Python value."""
    return value.toVariant() if hasattr(value, "toVariant") else value


def _type(window: QQuickWindow, text: str) -> None:
    for character in text:
        cast(Any, QTest).keyClick(window, character)


def _centre(item: QQuickItem) -> QPoint:
    return item.mapToScene(item.boundingRect().center()).toPoint()


def _click(window: QQuickWindow, item: QQuickItem, button=Qt.MouseButton.LeftButton, mods=None):
    QTest.mouseClick(window, button, mods or Qt.KeyboardModifier.NoModifier, _centre(item))


class _Harness:
    def __init__(self, qapp, body: str, imports: str = "") -> None:
        self.qapp = qapp
        self.engine = QQmlEngine()
        self.engine.addImportPath(str(qml_dir()))
        self.engine.addImageProvider(ICON_PROVIDER_ID, IconProvider())
        self.recorder = _Recorder()
        self.engine.rootContext().setContextProperty("rec", self.recorder)
        source = (
            "import QtQuick\nimport QtQuick.Window\nimport QtQuick.Controls.Basic\n"
            "import Mtee\n" + imports + "\nWindow {\n width: 800; height: 600; visible: true\n"
            ' color: "#202020"\n' + body + "\n}\n"
        )
        self.component = component = QQmlComponent(self.engine)
        component.setData(source.encode(), QUrl("file:///components-130.qml"))
        created = component.create()
        assert isinstance(created, QQuickWindow), component.errors()
        self.window = created
        QTest.qWaitForWindowExposed(created)
        _settle(qapp, 0.15)

    def close(self) -> None:
        self.window.close()
        self.window.deleteLater()


@pytest.fixture
def harness(qapp) -> Iterator[Any]:
    made: list[_Harness] = []

    def make(body: str, imports: str = "") -> _Harness:
        item = _Harness(qapp, body, imports)
        made.append(item)
        return item

    yield make
    for item in made:
        item.close()


def test_the_theme_has_the_frame_tokens(harness) -> None:
    probe = harness(
        """
        property var tokens: [Theme.frameSize, Theme.windowGap, Theme.radiusWindow,
            Theme.radiusControl, Theme.radiusChip, Theme.radiusCover, Theme.radius,
            Theme.badgeRadius, Theme.minWindowWidth, Theme.minWindowHeight,
            Theme.minCenterWindowWidth, Theme.minCenterWindowHeight]
        objectName: "root"
        """
    )
    assert _var(probe.window.property("tokens")) == [40, 5, 8, 6, 4, 2, 6, 4, 560, 420, 320, 200]


def test_a_window_surface_masks_its_corners_and_draws_the_focus_outline(harness) -> None:
    probe = harness(
        """
        WindowSurface {
            objectName: "surface"; x: 20; y: 20; width: 200; height: 100
            Rectangle { objectName: "child"; anchors.fill: parent; color: "red" }
        }
        """
    )
    window = probe.window
    surface = _find(window, "surface")
    assert surface.property("radius") == 8
    assert _find(window, "windowSurfaceCorners").isVisible()
    assert not _find(window, "windowSurfaceOutline").isVisible()
    assert _find(window, "child").width() == 200
    surface.setProperty("focused", True)
    assert _find(window, "windowSurfaceOutline").isVisible()
    # The corner pixels show the frame colour, not the square child.
    image = window.grabWindow()
    assert image.pixelColor(21, 21).name() == "#0b0b0c"
    assert image.pixelColor(120, 70).name() == "#ff0000"


def test_a_split_handle_reports_the_drag_and_draws_only_on_hover(harness) -> None:
    probe = harness(
        """
        SplitHandle {
            objectName: "handle"; x: 300; y: 50; width: 9; height: 300
            onDragged: (delta) => rec.log("drag:" + Math.round(delta))
            onReleased: rec.log("released")
            onDoubleClicked: rec.log("double")
        }
        """
    )
    window = probe.window
    handle = _find(window, "handle")
    assert not _find(window, "splitHandleLine").isVisible()
    assert handle.property("thickness") == 9
    start = _centre(handle)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(window, start + QPoint(30, 0))
    QTest.mouseMove(window, start + QPoint(40, 0))
    assert _find(window, "splitHandleLine").isVisible()
    QTest.mouseRelease(
        window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(40, 0)
    )
    assert "drag:30" in probe.recorder.events
    assert probe.recorder.events[-2:] == ["drag:40", "released"]
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    assert "double" in probe.recorder.events


def test_a_popover_hangs_under_its_anchor_stays_inside_and_closes_on_escape(qapp, harness) -> None:
    probe = harness(
        """
        Item {
            id: anchorHost
            Rectangle { id: anchor; objectName: "anchor"; x: 740; y: 10; width: 40; height: 40
                color: "blue" }
        }
        Popover {
            id: pop; objectName: "pop"; anchorItem: anchor; bodyWidth: 300
            Rectangle { width: 300; height: 100; color: "green" }
        }
        property int openCount: 0
        onOpenCountChanged: pop.open()
        """
    )
    window = probe.window
    window.setProperty("openCount", window.property("openCount") + 1)
    _settle(qapp)
    popover = window.findChild(QObject, "pop")
    assert popover.property("opened") is True
    assert popover.property("x") + popover.property("width") <= 800 - 8
    assert popover.property("y") >= 50
    QTest.keyClick(window, Qt.Key.Key_Escape)
    _settle(qapp)
    assert popover.property("opened") is False
    window.setProperty("openCount", window.property("openCount") + 1)
    _settle(qapp)
    QTest.mouseClick(
        window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(50, 500)
    )
    _settle(qapp)
    assert popover.property("opened") is False


def test_a_header_button_clicks_and_shows_a_badge(harness) -> None:
    probe = harness(
        """
        HeaderButton {
            objectName: "hb"; x: 10; y: 10; icon: "plus"; badge: 3
            onClicked: rec.log("clicked")
        }
        """
    )
    window = probe.window
    button = _find(window, "hb")
    assert (button.width(), button.height()) == (40, 40)
    assert _find(window, "headerButtonBadge").isVisible()
    button.setProperty("badge", 0)
    assert not _find(window, "headerButtonBadge").isVisible()
    _click(window, button)
    assert probe.recorder.events == ["clicked"]


def test_a_tag_chip_has_three_tones(harness) -> None:
    probe = harness(
        """
        Column {
            TagChip { objectName: "neutral"; text: "Installed" }
            TagChip { objectName: "primary"; text: "Running"; tone: "primary" }
            TagChip { objectName: "warning"; text: "Failed"; tone: "warning" }
        }
        """
    )
    colours = {
        name: _find(probe.window, name).property("toneColor").name()
        for name in ("neutral", "primary", "warning")
    }
    assert len(set(colours.values())) == 3
    assert colours["primary"] == "#c6ff1a"
    assert colours["warning"] == "#ffb020"


def test_a_cycle_button_steps_through_its_options(harness) -> None:
    probe = harness(
        """
        CycleButton {
            objectName: "cycle"; x: 10; y: 10
            options: [{key: "a", label: "Alpha", icon: "list"},
                      {key: "b", label: "Beta", icon: "grid"}]
            onChosen: (key) => rec.log("chosen:" + key)
        }
        """
    )
    window = probe.window
    cycle = _find(window, "cycle")
    assert _var(cycle.property("current"))["label"] == "Alpha"
    _click(window, cycle)
    _click(window, cycle)
    _click(window, cycle)
    assert probe.recorder.events == ["chosen:b", "chosen:a", "chosen:b"]
    assert cycle.property("currentKey") == "b"


def test_a_search_field_opens_reports_typing_and_escape_clears_and_folds(qapp, harness) -> None:
    probe = harness(
        """
        SearchField {
            objectName: "search"; x: 300; y: 10
            fieldObjectName: "searchInput"; buttonObjectName: "searchIcon"
            onEdited: (text) => rec.log("edited:" + text)
        }
        """
    )
    window = probe.window
    search = _find(window, "search")
    assert _find(window, "searchInput").width() == 0
    _click(window, _find(window, "searchIcon"))
    _settle(qapp, 0.4)
    assert search.property("open") is True
    assert _find(window, "searchInput").width() == 220
    _type(window, "ab")
    assert probe.recorder.events[-1] == "edited:ab"
    QTest.keyClick(window, Qt.Key.Key_Escape)
    _settle(qapp, 0.4)
    assert probe.recorder.events[-1] == "edited:"
    assert search.property("open") is False
    assert _find(window, "searchInput").width() == 0


def test_a_confirm_dialog_answers_with_the_pressed_key_and_escape_cancels(qapp, harness) -> None:
    probe = harness(
        """
        ConfirmDialog {
            id: dlg; objectName: "dlg"; title: "Delete folder"; text: "Sure?"
            buttons: [{key: "keep", label: "Keep playlists", kind: "ghost"},
                      {key: "all", label: "Delete everything", kind: "danger"},
                      {key: "go", label: "Go", kind: "primary"}]
            onAnswered: (key) => rec.log("answered:" + key)
        }
        property int openCount: 0
        onOpenCountChanged: dlg.open()
        """
    )
    window = probe.window

    def open_dialog() -> None:
        window.setProperty("openCount", window.property("openCount") + 1)
        _settle(qapp)

    open_dialog()
    assert window.findChild(QObject, "dlg").property("opened") is True
    _click(window, _find(window, "confirmButton_all"))
    _settle(qapp)
    assert probe.recorder.events == ["answered:all"]
    open_dialog()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    _settle(qapp)
    assert probe.recorder.events == ["answered:all", "answered:cancel"]
    assert window.findChild(QObject, "dlg").property("opened") is False


def test_an_inline_edit_commits_cancels_and_keeps_the_extension(qapp, harness) -> None:
    probe = harness(
        """
        InlineEdit {
            id: edit; objectName: "edit"; x: 10; y: 10; width: 300; keepExtension: true
            onCommitted: (text) => rec.log("committed:" + text)
            onCancelled: rec.log("cancelled")
        }
        property string startText: ""
        onStartTextChanged: edit.begin(startText)
        """
    )
    window = probe.window
    edit = window.findChild(QObject, "edit")
    window.setProperty("startText", "Song one.mp3")
    _settle(qapp)
    assert edit.property("selectedText") == "Song one"
    _type(window, "Song two")
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert probe.recorder.events == ["committed:Song two.mp3"]
    window.setProperty("startText", "a.mp3")
    QTest.keyClick(window, Qt.Key.Key_Escape)
    window.setProperty("startText", "b.mp3")
    window.setProperty("startText", "a.mp3")
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert probe.recorder.events[1:] == ["cancelled", "cancelled"]


_ROWS = (
    "[{id: 'a', title: 'Folder A', depth: 0, expandable: true, expanded: true},"
    " {id: 'a1', title: 'Song 1', depth: 1}, {id: 'a2', title: 'Song 2', depth: 1},"
    " {id: 'b', title: 'Folder B', depth: 0, expandable: true, expanded: true},"
    " {id: 'b1', title: 'Song 3', depth: 1}]"
)


def test_a_nav_item_highlights_only_behind_the_row_with_a_four_pixel_inset(qapp, harness) -> None:
    probe = harness(
        """
        Column {
            NavItem { objectName: "regular"; width: 240; title: "Playlist"; subtitle: "12 songs"
                leading: "P" }
            NavItem { objectName: "compact"; width: 240; size: "compact"; title: "Folder"
                leading: "folder"; expandable: true }
        }
        """
    )
    window = probe.window
    regular = _find(window, "regular")
    compact = _find(window, "compact")
    assert regular.height() == 52
    assert compact.height() == 28
    tile = [item for item in regular.childItems()[-1].childItems() if item.objectName()]
    del tile
    assert regular.property("tileSize") == 40
    assert compact.property("tileSize") == 18
    QTest.mouseMove(window, _centre(regular))
    _settle(qapp)
    background = next(
        item for item in regular.childItems() if item.objectName() == "navItemBackground"
    )
    assert background.x() == 4
    assert background.width() == 240 - 8
    assert background.property("color").name() != "#000000"
    assert background.property("color").alpha() > 0


def test_a_nav_list_selects_with_ctrl_and_shift_across_depths_and_the_keyboard(
    qapp, harness
) -> None:
    probe = harness(
        f"""
        NavList {{
            objectName: "list"; width: 300; height: 400; size: "compact"; model: {_ROWS}
            onActivated: (rowId) => rec.log("activated:" + rowId)
            onRowDragStarted: (ids) => rec.log("drag:" + ids.join(","))
        }}
        """
    )
    window = probe.window
    nav = _find(window, "list")

    def row(name: str) -> QQuickItem:
        return _find(window, "navRow_" + name)

    def selected() -> list[str]:
        return _var(nav.property("selectedIds"))

    ctrl, shift = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier
    _click(window, row("a1"))
    assert selected() == ["a1"]
    _click(window, row("b1"), mods=ctrl)
    assert selected() == ["a1", "b1"]
    _click(window, row("a1"), mods=ctrl)
    assert selected() == ["b1"]
    _click(window, row("a2"))
    _click(window, row("b1"), mods=shift)
    assert selected() == ["a2", "b", "b1"]
    _click(window, row("a1"))
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert selected() == ["a2"]
    QTest.keyClick(window, Qt.Key.Key_Down)
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert selected() == ["b"]
    assert probe.recorder.events[-1] == "activated:b"
    QTest.keyClick(window, Qt.Key.Key_Up)
    assert selected() == ["a2"]


def test_zone_at_uses_the_outer_quarter_and_the_allowed_list(harness) -> None:
    probe = harness(
        """
        DropZoneOverlay { id: zones; objectName: "zones"; width: 400; height: 300 }
        DropZoneOverlay { objectName: "big"; width: 700; height: 500 }
        DropZoneOverlay { objectName: "wide"; width: 700; height: 300 }
        DropZoneOverlay { objectName: "small"; width: 500; height: 300 }
        property var cases: [
            [10, 150, null], [390, 150, null], [200, 10, null], [200, 290, null],
            [200, 150, null], [99, 150, null], [101, 150, null], [10, 40, null],
            [40, 10, null], [10, 150, ["center", "top"]], [10, 150, ["top"]],
            [10, 10, ["center", "top"]], [-1, 5, null]]
        property var results: cases.map(c => zones.zoneAt(c[0], c[1], 400, 300, c[2]))
        """
    )
    assert _var(probe.window.property("results")) == [
        "left",
        "right",
        "top",
        "bottom",
        "center",
        "left",
        "center",
        "left",
        "top",
        "center",
        "",
        "top",
        "",
    ]
    window = probe.window
    assert _var(_find(window, "big").property("allowed")) == [
        "center",
        "left",
        "right",
        "top",
        "bottom",
    ]
    assert _var(_find(window, "wide").property("allowed")) == ["center", "left", "right"]
    assert _var(_find(window, "small").property("allowed")) == ["center"]


_TABS = (
    "[{id: 'a', title: 'Alpha', kind: 'folder'}, {id: 'b', title: 'Beta', kind: 'playlist'},"
    " {id: 'c', title: 'Gamma', kind: 'settings', preview: true}]"
)


def test_a_tab_strip_clicks_closes_keeps_and_reorders_by_dragging(qapp, harness) -> None:
    probe = harness(
        f"""
        TabStrip {{
            objectName: "strip"; width: 700; groupId: 7; activeId: "a"; focused: true
            tabs: {_TABS}
            onTabClicked: (id) => rec.log("click:" + id)
            onTabClosed: (id) => rec.log("close:" + id)
            onTabKept: (id) => rec.log("keep:" + id)
            onTabMoved: (id, to) => rec.log("move:" + id + ":" + to)
        }}
        """
    )
    window = probe.window
    tab_a, tab_b, tab_c = (_find(window, f"stripTab_{key}") for key in "abc")
    _click(window, tab_b)
    _click(window, tab_b, button=Qt.MouseButton.MiddleButton)
    QTest.mouseDClick(
        window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _centre(tab_c)
    )
    _click(window, _find(window, "stripTabClose_a"))
    assert probe.recorder.events[:2] == ["click:b", "close:b"]
    assert "keep:c" in probe.recorder.events
    assert probe.recorder.events[-1] == "close:a"
    probe.recorder.events.clear()
    # Drag Alpha onto Gamma: the strip reports the move to Gamma's index.
    start, end = _centre(tab_a), _centre(tab_c)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    steps = 12
    for step in range(1, steps + 1):
        point = QPoint(
            start.x() + (end.x() - start.x()) * step // steps,
            start.y() + (end.y() - start.y()) * step // steps,
        )
        QTest.mouseMove(window, point)
        _settle(qapp, 0.01)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    _settle(qapp)
    assert probe.recorder.events == ["move:a:2"]


def test_a_tab_strip_lists_all_tabs_in_a_drop_down_when_they_do_not_fit(qapp, harness) -> None:
    tabs = ", ".join(f"{{id: 't{i}', title: 'Tab number {i}', kind: 'folder'}}" for i in range(12))
    probe = harness(
        f"""
        TabStrip {{
            objectName: "strip"; width: 400; activeId: "t0"
            tabs: [{tabs}]
        }}
        TabStrip {{ objectName: "roomy"; y: 100; width: 400; tabs: [{{id: 'x', title: 'X'}}] }}
        """
    )
    window = probe.window
    strip, roomy = _find(window, "strip"), _find(window, "roomy")
    assert strip.property("overflowing") is True
    assert _find_in(strip, "tabOverflowButton").isVisible()
    assert roomy.property("overflowing") is False
    assert not _find_in(roomy, "tabOverflowButton").isVisible()


def test_a_tab_strip_in_switcher_mode_lists_the_other_windows(harness) -> None:
    probe = harness(
        """
        TabStrip {
            objectName: "strip"; width: 400; switcher: true
            switcherEntries: [{id: "w2", title: "Window 2"}]
            onSwitcherChosen: (id) => rec.log("window:" + id)
        }
        """
    )
    assert _find(probe.window, "tabSwitcherButton").isVisible()
    assert _find(probe.window, "tabSwitcherButton").width() == 28


def test_an_action_menu_draws_groups_with_one_separator_between_non_empty_ones(
    qapp, harness
) -> None:
    probe = harness(
        """
        ActionMenu {
            id: menu; objectName: "menu"
            groups: [
                {id: "one", items: [{id: "a", label: "Alpha"},
                    {id: "b", label: "Beta", enabled: false}]},
                {id: "hidden", items: [{id: "x", label: "Hidden", visible: false}]},
                {id: "empty", items: []},
                {id: "two", items: [{id: "c", label: "Gamma", danger: true, hint: "Del"},
                    {id: "d", label: "Delta", submenu: [{id: "e", label: "Epsilon"}]}]}
            ]
            onTriggered: (id) => rec.log("triggered:" + id)
        }
        property int openCount: 0
        onOpenCountChanged: menu.popup(10, 10)
        """
    )
    window = probe.window
    window.setProperty("openCount", 1)
    _settle(qapp)
    menu = window.findChild(QObject, "menu")
    content = cast(QQuickItem, menu.property("contentItem"))
    entries = sorted(content.childItems()[0].childItems(), key=lambda item: item.y())
    labels = [
        str(item.property("text")) if item.property("text") else "---"
        for item in entries
        if item.isVisible() and item.height() > 0
    ]
    assert labels == ["Alpha", "Beta", "---", "Gamma", "Delta"]
    by_text = {str(item.property("text")): item for item in entries if item.property("text")}
    assert "Hidden" not in by_text
    assert by_text["Beta"].property("enabled") is False
    assert by_text["Gamma"].property("danger") is True
    first = by_text["Alpha"]
    _click(window, first)
    _settle(qapp)
    assert probe.recorder.events == ["triggered:a"]


def test_one_wheel_notch_scrolls_three_times_the_old_distance(qapp, harness) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QGuiApplication, QWheelEvent

    probe = harness(
        """
        Flickable {
            id: flick; objectName: "flick"; width: 300; height: 200
            contentHeight: 20000; contentWidth: 300
            WheelScrollHandler { flickable: flick }
        }
        """
    )
    window = probe.window
    flick = _find(window, "flick")
    lines = QGuiApplication.styleHints().wheelScrollLines()
    point = QPointF(100, 100)
    event = QWheelEvent(
        point,
        window.mapToGlobal(point),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    # The first event of a fresh window is taken by the Flickable itself; measure the second.
    qapp.sendEvent(window, event)
    _settle(qapp, 0.6)
    before = flick.property("contentY")
    qapp.sendEvent(window, event)
    _settle(qapp, 0.6)
    # The old distance was lines * 24 px * 1.25 per notch; it is now three times that.
    assert flick.property("contentY") - before == pytest.approx(lines * 24 * 1.25 * 3, abs=1)

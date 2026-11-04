"""Feedback batch 136: playlist folder without a dialog, Liked heart, popover toggle, tab menu,
the layout that comes back after a restart, and the player title as a drag source."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_components_130 import _centre, _click, _find, _find_in, _settle, _var
from tests.ui.test_components_130 import harness as harness
from tests.ui.test_player_views import _find as _find_named
from tests.ui.test_player_views import _UiPlayerBackend, _visible
from tests.ui.track_list_fixtures import add_folder_tracks, open_folder

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.persistence.library_repository import LibraryRepository


def _click_named(root: QQuickWindow, name: str) -> None:
    item = _find_named(root, name)
    assert item is not None and item.isVisible(), name
    point = item.mapToScene(item.boundingRect().center())
    QTest.mouseClick(
        root, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
    )


def test_a_new_playlist_folder_is_made_at_once_and_renamed_inline(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(Any, runtime.workspace)
    playlists = cast(Any, workspace.playlistModel)
    try:
        workspace.setActivity("playlists")
        qtbot.waitUntil(lambda: _visible(root, "playlistsPlusButton"), timeout=5000)
        QTest.qWait(200)
        _click_named(root, "playlistsPlusButton")
        qtbot.waitUntil(lambda: _visible(root, "newFolderMenuItem"), timeout=5000)
        QTest.qWait(200)
        _click_named(root, "newFolderMenuItem")
        qtbot.waitUntil(lambda: len(playlists.folders) == 1, timeout=5000)
        folder = cast(list[dict[str, Any]], playlists.folders)[0]
        assert folder["name"] == "Untitled folder 01"
        # No "New folder" dialog: the name field of the playlist dialogs never shows.
        assert not _visible(root, "playlistNameInput")
        pane = root.findChild(QObject, "playlistsPane")
        assert pane is not None
        qtbot.waitUntil(lambda: pane.property("renamingId") == folder["id"], timeout=5000)
        # The next one takes the next number.
        playlists.createUntitledFolder("")
        qtbot.waitUntil(lambda: len(playlists.folders) == 2, timeout=5000)
        names = sorted(str(item["name"]) for item in cast(list[dict], playlists.folders))
        assert names == ["Untitled folder 01", "Untitled folder 02"]
    finally:
        _shutdown(runtime)
        application.processEvents()


def test_liked_tracks_shows_the_heart_never_a_mosaic(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(Any, runtime.workspace)
    playlists = cast(Any, workspace.playlistModel)
    try:
        root_id, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 3)
        assert runtime.jobs.wait_for_done(10_000)
        for track_id in track_ids:
            playlists.toggleLike(track_id)
        qtbot.waitUntil(lambda: len(playlists._liked) == 3, timeout=5000)
        liked_row = next(row for row in cast(list[dict], playlists.tree) if row["id"] == "liked")
        assert liked_row["covers"] == []
        assert playlists.details("liked")["covers"] == []
        workspace.setActivity("playlists")
        qtbot.waitUntil(lambda: _find_named(root, "navRow_liked") is not None, timeout=5000)
        row = _find_named(root, "navRow_liked")
        assert row is not None
        assert row.property("leading") == "heart"
        assert row.property("tileGradient") is True
        workspace.openPlaylist("liked")
        qtbot.waitUntil(lambda: _find_named(root, "playlistCoverHeart") is not None, timeout=5000)
        heart = _find_named(root, "playlistCoverHeart")
        assert heart is not None and heart.isVisible()
        del root_id
    finally:
        _shutdown(runtime)
        application.processEvents()


def test_a_header_button_closes_its_open_popover_instead_of_reopening_it(qapp, harness) -> None:
    probe = harness(
        """
        HeaderButton {
            id: hb; objectName: "hb"; x: 700; y: 10; icon: "bell"
            onClicked: pop.toggle()
        }
        Popover {
            id: pop; objectName: "pop"; anchorItem: hb; bodyWidth: 200
            Rectangle { width: 200; height: 80; color: "green" }
        }
        """
    )
    window = probe.window
    button = _find(window, "hb")
    popover = window.findChild(QObject, "pop")
    assert popover is not None
    _click(window, button)
    _settle(qapp)
    assert popover.property("opened") is True
    # The press outside closes it, the click that follows must not open it again.
    _click(window, button)
    _settle(qapp)
    assert popover.property("opened") is False
    # A later click opens it again.
    QTest.qWait(450)
    _click(window, button)
    _settle(qapp)
    assert popover.property("opened") is True


def test_the_menu_of_a_tab_lists_the_close_and_split_entries_and_disables_what_does_not_apply(
    qapp,
    harness,
) -> None:
    probe = harness(
        """
        TabStrip {
            objectName: "strip"; width: 700
            groupId: "g1"; activeId: "a"
            tabs: [{id: "a", title: "A"}, {id: "b", title: "B"}, {id: "c", title: "C"}]
            onTabAction: (id, action) => rec.log(action + ":" + id)
        }
        """
    )
    window = probe.window
    strip = _find(window, "strip")
    menu = window.findChild(QObject, "tabContextMenu")
    assert menu is not None

    def ids_and_states() -> dict[str, bool]:
        groups = _var(menu.property("groups"))
        return {
            item["id"]: item.get("enabled", True) is not False
            for group in groups
            for item in group["items"]
        }

    first = _find_in(strip, "stripTab_a")
    QTest.mouseClick(
        window, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, _centre(first)
    )
    _settle(qapp)
    states = ids_and_states()
    assert list(states) == [
        "close",
        "others",
        "all",
        "left",
        "right",
        "splitRight",
        "splitLeft",
        "splitUp",
        "splitDown",
    ]
    assert states["left"] is False and states["right"] is True and states["others"] is True
    QTest.keyClick(window, Qt.Key.Key_Escape)
    _settle(qapp)

    last = _find_in(strip, "stripTab_c")
    QTest.mouseClick(
        window, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, _centre(last)
    )
    _settle(qapp)
    states = ids_and_states()
    assert states["right"] is False and states["left"] is True
    entry = _find(window, "tabMenuSplitDown")
    _click(window, entry)
    _settle(qapp)
    assert probe.recorder.events == ["splitDown:c"]


def test_the_tab_menu_actions_close_and_split_through_the_workspace(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    workspace = cast(Any, runtime.workspace)
    try:
        library = LibraryRepository(runtime.database)
        root_id, _ids = add_folder_tracks(runtime, tmp_path / "audio", 1)
        (tmp_path / "audio" / "one").mkdir()
        (tmp_path / "audio" / "two").mkdir()
        (tmp_path / "audio" / "three").mkdir()
        del library
        assert runtime.jobs.wait_for_done(10_000)
        workspace.openSettings()
        workspace.openProfile()
        workspace.openTasks()
        open_folder(runtime, root_id)
        group = workspace.groups[0]
        tabs = list(group["tabs"])
        assert len(tabs) == 4
        first, second, third, fourth = (tab["id"] for tab in tabs)
        workspace.closeTabs("g1", "left", third)
        assert [t["id"] for t in workspace.groups[0]["tabs"]] == [third, fourth]
        workspace.closeTabs("g1", "right", third)
        assert [t["id"] for t in workspace.groups[0]["tabs"]] == [third]
        workspace.openSettings()
        workspace.openProfile()
        workspace.closeTabs("g1", "others", third)
        assert [t["id"] for t in workspace.groups[0]["tabs"]] == [third]
        # Split right moves the tab into a new window beside the first.
        workspace.openSettings()
        workspace.splitWithTab("g1", "right", "g1", third)
        groups = workspace.groups
        assert len(groups) == 2
        assert [t["id"] for t in groups[1]["tabs"]] == [third]
        workspace.closeTabs(groups[1]["id"], "all", "")
        assert first and second
    finally:
        _shutdown(runtime)
        application.processEvents()


def test_the_window_layout_comes_back_after_a_restart(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    options = AppOptions(data_dir=tmp_path / "data")
    runtime = _build_runtime(application, options)
    assert runtime is not None
    workspace = cast(Any, runtime.workspace)
    root_id, _ids = add_folder_tracks(runtime, tmp_path / "audio", 2)
    open_folder(runtime, root_id)
    workspace.openSettings()
    group_id = str(workspace.groups[0]["id"])
    settings_tab = "settings:"
    workspace.splitWithTab(group_id, "right", group_id, settings_tab)
    workspace.openToolWindow("info", False)
    workspace.setDockWidth("right", 410)
    workspace.setDockWidth("left", 300)
    workspace.saveWindowGeometry(120, 90, 1111, 777, False)
    before_groups = [
        {"id": g["id"], "tabs": [t["id"] for t in g["tabs"]], "active": g["active"]}
        for g in workspace.groups
    ]
    before_active = workspace.activeGroup
    before_layout = workspace._layout
    before_docks = {side: workspace.dockState(side) for side in ("left", "right")}
    assert len(before_groups) == 2
    _shutdown(runtime)
    application.processEvents()

    runtime = _build_runtime(application, options)
    assert runtime is not None
    workspace = cast(Any, runtime.workspace)
    try:
        after_groups = [
            {"id": g["id"], "tabs": [t["id"] for t in g["tabs"]], "active": g["active"]}
            for g in workspace.groups
        ]
        assert after_groups == before_groups
        assert workspace.activeGroup == before_active
        assert workspace._layout == before_layout
        assert {side: workspace.dockState(side) for side in ("left", "right")} == before_docks
        saved = workspace.savedWindow
        assert (saved["x"], saved["y"], saved["width"], saved["height"]) == (120, 90, 1111, 777)
        assert saved["maximized"] is False
    finally:
        _shutdown(runtime)
        application.processEvents()

    # A source that was removed between two runs: its tab is dropped without a word.
    database_runtime = _build_runtime(application, options)
    assert database_runtime is not None
    try:
        LibraryRepository(database_runtime.database).remove_root(root_id)
    finally:
        _shutdown(database_runtime)
        application.processEvents()
    runtime = _build_runtime(application, options)
    assert runtime is not None
    workspace = cast(Any, runtime.workspace)
    try:
        assert runtime.jobs.wait_for_done(10_000)
        qtbot.waitUntil(
            lambda: (
                not any(
                    str(t["id"]).startswith("folder:") for g in workspace.groups for t in g["tabs"]
                )
            ),
            timeout=10_000,
        )
        assert workspace.message == ""
    finally:
        _shutdown(runtime)
        application.processEvents()


def test_the_player_title_is_a_drag_source_with_the_menu_of_a_track(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(Any, runtime.workspace)
    try:
        _root_id, ids = add_folder_tracks(runtime, tmp_path / "audio", 1)
        assert runtime.jobs.wait_for_done(10_000)
        bar = _find_named(root, "playerIsland")
        assert bar is not None
        workspace.playTrack(ids[0], f"folder:{_root_id}/")
        qtbot.waitUntil(lambda: workspace.playingId == ids[0], timeout=5000)
        session = _find_named(root, "playerDragSession")
        assert session is not None
        # The same keys and fields as a track row of a list.
        assert list(_var(session.property("dragTrackIds"))) == [ids[0]]
        assert session.property("dragCanAdd") is True
        title = _find_named(root, "playerIslandTitle")
        assert title is not None
        QTest.mouseMove(root, _centre(title))
        QTest.qWait(200)
        QTest.mouseClick(
            root,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
            _centre(title),
        )
        menu = root.findChild(QObject, "playerTrackMenu")
        assert menu is not None
        qtbot.waitUntil(lambda: bool(menu.property("visible")), timeout=5000)
        labels = [
            item["label"]
            for group in _var(menu.property("groups"))
            for item in group["items"]
            if item.get("visible", True)
        ]
        assert "Add to playlist…" in labels and "Edit info" in labels
    finally:
        _shutdown(runtime)
        application.processEvents()


def test_ctrl_c_ctrl_x_and_ctrl_v_move_tracks_between_playlists_and_a_folder_copy(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    root.show()
    workspace = cast(Any, runtime.workspace)
    playlists = cast(Any, workspace.playlistModel)
    try:
        root_id, ids = add_folder_tracks(runtime, tmp_path / "audio", 3)
        assert runtime.jobs.wait_for_done(10_000)
        playlists.createUntitled("", ids[:2])
        qtbot.waitUntil(lambda: len(playlists._playlists) == 1, timeout=5000)
        playlists.createUntitled("", [])
        qtbot.waitUntil(lambda: len(playlists._playlists) == 2, timeout=5000)
        by_name = {str(p["name"]): str(p["id"]) for p in playlists._playlists}
        first, second = by_name["Untitled playlist 01"], by_name["Untitled playlist 02"]
        qtbot.waitUntil(lambda: not playlists._pending and not playlists._current_job)

        def rows_of(identity: str) -> list[str]:
            return [str(r["trackId"]) for r in playlists.service.rows(identity)]

        assert rows_of(first) == ids[:2] and rows_of(second) == []
        workspace.openPlaylist(first)
        qtbot.waitUntil(lambda: _find_named(root, "trackRow_2") is not None, timeout=10_000)
        row = _find_named(root, "trackRow_1")
        assert row is not None
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=_centre(row))
        QTest.mouseClick(
            root,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
            _centre(cast(Any, _find_named(root, "trackRow_2"))),
        )
        qtbot.waitUntil(lambda: len(workspace.selectedIds) == 2, timeout=5000)
        ctrl = Qt.KeyboardModifier.ControlModifier
        QTest.keyClick(root, Qt.Key.Key_X, ctrl)
        qtbot.waitUntil(lambda: workspace.clipboardCount == 2, timeout=5000)
        workspace.openPlaylist(second)
        qtbot.waitUntil(lambda: workspace.activeTabId == f"playlist:{second}", timeout=5000)
        QTest.qWait(300)
        QTest.keyClick(root, Qt.Key.Key_V, ctrl)
        qtbot.waitUntil(lambda: rows_of(second) == ids[:2], timeout=10_000)
        qtbot.waitUntil(lambda: rows_of(first) == [], timeout=10_000)
        assert workspace.clipboardCount == 0
        assert "Added 2 tracks" in workspace.message

        # Ctrl+C of a folder selection pasted into a folder list copies the files.
        (tmp_path / "audio" / "dest").mkdir()
        workspace.openFolder(f"folder:{root_id}/")
        qtbot.waitUntil(lambda: _find_named(root, "trackRow_1") is not None, timeout=10_000)
        workspace.selectTrack(ids[0], "single", [])
        QTest.keyClick(root, Qt.Key.Key_C, ctrl)
        qtbot.waitUntil(lambda: workspace.clipboardCount == 1, timeout=5000)
        workspace.openFolder(f"folder:{root_id}/dest")
        QTest.qWait(300)
        QTest.keyClick(root, Qt.Key.Key_V, ctrl)
        qtbot.waitUntil(
            lambda: (tmp_path / "audio" / "dest" / "track-000.wav").is_file(), timeout=10_000
        )
        assert (tmp_path / "audio" / "track-000.wav").is_file()
        assert workspace.clipboardCount == 1  # a copy stays on the clipboard
    finally:
        _shutdown(runtime)
        application.processEvents()


def test_dragging_songs_from_one_split_to_another_adds_moves_or_copies(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    from tests.ui.test_track_drag_98 import _drag

    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    root.show()
    workspace = cast(Any, runtime.workspace)
    playlists = cast(Any, workspace.playlistModel)
    try:
        root_id, _ids = add_folder_tracks(runtime, tmp_path / "audio", 2)
        audio = tmp_path / "audio"
        (audio / "dest").mkdir()
        assert runtime.jobs.wait_for_done(10_000)
        playlists.createUntitled("", [])
        qtbot.waitUntil(lambda: len(playlists._playlists) == 1, timeout=5000)
        playlist = str(playlists._playlists[0]["id"])
        qtbot.waitUntil(lambda: workspace.activeTabId == f"playlist:{playlist}", timeout=5000)
        group = str(workspace.groups[0]["id"])
        workspace.splitWithTab(group, "right", group, f"playlist:{playlist}")
        workspace.openFolder(f"folder:{root_id}/")
        qtbot.waitUntil(lambda: _find_named(root, "trackRow_1") is not None, timeout=10_000)
        row = cast(Any, _find_named(root, "trackRow_1"))
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=_centre(row))
        qtbot.waitUntil(lambda: len(workspace.selectedIds) == 1, timeout=5000)
        selected = workspace.selectedIds[0]
        # The right window holds the folder list, the left one the playlist: drop on the playlist.
        _drag(root, _centre(row), QPoint(560, 520))
        qtbot.waitUntil(
            lambda: [str(r["trackId"]) for r in playlists.service.rows(playlist)] == [selected],
            timeout=10_000,
        )
        # Now the "dest" folder replaces the folder list; the playlist row is dropped on it.
        workspace.openFolder(f"folder:{root_id}/dest")
        qtbot.waitUntil(lambda: _find_named(root, "trackRow_1") is not None, timeout=10_000)
        prow = cast(Any, _find_named(root, "trackRow_1"))
        QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=_centre(prow))
        qtbot.waitUntil(lambda: len(workspace.selectedIds) == 1, timeout=5000)
        _drag(root, _centre(prow), QPoint(1100, 520), release=False)
        QTest.keyPress(root, Qt.Key.Key_Control)
        QTest.mouseRelease(root, Qt.MouseButton.LeftButton, pos=QPoint(1100, 520))
        QTest.keyRelease(root, Qt.Key.Key_Control)
        qtbot.waitUntil(lambda: len(list((audio / "dest").glob("*.wav"))) == 1, timeout=10_000)
        # Ctrl was held: the file is copied, the original stays where it was.
        assert len(list(audio.glob("track-*.wav"))) == 2
    finally:
        _shutdown(runtime)
        application.processEvents()


def test_an_unnamed_explorer_folder_starts_in_inline_rename(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=tmp_path / "data"))
    assert runtime is not None
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    workspace = cast(Any, runtime.workspace)
    try:
        root_id, _ids = add_folder_tracks(runtime, tmp_path / "audio", 1)
        assert runtime.jobs.wait_for_done(10_000)
        workspace.setActivity("explorer")
        pane = None
        qtbot.waitUntil(
            lambda: (
                root.findChild(QObject, "explorerPane") is not None
                or _find_named(root, "explorerPane") is not None
            ),
            timeout=10_000,
        )
        pane = root.findChild(QObject, "explorerPane") or _find_named(root, "explorerPane")
        assert pane is not None
        with qtbot.waitSignal(workspace.folderRenameRequested, timeout=10_000) as blocker:
            workspace.createUnnamedFolder(f"root:{root_id}")
        assert blocker.args == [f"folder:{root_id}/Unnamed folder 01"]
        qtbot.waitUntil(lambda: pane.property("editMode") == "rename", timeout=10_000)
    finally:
        _shutdown(runtime)
        application.processEvents()

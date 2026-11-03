"""The first-match dialog in the real window (plan 126.2): the five counts, the rows, Cancel.

The window starts with ``--plugin-dir plugins``, offscreen, as the Settings tests do. The report is
built by hand (no server, no file): the dialog is what is checked here, not the match.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import cast

from mtee.plugins.remote.first_match import MatchReport  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.matcher import (  # pyright: ignore[reportMissingImports]
    DUPLICATE,
    UNREADABLE,
    LocalTrack,
    MatchResult,
    NotMatched,
    Pair,
    ServerItem,
)
from mtee.plugins.remote.ui.first_match_backend import (  # pyright: ignore[reportMissingImports]
    FirstMatchBackend,
    group_rows,
)
from PySide6.QtCore import QObject, QPointF
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.helpers.ui_plugin import (
    click,
    plugin_ui_of,
    settle,
    start_app,
    window_of,
    workspace_of,
)
from tests.plugins.remote.conftest import PLUGIN_DIR

from mtee.app import _shutdown

DIALOG_KEY = "remote.first_match"


def _report() -> MatchReport:
    """Counts 2, 3, 4, 5 and 6: each group has its own number, so the test can tell them apart."""
    matched = tuple(
        Pair(
            LocalTrack(f"m{i}", f"matched/{i}.flac", f"s{i}", f"a{i}"),
            ServerItem(f"mv{i}", "root", f"matched/{i}.flac", f"s{i}", f"a{i}", revision=1),
        )
        for i in range(2)
    )
    upload = tuple(LocalTrack(f"u{i}", f"new/{i}.flac", f"us{i}", f"ua{i}") for i in range(3))
    server_only = tuple(
        ServerItem(f"sv{i}", "root", f"far/{i}.flac", f"ss{i}", f"sa{i}") for i in range(4)
    )
    tags = tuple(
        Pair(
            LocalTrack(f"t{i}", f"tags/{i}.flac", f"ts{i}", f"ta{i}"),
            ServerItem(f"tv{i}", "root", f"tags/{i}.flac", f"tv-sha{i}", f"ta{i}"),
        )
        for i in range(5)
    )
    not_matched = tuple(
        NotMatched(
            LocalTrack(f"n{i}", f"copy/{i}.flac", None if i % 2 else f"ns{i}", None),
            UNREADABLE if i % 2 else DUPLICATE,
        )
        for i in range(6)
    )
    return MatchReport(
        result=MatchResult(
            matched=matched,
            tags_differ=tags,
            to_upload=upload,
            server_only=server_only,
            not_matched=not_matched,
        ),
        local_total=16,
        server_total=11,
        skipped=0,
        unhashed=0,
        mappings=1,
    )


def _big_report() -> MatchReport:
    """A real library's shape: 2,617 pairs in Tags differ, each with another server path.

    The names are long, so the test also shows that a long name is elided inside the dialog.
    """
    report = _report()
    tags = tuple(
        Pair(
            LocalTrack(
                f"bt{i}",
                f"Artist {i % 40}/Album {i % 97}/A track with a long name number {i:05d}.flac",
                f"bs{i}",
                f"ba{i}",
            ),
            ServerItem(
                f"bv{i}",
                "root",
                f"Server copies/Artist {i % 40}/A track with a long name number {i:05d}.flac",
                f"bv-sha{i}",
                f"ba{i}",
            ),
        )
        for i in range(2617)
    )
    return dataclasses.replace(report, result=dataclasses.replace(report.result, tags_differ=tags))


def _dialog_items(window: QQuickWindow, name: str) -> list[QQuickItem]:
    """The items named ``name`` inside the plugin dialog (the popup is not in the window tree)."""
    popup = window.findChild(QObject, "pluginDialog")
    assert popup is not None, "the plugin dialog is not in the window"
    pending = [cast(QQuickItem, popup.property("contentItem"))]
    found: list[QQuickItem] = []
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            found.append(item)
        pending.extend(item.childItems())
    return found


def test_the_dialog_shows_the_five_counts_and_cancel_closes_it(
    qapp: object, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        ui = plugin_ui_of(workspace)
        backend = cast(FirstMatchBackend, ui.dialogBackend(DIALOG_KEY))
        assert backend is not None

        backend.show(_report(), "first")
        ui.open_dialog(DIALOG_KEY, "first")
        settle(runtime)

        # Top to bottom, as the groups are drawn: Matched, To upload, Server only, Tags differ,
        # Not matched.
        shown = sorted(
            _dialog_items(window, "firstMatchCount"),
            key=lambda item: item.mapToScene(QPointF(0, 0)).y(),
        )
        counts = [item.property("text") for item in shown]
        assert counts == ["2", "3", "4", "5", "6"]
        intro = _dialog_items(window, "firstMatchIntro")[0].property("text")
        assert "16 tracks" in intro and "11" in intro
        assert "Nothing is sent or downloaded until you press Start sync." in intro

        assert _dialog_items(window, "firstMatchStart"), "the Start sync button is in the dialog"

        click(window, _dialog_items(window, "firstMatchCancel")[0])
        settle(runtime)

        assert backend.report is None
        popup = window.findChild(QObject, "pluginDialog")
        assert popup is not None
        assert popup.property("opened") is False
    finally:
        _shutdown(runtime)


def test_a_big_library_fits_the_window_and_keeps_the_buttons_in_reach(
    qapp: object, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        window.resize(1280, 720)
        settle(runtime)
        ui = plugin_ui_of(workspace)
        backend = cast(FirstMatchBackend, ui.dialogBackend(DIALOG_KEY))
        assert backend is not None

        backend.show(_big_report(), "first")
        ui.open_dialog(DIALOG_KEY, "first")
        settle(runtime)

        # Tags differ is unfolded by default, since it has rows.
        tags = next(group for group in backend.groups if group["key"] == "tags_differ")
        assert tags["count"] == "2,617"
        assert tags["open"] is True

        dialog = _dialog_items(window, "firstMatchDialog")[0]
        assert dialog.width() == 600

        # The buttons are inside the window: their bottom edge is at or above the window's bottom.
        start = _dialog_items(window, "firstMatchStart")[0]
        cancel = _dialog_items(window, "firstMatchCancel")[0]
        assert start.mapToScene(start.boundingRect().bottomLeft()).y() <= 720
        assert cancel.mapToScene(cancel.boundingRect().bottomLeft()).y() <= 720

        # The groups scroll: the list is taller than the area that shows it.
        scroll = _dialog_items(window, "firstMatchScroll")[0]
        assert scroll.height() < float(scroll.property("contentHeight"))

        # Every row on screen stays inside the dialog's 600 px.
        rows = [row for row in _dialog_items(window, "firstMatchRow") if row.isVisible()]
        assert rows
        right_edges = [row.mapToItem(dialog, QPointF(row.width(), 0)).x() for row in rows]
        assert max(right_edges) <= 600
    finally:
        _shutdown(runtime)


def _visible_items(window: QQuickWindow, name: str) -> list[QQuickItem]:
    """The items named ``name`` that are shown (a hidden group keeps a copy of the chips)."""
    return [item for item in _dialog_items(window, name) if item.isVisible()]


def test_the_choice_chips_set_the_choice_and_a_new_report_resets_it(
    qapp: object, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        ui = plugin_ui_of(workspace)
        backend = cast(FirstMatchBackend, ui.dialogBackend(DIALOG_KEY))
        assert backend is not None

        backend.show(_report(), "first")
        ui.open_dialog(DIALOG_KEY, "first")
        settle(runtime)
        assert backend.choice == "computer"
        # One shown set of chips: the Tags differ group's.
        assert len(_visible_items(window, "firstMatchChoice_server")) == 1
        text = _visible_items(window, "firstMatchChoiceText")[0]
        assert text.property("text").startswith("The server's copies take this computer's tags")

        click(window, _visible_items(window, "firstMatchChoice_server")[0])
        settle(runtime)
        assert backend.choice == "server"
        assert _visible_items(window, "firstMatchChoice_server")[0].property("checked") is True
        assert _visible_items(window, "firstMatchChoice_computer")[0].property("checked") is False
        text = _visible_items(window, "firstMatchChoiceText")[0]
        assert "Only the tags are downloaded." in text.property("text")

        click(window, _visible_items(window, "firstMatchChoice_later")[0])
        settle(runtime)
        assert backend.choice == "later"

        backend.show(_report(), "again")
        settle(runtime)
        assert backend.choice == "computer"
    finally:
        _shutdown(runtime)


def test_the_backend_ignores_an_unknown_choice() -> None:
    backend = FirstMatchBackend()
    backend.show(_report(), "first")
    assert backend.choice == "computer"

    backend.setChoice("server")
    assert backend.choice == "server"
    for unknown in ("both", "", "Server"):
        backend.setChoice(unknown)
        assert backend.choice == "server", unknown

    backend.show(_report(), "again")
    assert backend.choice == "computer"


def test_a_row_names_the_server_path_only_when_it_differs() -> None:
    other = Pair(
        LocalTrack("a", "Music/one.flac", "sa", "aa"),
        ServerItem("a-item", "root", "Server/one.flac", "sa", "aa"),
    )
    same = Pair(
        LocalTrack("b", "two.flac", "sb", "ab"),
        ServerItem("b-item", "root", "two.flac", "sb", "ab"),
    )
    result = MatchResult(matched=(other, same), tags_differ=(other,))

    groups = {group["key"]: group for group in group_rows(result, lambda key: True)}
    notes = [row["note"] for row in groups["matched"]["items"]]
    assert notes == ["On the server: Server/one.flac", ""]
    assert groups["tags_differ"]["items"][0]["note"] == "On the server: Server/one.flac"
    assert groups["tags_differ"]["label"] == "Same audio, different file"

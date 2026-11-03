"""The first-match dialog in the real window (plan 126.2): the five counts, the rows, Cancel.

The window starts with ``--plugin-dir plugins``, offscreen, as the Settings tests do. The report is
built by hand (no server, no file): the dialog is what is checked here, not the match.
"""

from __future__ import annotations

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

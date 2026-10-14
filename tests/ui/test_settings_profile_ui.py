"""Settings categories, the Profile page, and the listening columns, in the live QML window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QObject, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.track_list_fixtures import add_folder_tracks, open_folder

from mtee.app import _build_runtime, _Runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.artist_index import MODE_SPLIT
from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.track_list_model import TrackListModel
from mtee.persistence.credit_override_repository import CreditOverrideRepository
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository

# Each category of the Settings tab and the object name of its page.
CATEGORY_PAGES = {
    "general": "generalSettings",
    "library": "librarySettings",
    "playback": "playbackSettings",
    "analysis": "analysisSettings",
    "shortcuts": "shortcutSettings",
    "privacy": "privacySettings",
    "about": "aboutSettings",
}


def _first(root: QQuickItem, name: str) -> QQuickItem:
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    raise AssertionError(f"no QML item named {name}")


def _texts(root: QQuickItem) -> list[str]:
    found: list[str] = []
    pending = [root]
    while pending:
        item = pending.pop()
        text = item.property("text")
        if isinstance(text, str):
            found.append(text)
        pending.extend(item.childItems())
    return found


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    centre = item.mapToScene(item.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    QTest.qWait(30)


def _settle(runtime: _Runtime) -> None:
    """Let the background jobs and the queued signals finish."""
    for _ in range(40):
        runtime.jobs.wait_for_done(500)
        QCoreApplication.processEvents()
        QTest.qWait(25)


def _demo_runtime(qapp, tmp_path: Path) -> tuple[Any, _Runtime]:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application, AppOptions(data_dir=tmp_path / "demo", demo=True, scenario="explorer")
    )
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    return application, runtime


def _library_runtime(qapp, tmp_path: Path) -> tuple[Any, _Runtime]:
    application = create_application(["mtee"])
    runtime = _build_runtime(
        application, AppOptions(data_dir=tmp_path / "data", demo=False, scenario="explorer")
    )
    assert runtime is not None
    window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
    window.resize(1440, 900)
    return application, runtime


def _counted_listening(track_id: str, path: str, started: datetime) -> PlayEvent:
    return PlayEvent(
        event_id=str(uuid4()),
        track=PlayedTrack(track_id=track_id, path=path, artist="Example", title="T", album="A"),
        started_at=started,
        ended_at=started + timedelta(seconds=45),
        heard_ms=45_000,
        counted=True,
    )


def test_every_settings_category_shows_its_page(qapp, tmp_path: Path) -> None:
    _application, runtime = _demo_runtime(qapp, tmp_path)
    try:
        window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
        cast(DemoWorkspace, runtime.workspace).openSettings()
        QTest.qWait(100)
        view = _first(window.contentItem(), "settingsView")

        for key, page in CATEGORY_PAGES.items():
            _click(window, _first(view, f"settingsTab_{key}"))
            assert _first(view, page).isVisible(), key
            others = [name for other, name in CATEGORY_PAGES.items() if other != key]
            assert not any(_first(view, name).isVisible() for name in others), key
    finally:
        _shutdown(runtime)


def test_the_retired_settings_are_gone(qapp, tmp_path: Path) -> None:
    _application, runtime = _demo_runtime(qapp, tmp_path)
    try:
        window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
        cast(DemoWorkspace, runtime.workspace).openSettings()
        QTest.qWait(100)
        view = _first(window.contentItem(), "settingsView")
        for key in CATEGORY_PAGES:
            _click(window, _first(view, f"settingsTab_{key}"))
            texts = " ".join(_texts(view))
            assert "Remember the queue" not in texts, key
            assert "Appearance" not in texts, key
            assert "Density" not in texts, key
            assert "Playlist creator name" not in texts, key
    finally:
        _shutdown(runtime)


def test_the_profile_button_opens_the_profile_tab(qapp, tmp_path: Path) -> None:
    _application, runtime = _demo_runtime(qapp, tmp_path)
    try:
        window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
        _click(window, _first(window.contentItem(), "activity-profile"))
        QTest.qWait(100)

        assert _first(window.contentItem(), "profilePage").isVisible()
        assert "The profile is not available in the demo." in _texts(window.contentItem())
    finally:
        _shutdown(runtime)


def test_the_listening_columns_and_details_show_the_play_log(qapp, tmp_path: Path) -> None:
    _application, runtime = _library_runtime(qapp, tmp_path)
    try:
        root_id, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 3)
        PlayLogRepository(runtime.database).insert_events(
            [_counted_listening(track_ids[0], "track-000.wav", datetime.now(UTC))],
            str(uuid4()),
        )
        workspace = open_folder(runtime, root_id)
        tab_id = f"folder:{root_id}/"
        _settle(runtime)
        model = cast(
            TrackListModel,
            workspace.trackModelForTab(tab_id, "folder", f"{root_id}/", "fileCreatedAt", False),
        )
        played = next(row for row in model.rows_snapshot() if row["id"] == track_ids[0])
        assert "playCount" not in played  # hidden by default: the figures are not read

        workspace.toggleColumn(tab_id, "playCount")
        workspace.toggleColumn(tab_id, "lastPlayed")
        _settle(runtime)
        rows = {row["id"]: row for row in model.rows_snapshot()}
        assert rows[track_ids[0]]["playCount"] == 1
        assert rows[track_ids[0]]["lastPlayedText"] != "—"
        assert rows[track_ids[1]]["playCount"] == 0
        assert rows[track_ids[1]]["lastPlayedText"] == "—"

        workspace.selectTrack(track_ids[0], "single", [])
        _settle(runtime)
        assert workspace.property("infoListening")[0] == {"label": "Plays", "value": "1"}
    finally:
        _shutdown(runtime)


def test_the_profile_page_reads_the_real_statistics(qapp, tmp_path: Path) -> None:
    _application, runtime = _library_runtime(qapp, tmp_path)
    try:
        PlayLogRepository(runtime.database).insert_events(
            [_counted_listening(str(uuid4()), "x.wav", datetime.now(UTC))], str(uuid4())
        )
        statistics = cast(QObject, runtime.engine.rootContext().contextProperty("statistics"))
        assert statistics is not None
        assert statistics.property("period") == "month"
        statistics.refresh()
        _settle(runtime)

        assert statistics.property("countedPlays") == 1
        assert statistics.property("listeningMs") == 45_000
        assert statistics.property("loading") is False
    finally:
        _shutdown(runtime)


def test_the_library_rules_come_from_the_real_store(qapp, tmp_path: Path) -> None:
    # The rule is stored before the application starts, as a choice made in an earlier session.
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    CreditOverrideRepository(database).set_mode("Alpha & Beta", MODE_SPLIT)
    database.close()
    _application, runtime = _library_runtime(qapp, tmp_path)
    try:
        rules = cast(QObject, runtime.engine.rootContext().contextProperty("artistRules"))
        assert rules is not None
        _settle(runtime)

        assert rules.property("rules") == [
            {
                "id": "alpha & beta",
                "text": "Alpha & Beta",
                "decision": "Split into separate artists",
            }
        ]
    finally:
        _shutdown(runtime)

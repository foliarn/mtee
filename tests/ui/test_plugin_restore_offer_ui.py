"""A backup offered by a plugin opens the usual restore confirmation in Settings (plan 125.6)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_settings_profile_ui import _first, _library_runtime, _settle, _texts

from mtee.app import _show_proposed_restore, _shutdown
from mtee.models.data_privacy_model import DataPrivacyModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.services.data_privacy import RestoreLayout, read_pending_restore


def test_an_offered_backup_opens_the_confirmation_and_schedules_nothing_before_it(
    qapp, tmp_path: Path
) -> None:
    _application, runtime = _library_runtime(qapp, tmp_path)
    try:
        window = cast(QQuickWindow, runtime.engine.rootObjects()[0])
        privacy = cast(
            DataPrivacyModel, runtime.engine.rootContext().contextProperty("dataPrivacy")
        )
        backup = tmp_path / "offered.sqlite3"
        runtime.database.backup_to(backup)

        _show_proposed_restore(cast(WorkspaceModel, runtime.workspace), privacy, backup)
        QTest.qWait(200)
        _settle(runtime)

        view = _first(window.contentItem(), "settingsView")
        assert _first(view, "privacySettings").isVisible()
        assert _first(view, "privacyScrim").isVisible()
        assert any("Restore from offered.sqlite3?" in text for text in _texts(view))
        assert _first(view, "dialogSchedule").isVisible()
        assert read_pending_restore(RestoreLayout(tmp_path / "data")) is None
        assert cast(QObject, privacy).property("busy") is False
    finally:
        _shutdown(runtime)

"""Settings > Remote in the real window, started with ``--plugin-dir plugins`` (plan 126.1).

The window shows the Server, This computer, Sync and Settings that travel groups; the folder and
backup groups are not drawn yet. The device rows are checked on their own.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
)
from mtee.plugins.remote.ui import (  # pyright: ignore[reportMissingImports]
    settings_backend,
)
from mtee.plugins.remote.ui.settings_backend import (  # pyright: ignore[reportMissingImports]
    SettingsBackend,
    device_rows,
    last_seen_text,
)
from tests.helpers.ui_plugin import (
    find_item,
    need_item,
    settle,
    start_app,
    visible_texts,
    window_of,
    workspace_of,
)
from tests.plugins.remote.conftest import PLUGIN_DIR
from tests.plugins.remote.helpers import FakeLibrary, make_context

from mtee.app import _shutdown

REMOTE_PAGE = "plugin:remote.remote"


def test_settings_remote_shows_the_server_and_this_computer_groups(
    qapp: object, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.openSettings()
        workspace.setSettingsPage(REMOTE_PAGE)
        settle(runtime)

        texts = visible_texts(window)
        for expected in (
            "Server",
            "Server address",
            "User name",
            "Password",
            "Connection",
            "Not connected.",
            "This computer",
            "Device name",
            "Connect",
        ):
            assert expected in texts, expected
        for group in ("remoteGroupServer", "remoteGroupComputer"):
            assert find_item(window, group) is not None, group
        assert find_item(window, "remoteServer") is not None
        assert find_item(window, "remoteConnection") is not None
        assert need_item(window, "action_remoteConnection").isVisible()
        assert find_item(window, "remoteGroupSync") is not None
        assert "Sync mode" in texts
        # Settings that travel (plan 126.7): one switch per synced setting, drawn in this page.
        assert find_item(window, "remoteGroupTravel") is not None
        assert "Settings that travel" in texts
        assert "Display name" in texts
        assert "Loudness normalization" in texts
        for not_yet in ("Folders", "Backups"):
            assert not_yet not in texts, not_yet
    finally:
        _shutdown(runtime)


def test_sync_group_has_the_pull_settings_and_the_idle_delay_in_minutes(
    qapp: object, tmp_path: Path
) -> None:
    """Plan 126.4: Auto pull, Download new server tracks, Fetch, and the idle delay in minutes."""
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.openSettings()
        workspace.setSettingsPage(REMOTE_PAGE)
        settle(runtime)

        texts = visible_texts(window)
        for expected in (
            "Auto pull",
            "Download new server tracks",
            "File idle delay (minutes)",
        ):
            assert expected in texts, expected
        assert "File idle delay (seconds)" not in texts
        assert need_item(window, "remoteAutoPull").property("checked") is False
        assert need_item(window, "remoteDownloadNew").property("checked") is False
        assert need_item(window, "remoteIdleDelay").property("value") == 2
        assert find_item(window, "remoteFetch") is not None
    finally:
        _shutdown(runtime)


def test_device_rows_name_this_computer_and_the_others() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    raw = [
        {
            "device_id": "d1",
            "name": "Studio laptop",
            "kind": "desktop",
            "last_seen_utc": "2026-11-03T11:59:00Z",
            "current": True,
        },
        {
            "device_id": "d2",
            "name": "Desk PC",
            "kind": "desktop",
            "last_seen_utc": "2026-11-01T12:00:00Z",
            "current": False,
        },
        {
            "device_id": "d3",
            "name": "Phone",
            "kind": "phone",
            "last_seen_utc": "2026-10-01T12:00:00Z",
            "current": False,
        },
    ]
    rows = device_rows(raw, now)
    assert rows[0] == {
        "deviceId": "d1",
        "name": "Studio laptop",
        "kind": "desktop",
        "kindText": "Windows",
        "lastSeen": "connected now",
        "current": True,
    }
    assert rows[1]["lastSeen"] == "last seen 2 days ago"
    assert rows[1]["current"] is False
    assert rows[2]["kindText"] == "Phone"
    assert rows[2]["lastSeen"] == "last seen on 2026-10-01"


def test_last_seen_text_reads_each_age() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    assert last_seen_text("2026-11-03T11:59:30Z", now) == "last seen just now"
    assert last_seen_text("2026-11-03T11:30:00Z", now) == "last seen 30 min ago"
    assert last_seen_text("2026-11-03T09:00:00Z", now) == "last seen 3 h ago"
    assert last_seen_text("2026-11-02T12:00:00Z", now) == "last seen 1 day ago"
    assert last_seen_text("not a time", now) == "last seen at an unknown time"


def test_the_folder_editor_asks_for_a_local_subfolder_before_the_server_one() -> None:
    """Plan 129.1: the editor has the local subfolder field, then the server subfolder field.

    The folder rows only show when this computer is connected to a server, so the window test
    cannot reach them; the editor is checked in its source, and its save in the backend below.
    """
    text = (PLUGIN_DIR / "remote" / "ui" / "settings.qml").read_text(encoding="utf-8")
    assert text.index('objectName: "remoteLocalSubfolder"') < text.index(
        'objectName: "remoteSubfolder"'
    )
    assert 'label: "Local subfolder"' in text
    assert 'label: "Server subfolder"' in text
    assert (
        "page.backend.saveFolder(folderEntry.modelData.path, page.editRootId, "
        "page.editLocalSubpath, page.editSubpath)" in text
    )


def _run_inline(
    context: object, label: str, work: Callable[[object], Any], done: Callable[..., None], **_: Any
) -> None:
    """Run a job at once and call back at once: the save is then done when the call returns."""
    done(work(None), None)


def test_saving_a_folder_stores_its_local_subfolder_and_refuses_a_missing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = tmp_path / "Music"
    (local / "baile").mkdir(parents=True)
    notices: list[str] = []
    library = FakeLibrary([local], [])
    context = dataclasses.replace(make_context(tmp_path / "plugin", library), notify=notices.append)
    monkeypatch.setattr(settings_backend, "submit", _run_inline)
    backend = SettingsBackend(context, MagicMock(), MagicMock(), MagicMock())
    kept = FolderMapping(str(local), "root-1", "Incoming", "baile")

    backend.saveFolder(str(local), "root-1", "baile", "Incoming")
    assert RemoteStore(context).mappings() == [kept]

    backend.saveFolder(str(local), "root-1", "nowhere", "")
    assert notices == ["The local subfolder nowhere does not exist in this watched folder."]
    assert RemoteStore(context).mappings() == [kept], "a refused save changes nothing"

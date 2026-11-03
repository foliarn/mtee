"""The filter "Hide tracks not on this device" in the real window (plan 125.3).

The sample plugin provides the track of its HTTP server, which is not on this computer, and its
``TrackAvailability`` marks it remote. The gear menu of a playlist shows the item only while the
sample runs; the item and the Library setting drive the same choice, and the meta line counts
what is hidden. Without a plugin nothing of it is drawn.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtQuick import QQuickWindow
from tests.helpers.ui_plugin import (
    click,
    find_item,
    need_item,
    settle,
    start_app,
    visible_texts,
    window_of,
    workspace_of,
)
from tests.plugins.test_contract import SAMPLE
from tests.ui.track_list_fixtures import add_folder_tracks, open_folder, row_item

from mtee.app import _Runtime, _shutdown
from mtee.models.availability_filter import SETTING_HIDE_NOT_ON_DEVICE
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.settings_repository import SettingsRepository

_LOCAL_COUNT = 2


def _served_track(runtime: _Runtime) -> str:
    """Store the sample's track served over HTTP, and return its track identifier."""
    assert runtime.plugins is not None
    record = next(item for item in runtime.plugins.plugins if item.plugin_id == SAMPLE.plugin_id)
    service = cast(Any, record.service)
    return str(service.provide_tracks(b"not really audio", 3_000_000)["sample-url-track"])


def _playlist_with(runtime: _Runtime, workspace: WorkspaceModel, track_ids: list[str]) -> str:
    """Create a local playlist holding ``track_ids`` and open it; return its identifier."""
    playlists = cast(Any, workspace).playlistModel
    playlists.create("Mix", "", track_ids)
    settle(runtime)
    identity = next(item["id"] for item in playlists._playlists if item["name"] == "Mix")
    workspace.openPlaylist(identity)
    settle(runtime)
    return str(identity)


def _open_gear(window: QQuickWindow) -> None:
    click(window, need_item(window, "chooseColumnsButton"))


def _note_shown(window: QQuickWindow, count: int) -> bool:
    return any(f"{count} hidden" in text for text in visible_texts(window))


def test_the_gear_item_hides_the_remote_track_and_the_note_counts_it(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (SAMPLE.folder,), (SAMPLE.plugin_id,))
    try:
        workspace = cast(WorkspaceModel, workspace_of(runtime))
        window = window_of(runtime)
        assert workspace.availabilityProvided is True
        served = _served_track(runtime)
        _root_id, local = add_folder_tracks(runtime, tmp_path / "audio", _LOCAL_COUNT)
        _playlist_with(runtime, workspace, [served, *local])

        # Before the filter: three rows, no note.
        assert row_item(window, 3) is not None
        assert not _note_shown(window, 1)

        # The gear menu offers the item, and the Library setting is there too.
        _open_gear(window)
        item = need_item(window, "hideNotOnDevice")
        assert item.isVisible()
        click(window, item)
        settle(runtime)
        assert workspace.hideNotOnDevice is True
        assert SettingsRepository(runtime.database).get_json(SETTING_HIDE_NOT_ON_DEVICE) is True
        assert row_item(window, 3) is None and row_item(window, 2) is not None
        assert _note_shown(window, 1)

        # The same choice again from the gear menu brings the row back and removes the note.
        _open_gear(window)
        click(window, need_item(window, "hideNotOnDevice"))
        settle(runtime)
        assert workspace.hideNotOnDevice is False
        assert row_item(window, 3) is not None
        assert not _note_shown(window, 1)
    finally:
        _shutdown(runtime)


def test_the_settings_toggle_follows_the_same_choice(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (SAMPLE.folder,), (SAMPLE.plugin_id,))
    try:
        workspace = cast(WorkspaceModel, workspace_of(runtime))
        window = window_of(runtime)
        workspace.openSettings()
        settle(runtime)
        workspace.setSettingsPageForGroup(workspace.activeGroup, "library")
        settle(runtime)
        toggle = need_item(window, "hideNotOnDeviceSetting")
        assert toggle.isVisible()
        assert workspace.hideNotOnDevice is False
        workspace.setHideNotOnDevice(True)  # what the switch calls
        settle(runtime)
        assert SettingsRepository(runtime.database).get_json(SETTING_HIDE_NOT_ON_DEVICE) is True
    finally:
        _shutdown(runtime)


def test_without_a_provider_the_item_is_absent_and_the_rows_stay(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        workspace = cast(WorkspaceModel, workspace_of(runtime))
        window = window_of(runtime)
        assert workspace.availabilityProvided is False
        root_id, _local = add_folder_tracks(runtime, tmp_path / "audio", _LOCAL_COUNT)
        open_folder(runtime, root_id)
        settle(runtime)
        assert row_item(window, _LOCAL_COUNT) is not None

        _open_gear(window)
        assert find_item(window, "columnOption_title") is not None  # the menu is open
        hidden_item = find_item(window, "hideNotOnDevice")
        assert hidden_item is None or not hidden_item.isVisible()
        assert not _note_shown(window, 1)

        workspace.openSettings()
        settle(runtime)
        workspace.setSettingsPageForGroup(workspace.activeGroup, "library")
        settle(runtime)
        setting = find_item(window, "hideNotOnDeviceSetting")
        assert setting is None or not setting.isVisible()
    finally:
        _shutdown(runtime)

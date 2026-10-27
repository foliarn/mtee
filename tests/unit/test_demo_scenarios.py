"""Pure checks for the deterministic review scenarios and the demo workspace."""

from __future__ import annotations

from typing import Any

import pytest

from mtee.demo.library import TRACKS
from mtee.demo.scenarios import SCENARIO_NAMES, load_scenario
from mtee.models.demo_workspace import ACTIVITIES, DemoWorkspace, format_duration


def _workspace(name: str) -> Any:
    """Return a workspace typed loosely: Qt properties read as plain values."""
    return DemoWorkspace(name)


def test_every_review_scenario_has_a_known_visual_state() -> None:
    track_ids = {track.track_id for track in TRACKS}
    for name in SCENARIO_NAMES:
        scenario = load_scenario(name)
        assert scenario.name == name
        assert scenario.activity in ACTIVITIES
        assert len(scenario.groups) == len(scenario.active_tabs)
        assert set(scenario.selected) <= track_ids
        assert scenario.playing in track_ids
        workspace = _workspace(name)
        assert workspace.scenarioName == name


def test_scenarios_are_deterministic_and_do_not_share_mutable_state() -> None:
    first = _workspace("explorer-multi")
    second = _workspace("explorer-multi")

    first.selectTrack("dnb02", "toggle", [])

    assert first.selectedIds != second.selectedIds
    assert second.selectedIds == ["dnb01", "dnb04", "dnb06"]


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown demo scenario"):
        load_scenario("made-up-state")


def test_duration_format() -> None:
    assert format_duration(94) == "1:34"
    assert format_duration(3725) == "1:02:05"


def test_the_active_activity_toggles_the_sidebar() -> None:
    workspace = _workspace("explorer")

    workspace.setActivity("explorer")
    assert workspace.sidebarVisible is False

    workspace.setActivity("playlists")
    assert workspace.sidebarVisible is True
    assert workspace.activity == "playlists"


def test_placeholder_activities_exist_without_behaviour() -> None:
    workspace = _workspace("explorer")
    groups_before = workspace.groups

    workspace.setActivity("plugins")

    assert workspace.activity == "plugins"
    assert workspace.groups == groups_before


def test_profile_opens_a_tab_and_is_not_an_activity() -> None:
    workspace = _workspace("explorer")
    assert "profile" not in ACTIVITIES

    workspace.openProfile()
    group = workspace.groups[workspace.activeGroup]
    assert group["active"] == "profile:"
    assert "profile:" in [tab["id"] for tab in group["tabs"]]


def test_tabs_open_close_and_split_like_an_editor() -> None:
    workspace = _workspace("explorer")

    workspace.openFolder("techno")
    assert workspace.groups[0]["active"] == "folder:techno"

    workspace.toggleSplit()
    assert len(workspace.groups) == 2
    assert workspace.activeGroup == 1

    workspace.closeTab(1, "folder:techno")
    assert len(workspace.groups) == 1

    workspace.openSettings()
    workspace.openConvert()  # the Convert plugin is not part of this build: no tab opens
    tabs = [tab["id"] for tab in workspace.groups[0]["tabs"]]
    assert tabs[-1:] == ["settings:"]


def test_double_click_plays_and_captures_the_visible_order() -> None:
    workspace = _workspace("explorer")
    workspace.setSort("folder:dnb", "title")
    visible = [row["id"] for row in workspace.tabTracks("folder", "dnb", "title", True, 0)]

    workspace.playTrack(visible[0], "folder:dnb")

    assert workspace.playingId == visible[0]
    assert workspace.isPlaying is True
    assert [track["id"] for track in workspace.upNext] == visible[1:]


def test_queue_order_survives_a_sort_change() -> None:
    workspace = _workspace("explorer")
    workspace.playTrack("dnb01", "folder:dnb")
    before = [track["id"] for track in workspace.upNext]

    workspace.setSort("folder:dnb", "title")

    assert [track["id"] for track in workspace.upNext] == before


def test_selection_is_independent_from_playback() -> None:
    workspace = _workspace("explorer")
    workspace.selectTrack("dnb07", "single", [])

    assert workspace.playingId == "dnb02"
    assert workspace.selectedIds == ["dnb07"]


def test_range_selection_follows_the_given_order() -> None:
    workspace = _workspace("explorer")
    order = ["dnb01", "dnb02", "dnb03", "dnb04", "dnb05"]
    workspace.selectTrack("dnb02", "single", order)
    workspace.selectTrack("dnb04", "range", order)

    assert workspace.selectedIds == ["dnb02", "dnb03", "dnb04"]


def test_transport_modes_and_position() -> None:
    workspace = _workspace("explorer")

    workspace.toggleShuffle()
    assert workspace.shuffle is True
    workspace.cycleRepeat()
    assert workspace.repeat == "all"
    workspace.cycleRepeat()
    assert workspace.repeat == "one"

    workspace.seek(10_000)
    assert workspace.position == float(workspace.playingTrack["seconds"])
    workspace.tick(1)
    assert workspace.position == 0.0
    assert workspace.playingId == "dnb02"


def test_next_advances_and_history_remembers() -> None:
    workspace = _workspace("explorer")
    workspace.playTrack("dnb01", "folder:dnb")

    workspace.next()

    assert workspace.playingId == "dnb02"
    assert workspace.history[0]["id"] == "dnb01"


def test_saving_a_field_changes_only_that_field() -> None:
    workspace = _workspace("explorer")
    workspace.selectTrack("dnb03", "single", [])

    workspace.commitField("genre", "Rollers")
    assert workspace.saveState == "saving"
    workspace.finishSave()

    track = workspace.track("dnb03")
    assert workspace.saveState == "saved"
    assert track["genre"] == "Rollers"
    assert track["title"] == "Low Orbit"

    workspace.undoSave()
    assert workspace.track("dnb03")["genre"] == "Liquid"
    assert workspace.saveState == "idle"


def test_multi_selection_shows_mixed_values_and_a_failed_save_keeps_the_input() -> None:
    workspace = _workspace("explorer-multi")
    fields = {field["key"]: field for field in workspace.infoFields}
    assert fields["title"]["mixed"] is True
    assert fields["year"]["mixed"] is False

    workspace.commitField("genre", "Breaks")
    workspace.finishSave()

    assert workspace.saveState == "error"
    fields = {field["key"]: field for field in workspace.infoFields}
    assert fields["genre"]["value"] == "Breaks"
    assert fields["title"]["mixed"] is True
    assert workspace.track("dnb01")["genre"] == "Drum & Bass"

    workspace.retrySave()
    workspace.finishSave()
    assert workspace.saveState == "saved"
    assert {workspace.track(tid)["genre"] for tid in ("dnb01", "dnb04", "dnb06")} == {"Breaks"}
    assert workspace.track("dnb04")["title"] == "Feel This Pressure"


def test_add_to_playlist_toggles_membership() -> None:
    workspace = _workspace("explorer")

    workspace.togglePlaylist(["dnb01"], "warmup")
    assert "warmup" in workspace.playlistsContaining("dnb01", 0)

    workspace.togglePlaylist(["dnb01"], "warmup")
    assert "warmup" not in workspace.playlistsContaining("dnb01", 0)

    workspace.addToNewPlaylist(["dnb01", "dnb02"])
    assert workspace.playlists[-1]["count"] == 2


def test_fullscreen_and_island_switches() -> None:
    workspace = _workspace("explorer")

    workspace.setFullscreen(True)
    assert workspace.fullscreen is True
    workspace.setActivity("playlists")
    assert workspace.fullscreen is False

    workspace.setIslandEnabled(False)
    assert workspace.islandEnabled is False


def test_info_and_queue_share_the_right_panel() -> None:
    workspace = _workspace("explorer")

    workspace.showRightPanel("info")
    assert (workspace.rightPanelVisible, workspace.rightPanelTab) == (True, "info")
    workspace.toggleRightPanel("queue")
    assert workspace.rightPanelTab == "queue"
    workspace.toggleRightPanel("queue")
    assert workspace.rightPanelVisible is False


def test_the_convert_scenarios_are_not_offered_in_this_build() -> None:
    assert "convert" not in ACTIVITIES
    assert "convert" not in SCENARIO_NAMES
    with pytest.raises(ValueError):
        _workspace("convert-error")

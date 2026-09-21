"""Pure checks for the deterministic review scenarios."""

from __future__ import annotations

import pytest

from mtee.demo.scenarios import SCENARIO_NAMES, load_scenario
from mtee.models.demo_workspace import DemoWorkspace


def test_every_review_scenario_has_a_known_visual_state() -> None:
    for name in SCENARIO_NAMES:
        scenario = load_scenario(name)
        assert scenario.name == name
        assert scenario.screen in {"browser", "listening", "convert"}
        assert scenario.selected_rows


def test_scenarios_are_deterministic_and_do_not_share_mutable_state() -> None:
    first = DemoWorkspace("browser-multi")
    second = DemoWorkspace("browser-multi")

    first.selectRow(1, True)

    assert first.selectedRows != second.selectedRows
    assert second.selectedRows == [0, 2, 4]
    assert first.tracks == second.tracks


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown demo scenario"):
        load_scenario("made-up-state")


def test_workspace_actions_only_change_in_memory_state() -> None:
    workspace = DemoWorkspace("browser")

    workspace.setScreen("listening")
    workspace.setSaveState("saving")
    workspace.setInspectorVisible(True)

    assert workspace.screen == "listening"
    assert workspace.saveState == "saving"
    assert workspace.inspectorVisible is True

"""Scenario definitions for the UX prototype.

The scenarios are deliberately small and deterministic. They describe what a
reviewer sees; they do not model an audio file, call a service or touch disk.
A tab is written ``kind:ref``, for example ``folder:dnb`` or ``settings:``. The Convert
scenarios belong to the conversion plugin and are not offered in this build.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

__all__ = ["DEFAULT_SCENARIO", "SCENARIO_NAMES", "DemoScenario", "load_scenario"]


@dataclass(frozen=True, slots=True)
class DemoScenario:
    """Complete visual state for one reviewable prototype scenario."""

    name: str
    activity: str = "explorer"
    sidebar_visible: bool = True
    groups: tuple[tuple[str, ...], ...] = (("folder:dnb", "folder:ukg"),)
    active_tabs: tuple[str, ...] = ("folder:dnb",)
    artwork_tabs: tuple[str, ...] = ()
    right_panel: str = ""
    fullscreen: bool = False
    selected: tuple[str, ...] = ("dnb03",)
    playing: str = "dnb02"
    playing_source: str = "folder:dnb"
    is_playing: bool = True
    position: int = 94
    shuffle: bool = False
    repeat: str = "off"
    save_fails: bool = False
    conversion_error: bool = False
    island_enabled: bool = True


DEFAULT_SCENARIO = "explorer"

SCENARIO_NAMES = (
    "explorer",
    "explorer-info",
    "explorer-split",
    "explorer-multi",
    "explorer-no-artwork",
    "playing-queue",
    "fullscreen",
    "tasks",
    "playlists",
    "settings",
)

_SCENARIOS = {
    "explorer": DemoScenario(name="explorer"),
    "explorer-info": DemoScenario(name="explorer-info", right_panel="info"),
    "explorer-split": DemoScenario(
        name="explorer-split",
        groups=(("folder:dnb",), ("folder:ukg", "playlist:peak")),
        active_tabs=("folder:dnb", "folder:ukg"),
    ),
    "explorer-multi": DemoScenario(
        name="explorer-multi",
        right_panel="info",
        selected=("dnb01", "dnb04", "dnb06"),
        save_fails=True,
    ),
    "explorer-no-artwork": DemoScenario(
        name="explorer-no-artwork",
        groups=(("folder:dnb", "folder:samples"),),
        active_tabs=("folder:samples",),
        artwork_tabs=("folder:samples",),
        selected=("smp02",),
    ),
    "playing-queue": DemoScenario(
        name="playing-queue", right_panel="queue", shuffle=True, repeat="all", position=187
    ),
    "fullscreen": DemoScenario(name="fullscreen", fullscreen=True, position=131),
    "tasks": DemoScenario(name="tasks", activity="tasks"),
    "playlists": DemoScenario(
        name="playlists",
        activity="playlists",
        groups=(("folder:dnb", "playlist:peak"),),
        active_tabs=("playlist:peak",),
        selected=("dnb10",),
        playing="dnb06",
        playing_source="playlist:peak",
    ),
    "settings": DemoScenario(
        name="settings",
        groups=(("folder:dnb", "settings:"),),
        active_tabs=("settings:",),
    ),
}


def load_scenario(name: str) -> DemoScenario:
    """Return a fresh immutable state for ``name``.

    Unknown names fail early so a typo cannot silently produce a different
    review state.
    """
    try:
        return replace(_SCENARIOS[name])
    except KeyError as error:
        available = ", ".join(SCENARIO_NAMES)
        raise ValueError(f"Unknown demo scenario {name!r}; choose one of: {available}") from error

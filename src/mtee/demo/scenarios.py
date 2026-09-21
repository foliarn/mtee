"""Scenario definitions for the UX prototype.

The scenarios are deliberately small and deterministic. They describe what a
reviewer sees; they do not model an audio file, call a service or touch disk.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

__all__ = ["SCENARIO_NAMES", "DemoScenario", "load_scenario"]


@dataclass(frozen=True, slots=True)
class DemoScenario:
    """Complete visual state for one reviewable prototype scenario."""

    name: str
    screen: str = "browser"
    inspector_visible: bool = False
    split_view: bool = True
    artwork_view: bool = False
    multi_selection: bool = False
    no_artwork: bool = False
    save_state: str = "idle"
    conversion_error: bool = False
    selected_rows: tuple[int, ...] = (0,)
    playing_row: int = 1


SCENARIO_NAMES = (
    "browser",
    "browser-inspector",
    "browser-split",
    "browser-multi",
    "browser-no-artwork",
    "listening",
    "convert",
    "convert-error",
)

_SCENARIOS = {
    "browser": DemoScenario(name="browser", split_view=False),
    "browser-inspector": DemoScenario(
        name="browser-inspector", inspector_visible=True, split_view=False
    ),
    "browser-split": DemoScenario(name="browser-split", split_view=True),
    "browser-multi": DemoScenario(
        name="browser-multi",
        inspector_visible=True,
        multi_selection=True,
        selected_rows=(0, 2, 4),
        playing_row=3,
    ),
    "browser-no-artwork": DemoScenario(
        name="browser-no-artwork", artwork_view=True, no_artwork=True, split_view=False
    ),
    "listening": DemoScenario(name="listening", screen="listening", playing_row=1),
    "convert": DemoScenario(name="convert", screen="convert", selected_rows=(0, 1)),
    "convert-error": DemoScenario(
        name="convert-error", screen="convert", conversion_error=True, selected_rows=(0, 1)
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

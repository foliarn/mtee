"""In-memory page history for one editor group."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class NavigationLocation:
    activity: str
    tab_id: str
    fullscreen: bool = False
    right_visible: bool = False
    right_tab: str = "info"
    settings_page: str = "general"
    view: dict[str, Any] = field(default_factory=dict)

    @property
    def destination(self) -> tuple[str, str, bool, bool, str, str]:
        return (
            self.activity,
            self.tab_id,
            self.fullscreen,
            self.right_visible,
            self.right_tab,
            self.settings_page,
        )


@dataclass(frozen=True, slots=True)
class NavigationHistory:
    locations: tuple[NavigationLocation, ...] = ()
    cursor: int = -1

    @property
    def current(self) -> NavigationLocation | None:
        if 0 <= self.cursor < len(self.locations):
            return self.locations[self.cursor]
        return None

    @property
    def can_back(self) -> bool:
        return self.cursor > 0

    @property
    def can_forward(self) -> bool:
        return 0 <= self.cursor < len(self.locations) - 1

    def capture(self, location: NavigationLocation) -> NavigationHistory:
        if self.current is None:
            return self
        updated = list(self.locations)
        updated[self.cursor] = location
        return replace(self, locations=tuple(updated))

    def visit(self, location: NavigationLocation) -> NavigationHistory:
        if self.current is not None and self.current.destination == location.destination:
            return self.capture(location)
        return NavigationHistory((*self.locations[: self.cursor + 1], location), self.cursor + 1)

    def back(self) -> NavigationHistory:
        return replace(self, cursor=self.cursor - 1) if self.can_back else self

    def forward(self) -> NavigationHistory:
        return replace(self, cursor=self.cursor + 1) if self.can_forward else self

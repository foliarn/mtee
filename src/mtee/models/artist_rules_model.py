"""Qt model of the artist name rules shown in the Settings Library category (plan 114).

The rules are the choices made on credits in the Artists view and in the tag editor
("This is one artist" or "Split into separate artists"). They are read from and removed
through the core artist index service, the same store the Artists view uses.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.artist_index import MODE_ONE_ARTIST
from mtee.services.artist_index_service import ArtistIndexService

__all__ = ["ArtistRulesModel"]

_DECISIONS = {
    MODE_ONE_ARTIST: "This is one artist",
}
_SPLIT_DECISION = "Split into separate artists"


class ArtistRulesModel(QObject):
    """Expose the saved name rules to the Settings page and remove them."""

    changed = Signal()

    def __init__(self, index: ArtistIndexService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._message = ""
        index.indexChanged.connect(self.changed.emit)

    @Property(list, notify=changed)
    def rules(self) -> list[dict[str, str]]:
        """One row per rule: its key, the name as typed, and the decision in words."""
        return [
            {
                "id": item["key"],
                "text": item["text"],
                "decision": _DECISIONS.get(item["mode"], _SPLIT_DECISION),
            }
            for item in self._index.overrides()
        ]

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._message

    @Slot(str)
    def removeRule(self, key: str) -> None:
        """Forget a rule; the names go back to the automatic grouping."""
        removed = self._index.remove_override(key)
        self._message = (
            "Rule removed. The name is grouped automatically again."
            if removed
            else "That rule no longer exists."
        )
        self.changed.emit()

"""What the conflict tab reads and calls: one snapshot per conflict, as JSON, and the choices.

The tab of ``ui/conflict.qml`` asks for ``load(ref)`` (the conflict id) and gets the snapshot as a
JSON text; ``changed(ref)`` tells it to ask again. ``choose(ref, action)`` runs a choice. The work
is in ``conflicts.ConflictFeature``. Graphical thread only.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal, Slot

from ..conflicts import ConflictFeature


class ConflictBackend(QObject):
    """The backend of the ``remote.conflict`` tab: one object for every conflict tab."""

    changed = Signal(str)

    def __init__(self, feature: ConflictFeature) -> None:
        super().__init__()
        self._feature = feature
        feature.changed.connect(self.changed)

    @Slot(str, result=str)
    def load(self, conflict_id: str) -> str:
        """The snapshot of a conflict as JSON; the first call starts reading both versions."""
        self._feature.load(conflict_id)
        return json.dumps(self._feature.snapshot(conflict_id), ensure_ascii=False)

    @Slot(str, str)
    def choose(self, conflict_id: str, action: str) -> None:
        self._feature.choose(conflict_id, action)

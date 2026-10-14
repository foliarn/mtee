"""Run Python's cyclic garbage collector on the graphical thread only.

CPython starts an automatic collection on whichever thread crosses the allocation
threshold, often a worker of a ``JobService``. A reference cycle that holds a Qt object
owned by Python, such as a discarded model and the closures connected to it, is then
destroyed on that worker. Qt cannot undo thread-bound registrations from there: the
native event filter of a ``QFileSystemWatcher`` stays in the event dispatcher of the
graphical thread after its memory is freed, and the next ``processEvents`` calls into it.

The collector turns the automatic collection off and runs the same generations, with
the same thresholds, from a timer of the graphical thread.
"""

from __future__ import annotations

import gc

import shiboken6
from PySide6.QtCore import QCoreApplication, QObject, QTimer, Slot

__all__ = ["CHECK_INTERVAL_MS", "MainThreadGarbageCollector", "install_main_thread_gc"]

CHECK_INTERVAL_MS = 1_000

_installed: MainThreadGarbageCollector | None = None


class MainThreadGarbageCollector(QObject):
    """Replace the automatic collection by a timer on the thread of ``parent``."""

    def __init__(self, parent: QObject, *, interval_ms: int = CHECK_INTERVAL_MS) -> None:
        super().__init__(parent)
        self._thresholds = gc.get_threshold()
        gc.disable()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.collect_if_due)
        self._timer.start()

    @Slot()
    def collect_if_due(self) -> int:
        """Collect the generations whose counters passed their threshold; return the count."""
        counts = gc.get_count()
        if counts[0] <= self._thresholds[0]:
            return 0
        generation = 0
        if counts[1] > self._thresholds[1]:
            generation = 2 if counts[2] > self._thresholds[2] else 1
        return gc.collect(generation)


def install_main_thread_gc(application: QCoreApplication) -> MainThreadGarbageCollector:
    """Install the collector on ``application`` once; later calls return the same one."""
    global _installed
    if (
        _installed is None
        or not shiboken6.isValid(_installed)
        or _installed.parent() is not application
    ):
        _installed = MainThreadGarbageCollector(application)
    return _installed

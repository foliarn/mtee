"""The cyclic garbage collector runs on the graphical thread only (plan 118)."""

from __future__ import annotations

import gc
import threading

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt

from mtee.services.jobs import JobContext, JobService
from mtee.services.main_thread_gc import install_main_thread_gc


class _Cyclic(QObject):
    """A Python-owned Qt object in a reference cycle, like a discarded model."""

    def __init__(self) -> None:
        super().__init__()
        # On Windows the watcher installs a native event filter on the graphical thread.
        self.watcher = QFileSystemWatcher(self)
        self.myself = self


def _allocate(_context: JobContext) -> None:
    # Enough container allocations to cross the threshold of an automatic collection.
    junk = [[index] for index in range(200_000)]
    del junk


def test_install_is_idempotent_and_turns_the_automatic_collection_off(qapp) -> None:
    collector = install_main_thread_gc(qapp)
    assert install_main_thread_gc(qapp) is collector
    assert collector.parent() is qapp
    assert not gc.isenabled()


def test_collect_if_due_frees_a_cycle_on_the_calling_thread(qapp) -> None:
    collector = install_main_thread_gc(qapp)
    gc.collect()
    threads: list[str] = []
    item = _Cyclic()
    item.destroyed.connect(
        lambda: threads.append(threading.current_thread().name),
        Qt.ConnectionType.DirectConnection,
    )
    del item
    kept = [[] for _ in range(2 * gc.get_threshold()[0])]  # past the threshold of generation 0
    assert collector.collect_if_due() > 0
    assert threads == [threading.main_thread().name]
    del kept


def test_a_worker_never_frees_a_discarded_qt_object(qapp, qtbot) -> None:
    jobs = JobService(qapp, max_thread_count=1)
    threads: list[str] = []
    for _ in range(3):
        item = _Cyclic()
        item.destroyed.connect(
            lambda: threads.append(threading.current_thread().name),
            Qt.ConnectionType.DirectConnection,
        )
        del item
        jobs.submit(_allocate, visible=False)
        assert jobs.wait_for_done(10_000)
        qtbot.wait(20)
    gc.collect()
    jobs.shutdown(1_000)
    assert threads == [threading.main_thread().name] * 3

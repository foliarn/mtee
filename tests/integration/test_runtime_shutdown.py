"""The process must not close SQLite underneath a worker that outlives timeout."""

from __future__ import annotations

import threading

from mtee.app import _shutdown_services
from mtee.persistence.database import Database
from mtee.services.jobs import JobService


def test_shutdown_keeps_database_open_if_worker_exceeds_deadline(tmp_path, monkeypatch) -> None:
    import mtee.app as app

    monkeypatch.setattr(app, "_SHUTDOWN_TIMEOUT_MS", 20)
    database = Database(tmp_path / "runtime.sqlite")
    database.migrate()
    jobs = JobService(max_thread_count=1)
    started = threading.Event()
    release = threading.Event()

    def stubborn(_context) -> None:
        started.set()
        release.wait(2)

    jobs.submit(stubborn, label="Controlled worker")
    assert started.wait(1)
    _shutdown_services(database, jobs, None)
    assert database.connection().execute("SELECT 1").fetchone()[0] == 1
    release.set()
    assert jobs.wait_for_done(1_000)
    database.close()

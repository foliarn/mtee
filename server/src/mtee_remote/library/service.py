"""The background library service: a scan thread and a hash thread."""

from __future__ import annotations

import logging
import queue
import threading
import time

from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.library import scanner

log = logging.getLogger(__name__)

_JOIN_TIMEOUT_S = 10.0
# The hash thread also looks at the database this often, so items added by another process
# (the `adopt-root` and `scan` commands) or by code that does not call `wake_hasher` are found.
_HASH_POLL_S = 10.0
_HASH_BATCH = 100


class LibraryService:
    """Scans the roots (at start, on request, on a timer) and hashes new files.

    Two daemon threads, each with its own database connection:

    - the scan thread scans every root at start and then every `settings.scan_interval_s`
      seconds, and any root passed to `request_scan`. `scan_interval_s == 0` disables the
      start scan and the timer; requests still work;
    - the hash thread runs `hash_pending` and sleeps when nothing is pending. A finished scan
      wakes it; code that adds pending items itself (the upload commit) calls `wake_hasher`.
    """

    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._stop = threading.Event()
        self._requests: queue.Queue[str | None] = queue.Queue()
        self._wake = threading.Event()
        self._busy_lock = threading.Lock()
        self._busy = 0  # scans queued or running
        self._threads: list[threading.Thread] = []

    # -- control --------------------------------------------------------------------

    def start(self) -> None:
        if self._threads:
            return
        if self._settings.scan_interval_s > 0:
            self._add_busy(1)  # the start scan counts as queued from now on
        self._threads = [
            threading.Thread(target=self._scan_loop, name="library-scan", daemon=True),
            threading.Thread(target=self._hash_loop, name="library-hash", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        """Ask both threads to stop and wait for them (10 s at most each)."""
        self._stop.set()
        self._requests.put(None)
        self._wake.set()
        for thread in self._threads:
            thread.join(_JOIN_TIMEOUT_S)
        self._threads = []

    def request_scan(self, root_id: str) -> None:
        """Queue a scan of one root; it runs on the scan thread, one scan at a time."""
        self._add_busy(1)
        self._requests.put(root_id)

    def wake_hasher(self) -> None:
        """Tell the hash thread that pending items may exist."""
        self._wake.set()

    # -- state ----------------------------------------------------------------------

    def status(self) -> dict[str, int | bool]:
        """Return `{scanning, pending, done, errors}`; the counts are of present items."""
        counts = {"pending": 0, "done": 0, "error": 0}
        for row in self._db.conn().execute(
            "SELECT hash_state, COUNT(*) AS n FROM items WHERE state = 'present'"
            " GROUP BY hash_state"
        ):
            counts[row["hash_state"]] = row["n"]
        with self._busy_lock:
            scanning = self._busy > 0
        return {
            "scanning": scanning,
            "pending": counts["pending"],
            "done": counts["done"],
            "errors": counts["error"],
        }

    def wait_idle(self, timeout: float) -> bool:
        """Wait until no scan is queued or running and nothing is pending (for tests)."""
        deadline = time.monotonic() + timeout
        while True:
            state = self.status()
            if not state["scanning"] and state["pending"] == 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)

    # -- threads --------------------------------------------------------------------

    def _add_busy(self, delta: int) -> None:
        with self._busy_lock:
            self._busy += delta

    def _root_ids(self) -> list[str]:
        return [row[0] for row in self._db.conn().execute("SELECT root_id FROM roots")]

    def _scan_one(self, root_id: str) -> None:
        try:
            result = scanner.scan_root(self._db, self._settings, root_id, stop=self._stop)
            log.info("Scan finished: %s", result)
        except Exception:
            log.exception("The scan of a root failed.")
        self._wake.set()

    def _scan_all(self) -> None:
        for root_id in self._root_ids():
            if self._stop.is_set():
                return
            self._scan_one(root_id)

    def _scan_loop(self) -> None:
        interval = self._settings.scan_interval_s
        try:
            if interval > 0:
                try:
                    self._scan_all()
                finally:
                    self._add_busy(-1)
            while not self._stop.is_set():
                try:
                    root_id = self._requests.get(timeout=interval if interval > 0 else None)
                except queue.Empty:
                    self._add_busy(1)
                    try:
                        self._scan_all()
                    finally:
                        self._add_busy(-1)
                    continue
                if root_id is None:
                    break
                try:
                    self._scan_one(root_id)
                finally:
                    self._add_busy(-1)
        finally:
            self._db.close()

    def _hash_loop(self) -> None:
        try:
            while not self._stop.is_set():
                self._wake.clear()
                try:
                    done = scanner.hash_pending(
                        self._db, self._settings, limit=_HASH_BATCH, stop=self._stop
                    )
                except Exception:
                    log.exception("Hashing failed.")
                    done = 0
                if done == 0:
                    self._wake.wait(_HASH_POLL_S)
        finally:
            self._db.close()

"""Housekeeping of the plugin's tables, at start and once a day (review of 0.3.0).

Three tables only grew:

- ``remote_queue`` kept every operation that was sent (``done``). They are deleted once they are
  older than ``DONE_KEPT``. The open rows (pending, running, blocked, failed) are never touched. A
  dismissed conflict reopens on a push queued after it was dismissed (``has_newer_push``); the
  conflicts are swept every minute, so a week of done rows is far more than that check needs.
- ``remote_log`` kept every line; the Remote window shows the last 100. The newest ``LOG_KEPT``
  lines stay.
- ``remote_hash_cache`` kept the hashes of files that were renamed or deleted. An entry whose path
  is neither a library track nor a download waiting to be linked (``remote_imports``) is deleted;
  the next pass hashes a file again if it comes back.

Nothing here reads or writes a music file. ``run`` takes the library paths from the core and works
on the plugin's tables only, in one transaction per table; it runs in a hidden job.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mtee.plugins.api import JobContext, PluginContext

from .store import RemoteStore

DONE_KEPT = timedelta(days=7)
LOG_KEPT = 1000
LAST_RUN_SETTING = "maintenance_at_utc"
EVERY = timedelta(days=1)
_CHUNK = 400


@dataclass(frozen=True)
class MaintenanceReport:
    done_deleted: int
    log_deleted: int
    hashes_deleted: int


def is_due(context: PluginContext, now: datetime | None = None) -> bool:
    """True when the last housekeeping is older than a day, or never ran."""
    text = context.settings.get(LAST_RUN_SETTING, "")
    try:
        last = datetime.fromisoformat(text) if text else None
    except ValueError:
        last = None
    current = now or datetime.now(UTC)
    return last is None or current - last >= EVERY


def run(
    context: PluginContext,
    store: RemoteStore,
    job: JobContext | None = None,
    now: datetime | None = None,
) -> MaintenanceReport:
    """Trim the three tables and remember when; a job thread (it reads the library paths)."""
    current = now or datetime.now(UTC)
    done = _prune_done(store, current - DONE_KEPT)
    log = _prune_log(store)
    if job is not None:
        job.raise_if_cancelled()
    hashes = _prune_hashes(context, store)
    context.settings.set(LAST_RUN_SETTING, current.isoformat(timespec="seconds"))
    return MaintenanceReport(done, log, hashes)


def _prune_done(store: RemoteStore, before: datetime) -> int:
    with store.transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM remote_queue WHERE state = 'done' AND updated_at_utc < ?",
            (before.isoformat(timespec="seconds"),),
        )
        return cursor.rowcount


def _prune_log(store: RemoteStore) -> int:
    with store.transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM remote_log WHERE log_id <= "
            "(SELECT log_id FROM remote_log ORDER BY log_id DESC LIMIT 1 OFFSET ?)",
            (LOG_KEPT,),
        )
        return cursor.rowcount


def _prune_hashes(context: PluginContext, store: RemoteStore) -> int:
    """Delete the cached hashes of paths that no library track and no waiting download has."""
    kept = {
        os.path.normcase(os.path.abspath(track.path))
        for track in context.library.tracks(context.library.track_ids())
    }
    conn = store.connection()
    for row in conn.execute("SELECT local_path FROM remote_imports"):
        kept.add(os.path.normcase(os.path.abspath(str(row["local_path"]))))
    stale = [
        str(row["path"])
        for row in conn.execute("SELECT path FROM remote_hash_cache")
        if str(row["path"]) not in kept
    ]
    if not stale:
        return 0
    with store.transaction() as write:
        for start in range(0, len(stale), _CHUNK):
            chunk = stale[start : start + _CHUNK]
            marks = ", ".join("?" for _ in chunk)
            write.execute(f"DELETE FROM remote_hash_cache WHERE path IN ({marks})", chunk)
    return len(stale)

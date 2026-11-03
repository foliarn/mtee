"""The Remote activity: the sidebar pane of the plugin (plan 126.9).

The pane has four sections, each a ``PluginRowsModel`` that ``RemoteActivity.refresh`` rebuilds
from the plugin's own tables:

- **Changes**: the queue of the sync (uploads, replacements and moves). A blocked or failed entry is
  in the warning tone. The section action Apply sends the queue now (``SyncEngine.apply_pending``).
- **Conflicts**: the open conflicts, with their reason. A click opens the conflict's tab.
- **Backups**: the ten newest backups of the server. The list is read by a job, at most every ten
  minutes, while the computer is connected.
- **Activity log**: the last 100 lines of ``remote_log``, newest first; a warning or an error is in
  the warning tone.

The header has Sync now (a pass of the engine) and Fetch (``SyncEngine.fetch_now``).

The counts are read by the core on ``refresh_ui``: the Changes section counts the operations to send
and the blocked ones, the Conflicts section counts the open conflicts, and the activity badge is the
open conflicts plus the blocked operations. Apply is a text button, drawn in Manual mode only. The
plugin asks for a refresh of the interface only when one of those values changed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from mtee.plugins.api import (
    Contribution,
    PaneAction,
    PluginActivity,
    PluginContext,
    PluginRowsModel,
    SidebarSection,
)

from .backups import backup_rows
from .conflicts import ConflictFeature
from .engine import CONNECTED, MANUAL, SyncEngine, SyncLink, sync_mode
from .push import BLOCKED, PENDING
from .store import RemoteStore
from .tasks import submit

ACTIVITY_ID = "remote"
ACTIVITY_TITLE = "Remote"
ACTIVITY_ICON = "cloud"
CHANGES_ID = "changes"
CONFLICTS_ID = "conflicts"
BACKUPS_ID = "backups"
LOG_ID = "log"
RECENT_BACKUPS = 10
LOG_LINES = 100
BACKUP_MAX_AGE = timedelta(minutes=10)
QUEUE_STATES = ("pending", "running", "blocked", "failed")
PROBLEM_STATES = ("blocked", "failed")
WARNING_LEVELS = ("warning", "error")
VERBS = {"upload": "Upload", "replace": "Replace", "move": "Move"}
UP_TO_DATE = "Everything is up to date"


class RemoteActivity:
    """The rows of the Remote activity, and the header and section actions of its pane."""

    def __init__(
        self,
        context: PluginContext,
        store: RemoteStore,
        engine: SyncEngine,
        conflicts: ConflictFeature,
        link: SyncLink,
    ) -> None:
        self._context = context
        self._store = store
        self._engine = engine
        self._conflicts = conflicts
        self._link = link
        self._models: dict[str, PluginRowsModel] = {
            CHANGES_ID: PluginRowsModel(),
            CONFLICTS_ID: PluginRowsModel(),
            BACKUPS_ID: PluginRowsModel(),
            LOG_ID: PluginRowsModel(),
        }
        self._backups: list[dict[str, Any]] = []
        self._backups_read_at: datetime | None = None
        self._reading_backups = False
        # The values the core showed on its last refresh; a change asks for a new one.
        self._shown: tuple[int, int, int, bool] | None = None

    def contributions(self) -> Sequence[Contribution]:
        """The activity and its four sections, as the plugin's factory returns them."""
        return [
            PluginActivity(
                ACTIVITY_ID,
                ACTIVITY_TITLE,
                ACTIVITY_ICON,
                actions=(
                    PaneAction("sync", "Sync now", "repeat", self._engine.request_pass),
                    PaneAction("fetch", "Fetch", "arrow-down", self._engine.fetch_now),
                ),
                badge=self._attention,
            ),
            SidebarSection(
                CHANGES_ID,
                "Changes",
                ACTIVITY_ID,
                self._models[CHANGES_ID],
                actions=(
                    PaneAction(
                        "apply",
                        "Apply pending changes",
                        "check",
                        self._engine.apply_pending,
                        label="Apply",
                        visible=self._is_manual,
                    ),
                ),
                count=self._queued,
            ),
            SidebarSection(
                CONFLICTS_ID,
                "Conflicts",
                ACTIVITY_ID,
                self._models[CONFLICTS_ID],
                activate=self._conflicts.run_waiting,
                count=self._conflicts.open_count,
            ),
            SidebarSection(BACKUPS_ID, "Backups", ACTIVITY_ID, self._models[BACKUPS_ID]),
            SidebarSection(LOG_ID, "Activity log", ACTIVITY_ID, self._models[LOG_ID]),
        ]

    def model(self, section_id: str) -> PluginRowsModel:
        return self._models[section_id]

    def refresh(self) -> None:
        """Read the four sections again; a backup list older than ten minutes is read again too."""
        conn = self._store.connection()
        self._models[CHANGES_ID].replace(self._change_rows())
        self._models[CONFLICTS_ID].replace(self._conflict_rows())
        self._models[BACKUPS_ID].replace(self._backup_rows())
        self._models[LOG_ID].replace(self._log_rows(conn))
        self._read_backups_if_due()
        # A move from pending to blocked keeps the queue count and changes the badge: compare all.
        state = (self._queued(), self._conflicts.open_count(), self._blocked(), self._is_manual())
        if state != self._shown:
            self._shown = state
            self._context.refresh_ui()

    # -- counts and buttons (read by the core on refresh_ui) --------------------------------
    def _queued(self) -> int:
        """The operations to send and the blocked ones: the Changes count and part of the badge."""
        row = (
            self._store.connection()
            .execute(
                "SELECT COUNT(*) AS n FROM remote_queue WHERE state IN (?, ?)",
                (PENDING, BLOCKED),
            )
            .fetchone()
        )
        return int(row["n"])

    def _attention(self) -> int:
        """The activity badge: the open conflicts and the blocked operations."""
        return self._conflicts.open_count() + self._blocked()

    def _blocked(self) -> int:
        row = (
            self._store.connection()
            .execute("SELECT COUNT(*) AS n FROM remote_queue WHERE state = ?", (BLOCKED,))
            .fetchone()
        )
        return int(row["n"])

    def _is_manual(self) -> bool:
        return sync_mode(self._context) == MANUAL

    def set_backups(self, raw: Sequence[dict[str, Any]]) -> None:
        """Keep the server's backup list (newest first, as the server sends it) and show it."""
        self._backups = [dict(item) for item in raw]
        self._backups_read_at = datetime.now(UTC)
        self._models[BACKUPS_ID].replace(self._backup_rows())

    # -- rows ------------------------------------------------------------------------------
    def _change_rows(self) -> list[dict[str, Any]]:
        placeholders = ", ".join("?" for _ in QUEUE_STATES)
        found = (
            self._store.connection()
            .execute(
                "SELECT op_id, kind, track_id, state FROM remote_queue"
                f" WHERE state IN ({placeholders}) ORDER BY rowid",
                QUEUE_STATES,
            )
            .fetchall()
        )
        if not found:
            return [{"id": "up_to_date", "name": UP_TO_DATE}]
        titles = self._titles([row["track_id"] for row in found if row["track_id"]])
        rows: list[dict[str, Any]] = []
        for row in found:
            verb = VERBS.get(str(row["kind"]), "Send")
            title = titles.get(str(row["track_id"])) or "a track"
            entry: dict[str, Any] = {"id": str(row["op_id"]), "name": f"{verb} {title}"}
            if row["state"] in PROBLEM_STATES:
                entry.update(tone="warning", icon="alert", count=str(row["state"]))
            rows.append(entry)
        return rows

    def _titles(self, track_ids: Sequence[str]) -> dict[str, str]:
        ids = list(dict.fromkeys(track_ids))
        if not ids:
            return {}
        return {
            track.track_id: track.title
            for track in self._context.library.tracks(ids)
            if track.title
        }

    def _conflict_rows(self) -> list[dict[str, Any]]:
        """The open conflicts, read from the conflicts' own rows (title and reason)."""
        return [
            {
                "id": row["id"],
                "name": f"{row['title']}: {row['subtitle']}",
                "icon": "alert",
                "tone": "warning",
            }
            for row in self._conflicts.model.rows()
        ]

    def _backup_rows(self) -> list[dict[str, Any]]:
        return [
            {"id": row["backupId"], "name": f"{row['when']} · {row['kind']}", "count": row["size"]}
            for row in backup_rows(self._backups[:RECENT_BACKUPS], {})
        ]

    def _log_rows(self, conn: sqlite3.Connection) -> list[dict[str, Any]]:
        found = conn.execute(
            "SELECT log_id, at_utc, level, text FROM remote_log ORDER BY log_id DESC LIMIT ?",
            (LOG_LINES,),
        ).fetchall()
        rows: list[dict[str, Any]] = []
        for row in found:
            entry: dict[str, Any] = {
                "id": str(row["log_id"]),
                "name": str(row["text"]),
                "count": _clock(str(row["at_utc"])),
            }
            if row["level"] in WARNING_LEVELS:
                entry.update(tone="warning", icon="alert")
            rows.append(entry)
        return rows

    # -- backups ---------------------------------------------------------------------------
    def _read_backups_if_due(self) -> None:
        """Read the server's backup list in a job, when connected and the last read is old."""
        if self._reading_backups or self._link.state != CONNECTED:
            return
        if (
            self._backups_read_at is not None
            and datetime.now(UTC) - self._backups_read_at < BACKUP_MAX_AGE
        ):
            return
        client = self._link.client()
        if client is None:
            return
        self._reading_backups = True
        submit(
            self._context,
            "Reading the backups",
            lambda _job: client.backups(),
            self._on_backups,
            visible=False,
        )

    def _on_backups(self, result: list[dict[str, Any]] | None, error: BaseException | None) -> None:
        self._reading_backups = False
        # A failed read also waits ten minutes: the server is not asked every minute.
        self._backups_read_at = datetime.now(UTC)
        if error is not None:
            self._context.log.warning("Reading the backups failed: %s", error)
            return
        self.set_backups(result or [])


def _clock(text: str) -> str:
    """The local time of a stored UTC time, as ``HH:MM``; empty when it cannot be read."""
    try:
        return datetime.fromisoformat(text).astimezone().strftime("%H:%M")
    except ValueError:
        return ""

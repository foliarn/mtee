"""The per-user change journal and the notifier that wakes long-polling requests."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from mtee_remote import clock
from mtee_remote.db import Transaction

KINDS = frozenset(
    {
        "added",
        "replaced",
        "moved",
        "trashed",
        "restored",
        "metadata",
        "purged",
        "backup_added",
        "backup_trashed",
    }
)


def append(
    tx: Transaction, user_id: str, kind: str, item_id: str | None, payload: dict[str, Any]
) -> int:
    """Add a row to `user_id`'s journal inside `tx` and return its sequence number.

    The user is also added to `tx.notify_users`, so waiting requests wake up after commit.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown journal kind: {kind!r}")
    row = tx.conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 FROM journal WHERE user_id = ?", (user_id,)
    ).fetchone()
    seq = int(row[0])
    tx.conn.execute(
        "INSERT INTO journal(user_id, seq, item_id, kind, payload_json, at_utc)"
        " VALUES (?,?,?,?,?,?)",
        (
            user_id,
            seq,
            item_id,
            kind,
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            clock.to_iso(clock.utc_now()),
        ),
    )
    tx.notify_users.add(user_id)
    return seq


class ChangeNotifier:
    """Tells waiting requests that a user's journal changed.

    `notify` may be called from any thread. A waiter only sees notifications that arrive
    after it started waiting, so a caller must read the journal again after `wait` starts
    (or compare against the journal) to avoid missing a change that landed in between.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiters: dict[str, set[asyncio.Future[bool]]] = {}

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def notify(self, user_ids: set[str]) -> None:
        loop = self._loop
        if loop is None or not user_ids:
            return
        # A closed loop (shutdown) raises RuntimeError: nobody is waiting any more.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._wake, set(user_ids))

    def _wake(self, user_ids: set[str]) -> None:
        for user_id in user_ids:
            for future in self._waiters.pop(user_id, set()):
                if not future.done():
                    future.set_result(True)

    async def wait(self, user_id: str, timeout: float) -> bool:
        """Return True if a notification for `user_id` arrives within `timeout` seconds."""
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._waiters.setdefault(user_id, set()).add(future)
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            return False
        finally:
            waiters = self._waiters.get(user_id)
            if waiters is not None:
                waiters.discard(future)
                if not waiters:
                    del self._waiters[user_id]

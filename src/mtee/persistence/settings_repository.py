"""Storage of the simple application settings.

The repository stores text values. A caller that needs a structured value
encodes it, so the table stays readable and no implicit type is invented.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from mtee.persistence.database import Database

__all__ = ["SettingsRepository"]

_LOGGER = logging.getLogger(__name__)


class SettingsRepository:
    """Reads and writes the ``settings`` table."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._listeners: list[Callable[[str], None]] = []
        self._listeners_lock = threading.Lock()

    def add_listener(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Call ``listener(key)`` after every committed ``set`` or ``delete`` of a key.

        The call runs on the thread that wrote the setting, so a listener that touches the
        interface hands the work to the graphical thread itself. A listener that raises is
        logged and skipped: the setting is already stored when it is called. Returns the
        function that removes the listener.
        """
        with self._listeners_lock:
            self._listeners.append(listener)

        def remove() -> None:
            with self._listeners_lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return remove

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the value stored for ``key``, or ``default``."""
        row = (
            self._database.connection()
            .execute("SELECT value FROM settings WHERE key = ?", (key,))
            .fetchone()
        )
        return str(row["value"]) if row is not None else default

    def set(self, key: str, value: str) -> None:
        """Store ``value`` for ``key``, replacing a previous value."""
        if not key:
            raise ValueError("a setting key is required")
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO settings (key, value, updated_at_utc) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at_utc = excluded.updated_at_utc",
                (key, value, datetime.now(UTC).isoformat(timespec="seconds")),
            )
        self._announce(key)

    def set_many(self, values: Mapping[str, str]) -> None:
        """Store several values in one transaction; listeners are called once it is committed."""
        if any(not key for key in values):
            raise ValueError("a setting key is required")
        if not values:
            return
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with self._database.transaction() as connection:
            connection.executemany(
                "INSERT INTO settings (key, value, updated_at_utc) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at_utc = excluded.updated_at_utc",
                [(key, value, stamp) for key, value in values.items()],
            )
        for key in values:
            self._announce(key)

    def get_json(self, key: str, default: Any = None) -> Any:
        """Return the JSON value stored for ``key``, or ``default``.

        A stored value that is not valid JSON is reported as absent rather than
        raising, so a corrupted setting never prevents the window from opening.
        """
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def set_json(self, key: str, value: Any) -> None:
        """Store ``value`` encoded as JSON."""
        self.set(key, json.dumps(value, ensure_ascii=False, sort_keys=True))

    def delete(self, key: str) -> None:
        """Remove ``key`` when it exists."""
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM settings WHERE key = ?", (key,))
        self._announce(key)

    def all(self) -> dict[str, str]:
        """Return every stored setting."""
        rows = self._database.connection().execute("SELECT key, value FROM settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def _announce(self, key: str) -> None:
        with self._listeners_lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(key)
            except Exception:
                _LOGGER.exception("A settings listener failed for %s.", key)

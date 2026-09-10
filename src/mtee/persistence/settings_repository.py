"""Storage of the simple application settings.

The repository stores text values. A caller that needs a structured value
encodes it, so the table stays readable and no implicit type is invented.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from mtee.persistence.database import Database

__all__ = ["SettingsRepository"]


class SettingsRepository:
    """Reads and writes the ``settings`` table."""

    def __init__(self, database: Database) -> None:
        self._database = database

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

    def all(self) -> dict[str, str]:
        """Return every stored setting."""
        rows = self._database.connection().execute("SELECT key, value FROM settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

"""Core store of the user's choices on artist credits (table ``credit_overrides``)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mtee.domain.artist_index import OVERRIDE_MODES
from mtee.domain.artists import clean_name, normalize_key
from mtee.persistence.database import Database

__all__ = ["CreditOverrideRepository"]


class CreditOverrideRepository:
    """Keep "This is one artist" and "Split into separate artists" choices across restarts."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def set_mode(self, text: str, mode: str) -> None:
        """Store ``mode`` for the credit ``text``, replacing an earlier choice for it."""
        if mode not in OVERRIDE_MODES:
            raise ValueError(f"Unknown credit override mode: {mode}")
        cleaned = clean_name(text)
        key = normalize_key(cleaned)
        if not key:
            raise ValueError("A credit override needs a name.")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO credit_overrides(credit_key,credit_text,mode,updated_at_utc) "
                "VALUES(?,?,?,?) ON CONFLICT(credit_key) DO UPDATE SET "
                "credit_text=excluded.credit_text,mode=excluded.mode,"
                "updated_at_utc=excluded.updated_at_utc",
                (key, cleaned, mode, now),
            )

    def remove(self, credit_key: str) -> bool:
        """Forget the choice of ``credit_key``; return whether one existed."""
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM credit_overrides WHERE credit_key=?", (normalize_key(credit_key),)
            )
            return cursor.rowcount > 0

    def modes(self) -> dict[str, tuple[str, str]]:
        """Return ``{credit_key: (credit text, mode)}`` for the index build."""
        rows = (
            self._database.connection()
            .execute("SELECT credit_key,credit_text,mode FROM credit_overrides")
            .fetchall()
        )
        return {str(row["credit_key"]): (str(row["credit_text"]), str(row["mode"])) for row in rows}

    def all(self) -> list[dict[str, Any]]:
        """Return every choice as ``{"key", "text", "mode"}``, sorted by credit text."""
        rows = (
            self._database.connection()
            .execute(
                "SELECT credit_key,credit_text,mode,updated_at_utc FROM credit_overrides "
                "ORDER BY credit_text COLLATE NOCASE"
            )
            .fetchall()
        )
        return [
            {
                "key": str(row["credit_key"]),
                "text": str(row["credit_text"]),
                "mode": str(row["mode"]),
                "updatedAtUtc": str(row["updated_at_utc"]),
            }
            for row in rows
        ]

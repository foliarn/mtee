"""User accounts: the rules for names, creation and the public view of a user row."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from mtee_remote import clock
from mtee_remote.config import Settings
from mtee_remote.db import Transaction
from mtee_remote.errors import ApiError
from mtee_remote.ids import new_id
from mtee_remote.passwords import check_new_password, hash_password

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,31}$")


def check_username(name: str) -> str:
    """Return `name` in lower case, or refuse it. The name is also the library folder name."""
    lowered = name.lower()
    if USERNAME_RE.fullmatch(lowered) is None:
        raise ApiError(
            "bad_request",
            "A user name has 2 to 32 characters: letters, digits, '_', '.' or '-', "
            "and starts with a letter or a digit.",
        )
    return lowered


def create_user_row(
    tx: Transaction,
    settings: Settings,
    *,
    username: str,
    password: str,
    is_admin: bool,
    quota_bytes: int | None,
) -> str:
    """Insert a user with its library folder and return the new user id."""
    name = check_username(username)
    check_new_password(password)
    if quota_bytes is not None and quota_bytes < 0:
        raise ApiError("bad_request", "The quota must not be negative.")
    taken = tx.conn.execute("SELECT 1 FROM users WHERE username = ?", (name,)).fetchone()
    if taken is not None:
        raise ApiError("conflict", f"The user name {name} is already taken.")
    password_hash = hash_password(password)
    (settings.music_dir / name).mkdir(parents=True, exist_ok=True)
    user_id = new_id()
    try:
        tx.conn.execute(
            "INSERT INTO users(user_id, username, password_hash, is_admin, disabled,"
            " quota_bytes, library_dir, created_at_utc) VALUES (?,?,?,?,?,?,?,?)",
            (
                user_id,
                name,
                password_hash,
                int(is_admin),
                0,
                quota_bytes,
                name,
                clock.to_iso(clock.utc_now()),
            ),
        )
    except sqlite3.IntegrityError:
        raise ApiError("conflict", f"The user name {name} is already taken.") from None
    return user_id


def user_public(row: sqlite3.Row) -> dict[str, Any]:
    """The fields of a user row that the API shows to clients."""
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "is_admin": bool(row["is_admin"]),
        "disabled": bool(row["disabled"]),
        "quota_bytes": row["quota_bytes"],
        "created_at_utc": row["created_at_utc"],
    }

"""Account commands: create-admin, create-user and reset-password (milestone 124.3).

They run on the server host, for example with `docker compose exec`, and open the database
directly, so the HTTP server does not need to be running.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable

from mtee_remote import clock
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.passwords import check_new_password, hash_password
from mtee_remote.users import check_username, create_user_row

GIB = 1024**3
PASSWORD_ENV = "MTEE_REMOTE_ADMIN_PASSWORD"


def _open_database() -> tuple[Settings, Database]:
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = settings.data_dir / "db-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.data_dir / "mtee-remote.db", backup_dir)
    db.migrate()
    return settings, db


def _new_password() -> str:
    """Read the new password from the environment, or ask for it twice."""
    value = os.environ.get(PASSWORD_ENV)
    if value is not None:
        password = value
    else:
        first = getpass.getpass("New password: ")
        second = getpass.getpass("Repeat the new password: ")
        if first != second:
            raise ApiError("bad_request", "The two passwords do not match.")
        password = first
    check_new_password(password)
    return password


def _run(action: Callable[[], str]) -> int:
    """Run a command body; print its message on success, or the error on stderr."""
    try:
        message = action()
    except ApiError as error:
        print(error.message, file=sys.stderr)
        return 1
    except ValueError as error:  # missing or invalid settings, such as MTEE_REMOTE_DATA
        print(error, file=sys.stderr)
        return 2
    print(message)
    return 0


def _create(username: str, *, is_admin: bool, quota_bytes: int | None) -> str:
    name = check_username(username)
    password = _new_password()
    settings, db = _open_database()
    try:
        with db.transaction() as tx:
            create_user_row(
                tx,
                settings,
                username=name,
                password=password,
                is_admin=is_admin,
                quota_bytes=quota_bytes,
            )
    finally:
        db.close()
    label = "Admin" if is_admin else "User"
    return f"{label} {name} created."


def create_admin(args: argparse.Namespace) -> int:
    return _run(lambda: _create(args.username, is_admin=True, quota_bytes=None))


def create_user(args: argparse.Namespace) -> int:
    quota_bytes: int | None = None
    if args.quota_gb is not None:
        quota_bytes = int(args.quota_gb * GIB)
    return _run(lambda: _create(args.username, is_admin=bool(args.admin), quota_bytes=quota_bytes))


def _reset(username: str) -> str:
    name = check_username(username)
    password = _new_password()
    _, db = _open_database()
    try:
        with db.transaction() as tx:
            row = tx.conn.execute(
                "SELECT user_id FROM users WHERE username = ?", (name,)
            ).fetchone()
            if row is None:
                raise ApiError("not_found", f"No account named {name}.")
            tx.conn.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (hash_password(password), row["user_id"]),
            )
            cursor = tx.conn.execute(
                "UPDATE devices SET revoked_at_utc = ?"
                " WHERE user_id = ? AND revoked_at_utc IS NULL",
                (clock.to_iso(clock.utc_now()), row["user_id"]),
            )
            signed_out = cursor.rowcount
    finally:
        db.close()
    return f"Password changed; {signed_out} devices signed out."


def reset_password(args: argparse.Namespace) -> int:
    return _run(lambda: _reset(args.username))

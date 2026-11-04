"""`mtee-remote admin ...`: the administration commands of the setup TUI, in JSON.

The TUI (`admin/`, the `mtee-remote-admin` program) runs on the server host and calls these with
`docker compose exec -T server mtee-remote admin <command>`. Each command opens the database
directly, as the other commands do, so it works while the HTTP side is down; it prints one JSON
object on stdout and returns 0, or prints `{"error": "<sentence>"}` and returns 1.

A password is read from stdin (`--password-stdin`, one line), never from an argument or the
environment, so it does not show in the process list of the host. The rules are the server's own:
`create_user_row`, `check_new_password`, the streaming settings validation, and the same refusals
as the admin routes (files are never deleted with an account).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

from mtee_remote import __version__, clock
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.passwords import check_new_password, hash_password
from mtee_remote.streaming.settings import (
    put_server_streaming_settings,
    server_streaming_settings,
)
from mtee_remote.users import check_username, create_user_row, user_public

GIB = 1024**3


class _RefusedError(Exception):
    """A request the command refuses, with the sentence to show."""


def _open() -> tuple[Settings, Database]:
    settings = Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.data_dir / "mtee-remote.db", settings.data_dir / "db-backups")
    db.migrate()
    return settings, db


def _run(body: Callable[[Settings, Database, argparse.Namespace], Any]) -> Callable[..., int]:
    """Wrap a command body: JSON on stdout, or `{"error"}` and exit code 1."""

    def command(args: argparse.Namespace) -> int:
        try:
            settings, db = _open()
        except ValueError as error:  # missing settings, such as MTEE_REMOTE_DATA
            return _fail(str(error))
        try:
            result = body(settings, db, args)
        except ApiError as error:
            return _fail(error.message)
        except _RefusedError as error:
            return _fail(str(error))
        finally:
            db.close()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    return command


def _fail(message: str) -> int:
    print(json.dumps({"error": message}, ensure_ascii=False))
    return 1


def _password_from_stdin() -> str:
    line = sys.stdin.readline()
    password = line[:-1] if line.endswith("\n") else line
    check_new_password(password)
    return password


def _user_row(db: Database, username: str) -> Any:
    row = db.conn().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise _RefusedError(f"There is no account named {username}.")
    return row


def _quota(text: str | None) -> int | None:
    """`--quota-gb`: a number of GB, or `none` for no quota."""
    if text is None or text.strip().lower() in ("", "none"):
        return None
    try:
        value = float(text)
    except ValueError:
        raise _RefusedError("The quota is a number of GB, or none.") from None
    if value < 0:
        raise _RefusedError("The quota must not be negative.")
    return int(value * GIB)


def _yes_no(text: str) -> int:
    value = text.strip().lower()
    if value in ("yes", "true", "1"):
        return 1
    if value in ("no", "false", "0"):
        return 0
    raise _RefusedError(f"Expected yes or no, got {text!r}.")


# -- status -----------------------------------------------------------------------------
def _status(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del args
    conn = db.conn()
    hashes = {"pending": 0, "done": 0, "error": 0}
    for row in conn.execute(
        "SELECT hash_state, COUNT(*) AS n FROM items WHERE state = 'present' GROUP BY hash_state"
    ):
        hashes[str(row["hash_state"])] = int(row["n"])
    size = conn.execute(
        "SELECT COALESCE(SUM(size_bytes), 0) AS n FROM items WHERE state = 'present'"
    ).fetchone()
    database_file = settings.data_dir / "mtee-remote.db"
    return {
        "version": __version__,
        "users": int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]),
        "devices": int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM devices WHERE revoked_at_utc IS NULL"
            ).fetchone()["n"]
        ),
        "items": sum(hashes.values()),
        "library_bytes": int(size["n"]),
        "hashes": hashes,
        "database_bytes": database_file.stat().st_size if database_file.is_file() else 0,
        "public_url": settings.public_url,
        "scan_interval_s": settings.scan_interval_s,
    }


# -- users -------------------------------------------------------------------------------
def _users(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings, args
    conn = db.conn()
    users = []
    for row in conn.execute("SELECT * FROM users ORDER BY username"):
        entry = user_public(row)
        entry["library_dir"] = row["library_dir"]
        used = conn.execute(
            "SELECT COALESCE(SUM(i.size_bytes), 0) AS n FROM items AS i"
            " JOIN roots AS r ON r.root_id = i.root_id"
            " WHERE r.user_id = ? AND i.state = 'present'",
            (row["user_id"],),
        ).fetchone()
        entry["used_bytes"] = int(used["n"])
        entry["devices"] = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM devices WHERE user_id = ? AND revoked_at_utc IS NULL",
                (row["user_id"],),
            ).fetchone()["n"]
        )
        users.append(entry)
    return {"users": users}


def _user_create(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    name = check_username(args.username)
    password = _password_from_stdin()
    with db.transaction() as tx:
        user_id = create_user_row(
            tx,
            settings,
            username=name,
            password=password,
            is_admin=bool(args.admin),
            quota_bytes=_quota(args.quota_gb),
        )
        row = tx.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return {"user": user_public(row), "message": f"Account {name} created."}


def _user_set(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings
    row = _user_row(db, args.username)
    changes: dict[str, Any] = {}
    if args.quota_gb is not None:
        changes["quota_bytes"] = _quota(args.quota_gb)
    if args.disabled is not None:
        changes["disabled"] = _yes_no(args.disabled)
    if args.admin is not None:
        changes["is_admin"] = _yes_no(args.admin)
    if not changes:
        raise _RefusedError("Nothing to change: give --quota-gb, --disabled or --admin.")
    removes_admin = changes.get("is_admin") == 0 or changes.get("disabled") == 1
    if removes_admin and row["is_admin"]:
        others = (
            db.conn()
            .execute(
                "SELECT COUNT(*) AS n FROM users"
                " WHERE is_admin = 1 AND disabled = 0 AND user_id <> ?",
                (row["user_id"],),
            )
            .fetchone()
        )
        if int(others["n"]) == 0:
            raise _RefusedError("This is the last active administrator: keep it an active admin.")
    with db.transaction() as tx:
        # The column names come from the fixed keys above, never from the arguments.
        assignments = ", ".join(f"{column} = ?" for column in changes)
        tx.conn.execute(
            f"UPDATE users SET {assignments} WHERE user_id = ?",
            (*changes.values(), row["user_id"]),
        )
        updated = tx.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (row["user_id"],)
        ).fetchone()
    return {"user": user_public(updated), "message": f"Account {updated['username']} changed."}


def _user_password(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings
    row = _user_row(db, args.username)
    password = _password_from_stdin()
    with db.transaction() as tx:
        tx.conn.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (hash_password(password), row["user_id"]),
        )
        cursor = tx.conn.execute(
            "UPDATE devices SET revoked_at_utc = ? WHERE user_id = ? AND revoked_at_utc IS NULL",
            (clock.to_iso(clock.utc_now()), row["user_id"]),
        )
    signed_out = cursor.rowcount
    return {
        "signed_out": signed_out,
        "message": f"Password changed; {signed_out} devices signed out.",
    }


def _user_delete(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    row = _user_row(db, args.username)
    if args.confirm != row["username"]:
        raise _RefusedError("Type the user name to confirm the deletion.")
    if row["is_admin"]:
        others = (
            db.conn()
            .execute(
                "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1 AND user_id <> ?",
                (row["user_id"],),
            )
            .fetchone()
        )
        if int(others["n"]) == 0:
            raise _RefusedError("This is the last administrator: it cannot be deleted.")
    with db.transaction() as tx:
        tx.conn.execute("DELETE FROM users WHERE user_id = ?", (row["user_id"],))
    kept = settings.music_dir / row["library_dir"]
    return {
        "library_folder_kept": row["library_dir"] if kept.is_dir() else None,
        "message": f"Account {row['username']} deleted. Its music folder is kept.",
    }


# -- devices -----------------------------------------------------------------------------
def _devices(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings
    query = (
        "SELECT d.device_id, d.name, d.kind, d.created_at_utc, d.last_seen_utc,"
        " d.revoked_at_utc, u.username FROM devices AS d JOIN users AS u ON u.user_id = d.user_id"
    )
    params: tuple[str, ...] = ()
    if args.username:
        query += " WHERE u.username = ?"
        params = (args.username,)
    query += " ORDER BY u.username, d.last_seen_utc DESC"
    devices = [dict(row) for row in db.conn().execute(query, params)]
    for device in devices:
        device["active"] = device["revoked_at_utc"] is None
    return {"devices": devices}


def _device_revoke(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings
    with db.transaction() as tx:
        cursor = tx.conn.execute(
            "UPDATE devices SET revoked_at_utc = ? WHERE device_id = ? AND revoked_at_utc IS NULL",
            (clock.to_iso(clock.utc_now()), args.device_id),
        )
    if cursor.rowcount == 0:
        raise _RefusedError("No active device has this id.")
    return {"message": "The device is signed out."}


# -- libraries ---------------------------------------------------------------------------
def _roots(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings, args
    conn = db.conn()
    roots = []
    for row in conn.execute(
        "SELECT r.root_id, r.name, r.relative_dir, r.adopted, u.username"
        " FROM roots AS r JOIN users AS u ON u.user_id = r.user_id ORDER BY u.username, r.name"
    ):
        entry = dict(row)
        entry["adopted"] = bool(entry["adopted"])
        counts = conn.execute(
            "SELECT COUNT(*) AS items, COALESCE(SUM(size_bytes), 0) AS bytes,"
            " COALESCE(SUM(hash_state = 'pending'), 0) AS pending"
            " FROM items WHERE root_id = ? AND state = 'present'",
            (row["root_id"],),
        ).fetchone()
        entry.update(
            items=int(counts["items"]), bytes=int(counts["bytes"]), pending=int(counts["pending"])
        )
        roots.append(entry)
    return {"roots": roots}


# -- server settings ---------------------------------------------------------------------
def _settings(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings, args
    return {"streaming": server_streaming_settings(db.conn())}


def _settings_set(settings: Settings, db: Database, args: argparse.Namespace) -> dict[str, Any]:
    del settings
    values: dict[str, Any] = {}
    for pair in args.values:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            raise _RefusedError(f"Expected name=value, got {pair!r}.")
        try:
            values[key] = json.loads(raw)
        except ValueError:
            raise _RefusedError(f"The value of {key} is not valid JSON: {raw!r}.") from None
    with db.transaction() as tx:
        stored = put_server_streaming_settings(tx, values)
    return {"streaming": stored, "message": "Saved. The server applies it after a restart."}


def add_parsers(commands: Any) -> None:
    """Add `admin` and its commands to the `mtee-remote` parser."""
    admin = commands.add_parser("admin", help="administration commands in JSON (setup TUI)")
    sub = admin.add_subparsers(dest="admin_command", required=True)

    sub.add_parser("status", help="counts, hashing and settings").set_defaults(func=_run(_status))
    sub.add_parser("users", help="list the accounts").set_defaults(func=_run(_users))

    p = sub.add_parser("user-create", help="create an account (password on stdin)")
    p.add_argument("--username", required=True)
    p.add_argument("--admin", action="store_true")
    p.add_argument("--quota-gb", default=None)
    p.add_argument("--password-stdin", action="store_true", required=True)
    p.set_defaults(func=_run(_user_create))

    p = sub.add_parser("user-set", help="change the quota, disabled or admin of an account")
    p.add_argument("--username", required=True)
    p.add_argument("--quota-gb", default=None, help="a number of GB, or none")
    p.add_argument("--disabled", default=None, help="yes or no")
    p.add_argument("--admin", default=None, help="yes or no")
    p.set_defaults(func=_run(_user_set))

    p = sub.add_parser("user-password", help="set a new password (on stdin); signs devices out")
    p.add_argument("--username", required=True)
    p.add_argument("--password-stdin", action="store_true", required=True)
    p.set_defaults(func=_run(_user_password))

    p = sub.add_parser("user-delete", help="delete an account; its music folder is kept")
    p.add_argument("--username", required=True)
    p.add_argument("--confirm", required=True, help="the user name again")
    p.set_defaults(func=_run(_user_delete))

    p = sub.add_parser("devices", help="list the devices")
    p.add_argument("--username", default=None)
    p.set_defaults(func=_run(_devices))

    p = sub.add_parser("device-revoke", help="sign a device out")
    p.add_argument("--device-id", required=True)
    p.set_defaults(func=_run(_device_revoke))

    sub.add_parser("roots", help="list the library folders").set_defaults(func=_run(_roots))
    sub.add_parser("settings", help="the server's streaming settings").set_defaults(
        func=_run(_settings)
    )

    p = sub.add_parser("settings-set", help="store streaming settings: name=json ...")
    p.add_argument("values", nargs="+")
    p.set_defaults(func=_run(_settings_set))

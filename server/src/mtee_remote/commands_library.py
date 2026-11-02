"""Library commands: adopt-root and scan (milestone 124.4)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from mtee_remote import clock
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.errors import ApiError
from mtee_remote.ids import new_id
from mtee_remote.library import scanner, store
from mtee_remote.paths import normalize_relative_path


class _CommandError(Exception):
    """A problem to print on stderr; the command then returns 1."""


def _open() -> tuple[Settings, Database]:
    try:
        settings = Settings.from_env()
    except ValueError as error:
        raise _CommandError(str(error)) from None
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.data_dir / "mtee-remote.db", settings.data_dir / "db-backups")
    db.migrate()
    return settings, db


def _user(conn: sqlite3.Connection, username: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT user_id, library_dir FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        raise _CommandError(f"There is no account named {username!r}.")
    return row


def adopt_root(args: argparse.Namespace) -> int:
    """Adopt an existing folder inside the user's library folder as a root and scan it.

    The folder is only read: nothing is created, moved or written inside it.
    """
    try:
        settings, db = _open()
    except _CommandError as error:
        print(error, file=sys.stderr)
        return 1
    try:
        return _adopt(settings, db, args)
    except _CommandError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        db.close()


def _adopt(settings: Settings, db: Database, args: argparse.Namespace) -> int:
    conn = db.conn()
    user = _user(conn, args.user)
    try:
        name = normalize_relative_path(args.name)
    except ApiError as error:
        raise _CommandError(error.message) from None
    if "/" in name:
        raise _CommandError("A root name is a single folder name, without '/'.")
    library = store.user_library_dir(settings, user["library_dir"]).resolve()
    folder = Path(args.path).resolve()
    if not folder.is_dir():
        raise _CommandError("The path is not an existing folder.")
    if folder != library and not folder.is_relative_to(library):
        raise _CommandError("The folder must be inside the user's library folder.")
    relative_dir = "" if folder == library else folder.relative_to(library).as_posix()
    with db.transaction() as tx:
        for row in tx.conn.execute(
            "SELECT name, relative_dir FROM roots WHERE user_id = ?", (user["user_id"],)
        ):
            if row["relative_dir"] == "":
                raise _CommandError("The whole library folder is already a root.")
            if row["name"] == name:
                raise _CommandError(f"The user already has a root named {name!r}.")
            if store.roots_overlap(row["relative_dir"], relative_dir):
                raise _CommandError(f"The folder overlaps the existing root {row['name']!r}.")
        root_id = new_id()
        tx.conn.execute(
            "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
            " VALUES (?,?,?,?,1,?)",
            (root_id, user["user_id"], name, relative_dir, clock.to_iso(clock.utc_now())),
        )
    result = _scan(db, settings, root_id)
    print(
        f"Adopted {name}: {result.added} audio files found. "
        "Their hashes are computed by the running server."
    )
    return 0


def _scan(db: Database, settings: Settings, root_id: str) -> scanner.ScanResult:
    try:
        return scanner.scan_root(db, settings, root_id)
    except (OSError, ApiError) as error:
        raise _CommandError(f"The scan failed: {error}") from None


def scan(args: argparse.Namespace) -> int:
    """Scan one root (`--root NAME`) or all roots of a user and print what changed."""
    try:
        settings, db = _open()
    except _CommandError as error:
        print(error, file=sys.stderr)
        return 1
    try:
        conn = db.conn()
        user = _user(conn, args.user)
        sql = "SELECT root_id, name FROM roots WHERE user_id = ?"
        params: list[str] = [user["user_id"]]
        if args.root is not None:
            sql += " AND name = ?"
            params.append(args.root)
        roots = conn.execute(sql + " ORDER BY name", params).fetchall()
        if not roots:
            if args.root is not None:
                raise _CommandError(f"The user has no root named {args.root!r}.")
            raise _CommandError("The user has no root.")
        for root in roots:
            result = _scan(db, settings, root["root_id"])
            print(
                f"{root['name']}: {result.added} added, {result.changed} changed, "
                f"{result.moved} moved, {result.removed} removed, {result.unchanged} unchanged"
            )
        return 0
    except _CommandError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        db.close()

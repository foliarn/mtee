"""Transactional virtual folders, playlists, ordered entries and local likes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mtee.domain.playlists import playlist_name
from mtee.persistence.database import Database


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class PlaylistsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def playlists(self) -> list[dict[str, Any]]:
        rows = self.database.connection().execute(
            "SELECT p.*,COUNT(e.entry_id) AS count FROM playlists p "
            "LEFT JOIN playlist_entries e ON e.playlist_id=p.playlist_id "
            "GROUP BY p.playlist_id ORDER BY p.pinned DESC,p.ordinal,p.playlist_id"
        )
        return [dict(row) for row in rows]

    def folders(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.database.connection().execute(
                "SELECT * FROM playlist_folders ORDER BY ordinal,folder_id"
            )
        ]

    def playlist(self, identity: str) -> dict[str, Any]:
        row = (
            self.database.connection()
            .execute("SELECT * FROM playlists WHERE playlist_id=?", (identity,))
            .fetchone()
        )
        if row is None:
            raise LookupError("This playlist no longer exists.")
        return dict(row)

    def entries(self, identity: str) -> list[dict[str, Any]]:
        return [
            dict(row) | {"snapshot": json.loads(row["snapshot_json"])}
            for row in self.database.connection().execute(
                "SELECT * FROM playlist_entries WHERE playlist_id=? ORDER BY ordinal",
                (identity,),
            )
        ]

    def create(
        self,
        name: str,
        folder: str = "",
        *,
        description: str = "",
        cover: str = "",
        entries: list[dict[str, Any]] | None = None,
        operation_id: str = "",
    ) -> str:
        identity = str(uuid4())
        with self.database.transaction() as connection:
            if operation_id:
                previous = connection.execute(
                    "SELECT result_playlist_id FROM playlist_imports WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if previous is None:
                    raise LookupError("This import operation no longer exists.")
                if previous[0]:
                    return str(previous[0])
            connection.execute(
                "INSERT INTO playlists(playlist_id,folder_id,name,description,cover_ref,ordinal,"
                "updated_at_utc) VALUES(?,?,?,?,?,(SELECT COALESCE(MAX(ordinal),-1)+1 "
                "FROM playlists),?)",
                (identity, folder or None, playlist_name(name), description, cover, _now()),
            )
            for index, entry in enumerate(entries or []):
                connection.execute(
                    "INSERT INTO playlist_entries VALUES(?,?,?,?,?)",
                    (
                        str(uuid4()),
                        identity,
                        entry.get("track_id"),
                        index,
                        json.dumps(entry["snapshot"], ensure_ascii=False),
                    ),
                )
            if operation_id:
                connection.execute(
                    "UPDATE playlist_imports SET phase='completed',result_playlist_id=?,error='' "
                    "WHERE operation_id=?",
                    (identity, operation_id),
                )
        return identity

    def update(
        self, identity: str, *, name: str, description: str, cover: str, version: int
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE playlists SET name=?,description=?,cover_ref=?,version=version+1,"
                "updated_at_utc=? WHERE playlist_id=? AND version=?",
                (playlist_name(name), description, cover, _now(), identity, version),
            )
            if result.rowcount != 1:
                raise ValueError("This playlist changed. Reopen its details and try again.")

    def duplicate(self, identity: str) -> str:
        source = self.playlist(identity)
        return self.create(
            source["name"] + " (copy)",
            source["folder_id"] or "",
            description=source["description"],
            cover=source["cover_ref"],
            entries=self.entries(identity),
        )

    def delete(self, identity: str) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM playlists WHERE playlist_id=?", (identity,))

    def pin(self, identity: str, pinned: bool) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE playlists SET pinned=?,version=version+1 WHERE playlist_id=?",
                (int(pinned), identity),
            )

    def add_entries(self, identity: str, entries: list[dict[str, Any]], version: int) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE playlists SET version=version+1,updated_at_utc=? "
                "WHERE playlist_id=? AND version=?",
                (_now(), identity, version),
            )
            if result.rowcount != 1:
                raise ValueError("This playlist changed. Try adding the selection again.")
            ordinal = connection.execute(
                "SELECT COALESCE(MAX(ordinal),-1)+1 FROM playlist_entries WHERE playlist_id=?",
                (identity,),
            ).fetchone()[0]
            for index, entry in enumerate(entries):
                connection.execute(
                    "INSERT INTO playlist_entries VALUES(?,?,?,?,?)",
                    (
                        str(uuid4()),
                        identity,
                        entry.get("track_id"),
                        ordinal + index,
                        json.dumps(entry["snapshot"], ensure_ascii=False),
                    ),
                )

    def remove(self, identity: str, entry_ids: list[str]) -> None:
        with self.database.transaction() as connection:
            connection.executemany(
                "DELETE FROM playlist_entries WHERE playlist_id=? AND entry_id=?",
                [(identity, entry_id) for entry_id in entry_ids],
            )
            connection.execute(
                "UPDATE playlists SET version=version+1,updated_at_utc=? WHERE playlist_id=?",
                (_now(), identity),
            )

    def reorder(self, identity: str, entry_ids: list[str], version: int) -> None:
        with self.database.transaction() as connection:
            current = connection.execute(
                "SELECT entry_id FROM playlist_entries WHERE playlist_id=?", (identity,)
            ).fetchall()
            if len(entry_ids) != len(current) or set(entry_ids) != {r[0] for r in current}:
                raise ValueError("The playlist entries changed. Refresh before reordering.")
            result = connection.execute(
                "UPDATE playlists SET version=version+1,updated_at_utc=? "
                "WHERE playlist_id=? AND version=?",
                (_now(), identity, version),
            )
            if result.rowcount != 1:
                raise ValueError("This playlist changed. Refresh before reordering.")
            connection.execute(
                "UPDATE playlist_entries SET ordinal=-ordinal-1 WHERE playlist_id=?", (identity,)
            )
            connection.executemany(
                "UPDATE playlist_entries SET ordinal=? WHERE playlist_id=? AND entry_id=?",
                [(index, identity, entry_id) for index, entry_id in enumerate(entry_ids)],
            )

    def resolve(
        self, identity: str, entry_id: str, track_id: str, snapshot: dict[str, Any], version: int
    ) -> None:
        with self.database.transaction() as connection:
            result = connection.execute(
                "UPDATE playlists SET version=version+1,updated_at_utc=? "
                "WHERE playlist_id=? AND version=?",
                (_now(), identity, version),
            )
            if result.rowcount != 1:
                raise ValueError("This playlist changed. Locate the entry again.")
            result = connection.execute(
                "UPDATE playlist_entries SET track_id=?,snapshot_json=? "
                "WHERE playlist_id=? AND entry_id=?",
                (track_id, json.dumps(snapshot, ensure_ascii=False), identity, entry_id),
            )
            if result.rowcount != 1:
                raise LookupError("This entry no longer exists.")

    def liked_ids(self) -> list[str]:
        return [
            r[0]
            for r in self.database.connection().execute(
                "SELECT track_id FROM liked_tracks ORDER BY liked_at_utc DESC,track_id"
            )
        ]

    def like(self, track_id: str, liked: bool) -> None:
        with self.database.transaction() as connection:
            if liked:
                connection.execute(
                    "INSERT OR IGNORE INTO liked_tracks VALUES(?,?)", (track_id, _now())
                )
            else:
                connection.execute("DELETE FROM liked_tracks WHERE track_id=?", (track_id,))

    def create_folder(self, name: str, parent: str = "") -> str:
        identity = str(uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO playlist_folders(folder_id,parent_id,name,ordinal) "
                "VALUES(?,?,?,(SELECT COALESCE(MAX(ordinal),-1)+1 FROM playlist_folders))",
                (identity, parent or None, playlist_name(name)),
            )
        return identity

    def rename_folder(self, identity: str, name: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE playlist_folders SET name=?,version=version+1 WHERE folder_id=?",
                (playlist_name(name), identity),
            )

    def delete_folder(self, identity: str) -> None:
        with self.database.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM playlist_folders WHERE parent_id=? UNION ALL "
                "SELECT 1 FROM playlists WHERE folder_id=? LIMIT 1",
                (identity, identity),
            ).fetchone():
                raise ValueError("Move all playlists and subfolders before deleting this folder.")
            connection.execute("DELETE FROM playlist_folders WHERE folder_id=?", (identity,))

    def move(
        self, identity: str, folder: str, *, is_folder: bool = False, before: str = ""
    ) -> None:
        table = "playlist_folders" if is_folder else "playlists"
        key = "folder_id" if is_folder else "playlist_id"
        parent_key = "parent_id" if is_folder else "folder_id"
        with self.database.transaction() as connection:
            if is_folder:
                ancestor = folder
                while ancestor:
                    if ancestor == identity:
                        raise ValueError("A folder cannot be moved into itself or its descendants.")
                    row = connection.execute(
                        "SELECT parent_id FROM playlist_folders WHERE folder_id=?", (ancestor,)
                    ).fetchone()
                    if row is None:
                        raise LookupError("The destination folder no longer exists.")
                    ancestor = row[0] or ""
            siblings = [
                r[0]
                for r in connection.execute(
                    f"SELECT {key} FROM {table} WHERE {parent_key} IS ? AND {key}<>? "
                    "ORDER BY ordinal",
                    (folder or None, identity),
                )
            ]
            index = siblings.index(before) if before in siblings else len(siblings)
            siblings.insert(index, identity)
            connection.execute(
                f"UPDATE {table} SET {parent_key}=?,version=version+1 WHERE {key}=?",
                (folder or None, identity),
            )
            connection.executemany(
                f"UPDATE {table} SET ordinal=? WHERE {key}=?",
                [(i, item) for i, item in enumerate(siblings)],
            )

"""Transactional local decisions for the bundled Genre Manager."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import wraps
from threading import RLock
from typing import Any

from mtee.persistence.database import Database
from mtee.plugins.genre_manager.catalogue import GENRE_TREE
from mtee.plugins.genre_manager.domain import validate_order


class StaleDecisionError(RuntimeError):
    """The track changed after the caller displayed it."""


GENRE_ORGANIZATION_LOCK = RLock()


def serialized_decision(method: Any) -> Any:
    """Serialize local classification writes with Genre Manager file movements."""

    @wraps(method)
    def locked(*args: Any, **kwargs: Any) -> Any:
        with GENRE_ORGANIZATION_LOCK:
            return method(*args, **kwargs)

    return locked


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


class GenreManagerRepository:
    """Keep plugin writes isolated from audio metadata and ordinary list queries."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def genres(self) -> list[dict[str, Any]]:
        rows = self._database.connection().execute(
            "SELECT genre_id,parent_id,name,sort_order,archived FROM gm_genres "
            "ORDER BY sort_order,name"
        )
        return [dict(row) for row in rows]

    def ensure_catalogue(self) -> None:
        """Insert the initial tree once, atomically, on first plugin opening."""
        with self._database.transaction() as connection:
            if connection.execute("SELECT 1 FROM gm_genres LIMIT 1").fetchone():
                return
            for root_order, (root_name, children) in enumerate(GENRE_TREE):
                root_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mtee/genre/{root_name}"))
                connection.execute(
                    "INSERT INTO gm_genres(genre_id,parent_id,name,name_key,sort_order,"
                    "created_at_utc,updated_at_utc) VALUES(?,NULL,?,?,?,?,?)",
                    (root_id, root_name, _key(root_name), root_order, _now(), _now()),
                )
                for child_order, child in enumerate(children):
                    child_id = str(
                        uuid.uuid5(uuid.NAMESPACE_URL, f"mtee/genre/{root_name}/{child}")
                    )
                    connection.execute(
                        "INSERT INTO gm_genres(genre_id,parent_id,name,name_key,sort_order,"
                        "created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?)",
                        (child_id, root_id, child, _key(child), child_order, _now(), _now()),
                    )

    def tags(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self._database.connection().execute(
                "SELECT tag_id,name,archived FROM gm_tags ORDER BY name"
            )
        ]

    def operation_exists(self, operation_id: str) -> bool:
        return self._already_applied(self._database.connection(), operation_id)

    def create_genre(
        self, name: str, parent_id: str | None = None, *, genre_id: str | None = None
    ) -> str:
        clean = name.strip()
        if not clean:
            raise ValueError("Genre name is required")
        identity = genre_id or str(uuid.uuid4())
        with self._database.transaction() as connection:
            if (
                parent_id is not None
                and connection.execute(
                    "SELECT 1 FROM gm_genres WHERE genre_id=? AND archived=0", (parent_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("Parent genre is missing or archived")
            order = connection.execute(
                "SELECT COALESCE(MAX(sort_order)+1,0) FROM gm_genres WHERE parent_id IS ?",
                (parent_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO gm_genres(genre_id,parent_id,name,name_key,sort_order,"
                "created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?)",
                (identity, parent_id, clean, _key(clean), order, _now(), _now()),
            )
        return identity

    def rename_genre(self, genre_id: str, name: str) -> None:
        clean = name.strip()
        if not clean:
            raise ValueError("Genre name is required")
        with self._database.transaction() as connection:
            changed = connection.execute(
                "UPDATE gm_genres SET name=?,name_key=?,updated_at_utc=? WHERE genre_id=?",
                (clean, _key(clean), _now(), genre_id),
            ).rowcount
            if changed != 1:
                raise KeyError(genre_id)

    def set_genre_archived(self, genre_id: str, archived: bool) -> None:
        """Archive or restore a branch without losing existing assignments."""
        with self._database.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM gm_genres WHERE genre_id=?", (genre_id,)
                ).fetchone()
                is None
            ):
                raise KeyError(genre_id)
            connection.execute(
                "WITH RECURSIVE branch(genre_id) AS ("
                "SELECT genre_id FROM gm_genres WHERE genre_id=? "
                "UNION ALL SELECT child.genre_id FROM gm_genres child "
                "JOIN branch ON child.parent_id=branch.genre_id) "
                "UPDATE gm_genres SET archived=?,updated_at_utc=? "
                "WHERE genre_id IN (SELECT genre_id FROM branch)",
                (genre_id, int(archived), _now()),
            )

    def create_tag(self, name: str, *, tag_id: str | None = None) -> str:
        clean = name.strip()
        if not clean:
            raise ValueError("Tag name is required")
        identity = tag_id or str(uuid.uuid4())
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO gm_tags(tag_id,name,name_key,created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,?,?)",
                (identity, clean, _key(clean), _now(), _now()),
            )
        return identity

    def track(self, track_id: str) -> dict[str, Any]:
        connection = self._database.connection()
        state = connection.execute(
            "SELECT genre_revision,tag_revision,reviewed_revision FROM gm_track_state "
            "WHERE track_id=?",
            (track_id,),
        ).fetchone()
        genres = [
            str(row[0])
            for row in connection.execute(
                "SELECT genre_id FROM gm_track_genres WHERE track_id=? ORDER BY position",
                (track_id,),
            )
        ]
        tags = [
            str(row[0])
            for row in connection.execute(
                "SELECT tag_id FROM gm_track_tags WHERE track_id=? ORDER BY tag_id",
                (track_id,),
            )
        ]
        genre_revision = int(state[0]) if state is not None else 0
        return {
            "track_id": track_id,
            "genres": genres,
            "tags": tags,
            "genre_revision": genre_revision,
            "tag_revision": int(state[1]) if state is not None else 0,
            "reviewed": bool(state is not None and state[2] == genre_revision),
        }

    @serialized_decision
    def set_genres(
        self,
        track_id: str,
        genres: Sequence[str],
        *,
        expected_revision: int,
        operation_id: str,
    ) -> dict[str, Any]:
        """Set an exact ordered list; retries of the same operation are harmless."""
        with self._database.transaction() as connection:
            if self._already_applied(connection, operation_id):
                return self.track(track_id)
            self._ensure_track(connection, track_id)
            before = self.track(track_id)
            if before["genre_revision"] != expected_revision:
                raise StaleDecisionError("The track's genres changed. Refresh before saving.")
            parents = {
                str(row[0]): str(row[1]) if row[1] is not None else None
                for row in connection.execute("SELECT genre_id,parent_id FROM gm_genres")
            }
            ordered = validate_order(genres, parents)
            newly_assigned = set(ordered) - set(before["genres"])
            if newly_assigned:
                marks = ",".join("?" * len(newly_assigned))
                if connection.execute(
                    f"SELECT 1 FROM gm_genres WHERE genre_id IN ({marks}) AND archived=1 LIMIT 1",
                    list(newly_assigned),
                ).fetchone():
                    raise ValueError("Archived genres cannot be newly assigned")
            if list(ordered) == before["genres"]:
                return before
            connection.execute("DELETE FROM gm_track_genres WHERE track_id=?", (track_id,))
            connection.executemany(
                "INSERT INTO gm_track_genres(track_id,genre_id,position) VALUES(?,?,?)",
                [(track_id, genre_id, index) for index, genre_id in enumerate(ordered)],
            )
            revision = expected_revision + 1
            connection.execute(
                "UPDATE gm_track_state SET genre_revision=?,reviewed_revision=NULL,"
                "updated_at_utc=? WHERE track_id=?",
                (revision, _now(), track_id),
            )
            self._record(
                connection,
                operation_id,
                track_id,
                "genres",
                before,
                {"genres": list(ordered), "reviewed": False},
                expected_revision,
                revision,
            )
            return self.track(track_id)

    def set_tag(
        self,
        track_id: str,
        tag_id: str,
        *,
        present: bool,
        expected_revision: int,
        operation_id: str,
    ) -> dict[str, Any]:
        with self._database.transaction() as connection:
            if self._already_applied(connection, operation_id):
                return self.track(track_id)
            self._ensure_track(connection, track_id)
            before = self.track(track_id)
            if before["tag_revision"] != expected_revision:
                raise StaleDecisionError("The track's tags changed. Refresh before saving.")
            if tag_id not in {
                row[0] for row in connection.execute("SELECT tag_id FROM gm_tags WHERE archived=0")
            }:
                raise ValueError("Tag is missing or archived")
            if (tag_id in before["tags"]) == present:
                return before
            if present:
                connection.execute(
                    "INSERT INTO gm_track_tags(track_id,tag_id) VALUES(?,?)", (track_id, tag_id)
                )
            else:
                connection.execute(
                    "DELETE FROM gm_track_tags WHERE track_id=? AND tag_id=?", (track_id, tag_id)
                )
            revision = expected_revision + 1
            connection.execute(
                "UPDATE gm_track_state SET tag_revision=?,updated_at_utc=? WHERE track_id=?",
                (revision, _now(), track_id),
            )
            after = self.track(track_id)
            self._record(
                connection,
                operation_id,
                track_id,
                "tags",
                before,
                after,
                expected_revision,
                revision,
            )
            return after

    @serialized_decision
    def mark_reviewed(
        self, track_id: str, *, expected_revision: int, operation_id: str
    ) -> dict[str, Any]:
        with self._database.transaction() as connection:
            if self._already_applied(connection, operation_id):
                return self.track(track_id)
            self._ensure_track(connection, track_id)
            before = self.track(track_id)
            if before["genre_revision"] != expected_revision:
                raise StaleDecisionError("The track's genres changed. Review them again.")
            if not before["genres"]:
                raise ValueError("Choose a main genre before marking the track as reviewed")
            if before["reviewed"]:
                return before
            connection.execute(
                "UPDATE gm_track_state SET reviewed_revision=?,updated_at_utc=? WHERE track_id=?",
                (expected_revision, _now(), track_id),
            )
            after = self.track(track_id)
            self._record(
                connection,
                operation_id,
                track_id,
                "review",
                before,
                after,
                expected_revision,
                expected_revision,
            )
            return after

    @serialized_decision
    def undo(self, operation_id: str) -> dict[str, Any]:
        """Restore one decision only while its result is still current."""
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM gm_decision_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            track_id = str(row["track_id"])
            if row["undone"]:
                return self.track(track_id)
            before = json.loads(str(row["before_json"]))
            after = json.loads(str(row["after_json"]))
            current = self.track(track_id)
            kind = str(row["kind"])
            if kind == "genres":
                if (
                    current["genre_revision"] != row["after_revision"]
                    or current["genres"] != after["genres"]
                    or current["reviewed"] != after["reviewed"]
                ):
                    raise StaleDecisionError("A newer genre decision prevents this undo")
                connection.execute("DELETE FROM gm_track_genres WHERE track_id=?", (track_id,))
                connection.executemany(
                    "INSERT INTO gm_track_genres(track_id,genre_id,position) VALUES(?,?,?)",
                    [(track_id, genre_id, i) for i, genre_id in enumerate(before["genres"])],
                )
                revision = current["genre_revision"] + 1
                connection.execute(
                    "UPDATE gm_track_state SET genre_revision=?,reviewed_revision=?,"
                    "updated_at_utc=? WHERE track_id=?",
                    (revision, revision if before["reviewed"] else None, _now(), track_id),
                )
            elif kind == "tags":
                if (
                    current["tag_revision"] != row["after_revision"]
                    or current["tags"] != after["tags"]
                ):
                    raise StaleDecisionError("A newer tag decision prevents this undo")
                connection.execute("DELETE FROM gm_track_tags WHERE track_id=?", (track_id,))
                connection.executemany(
                    "INSERT INTO gm_track_tags(track_id,tag_id) VALUES(?,?)",
                    [(track_id, tag_id) for tag_id in before["tags"]],
                )
                connection.execute(
                    "UPDATE gm_track_state SET tag_revision=?,updated_at_utc=? WHERE track_id=?",
                    (current["tag_revision"] + 1, _now(), track_id),
                )
            else:
                if (
                    current["genre_revision"] != row["after_revision"]
                    or current["reviewed"] != after["reviewed"]
                ):
                    raise StaleDecisionError("A newer review decision prevents this undo")
                connection.execute(
                    "UPDATE gm_track_state SET reviewed_revision=?,updated_at_utc=? "
                    "WHERE track_id=?",
                    (current["genre_revision"] if before["reviewed"] else None, _now(), track_id),
                )
            connection.execute(
                "UPDATE gm_decision_operations SET undone=1 WHERE operation_id=?",
                (operation_id,),
            )
            return self.track(track_id)

    @staticmethod
    def _ensure_track(connection: Any, track_id: str) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO gm_track_state(track_id,updated_at_utc) VALUES(?,?)",
            (track_id, _now()),
        )

    @staticmethod
    def _already_applied(connection: Any, operation_id: str) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM gm_decision_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            is not None
        )

    @staticmethod
    def _record(
        connection: Any,
        operation_id: str,
        track_id: str,
        kind: str,
        before: dict[str, Any],
        after: dict[str, Any],
        before_revision: int,
        after_revision: int,
    ) -> None:
        connection.execute(
            "INSERT INTO gm_decision_operations(operation_id,track_id,kind,before_json,"
            "after_json,before_revision,after_revision,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (
                operation_id,
                track_id,
                kind,
                json.dumps(before),
                json.dumps(after),
                before_revision,
                after_revision,
                _now(),
            ),
        )

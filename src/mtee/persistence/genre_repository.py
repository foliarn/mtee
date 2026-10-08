"""Transactional local assignments and conflict-aware operation history."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mtee.domain.genres import Genre, GenreError, Taxonomy, initial_config, name_key
from mtee.persistence.database import Database


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class GenreRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def initialize(self) -> None:
        """Bootstrap once, never restore renamed, moved, archived or deleted definitions."""
        with self.database.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM settings WHERE key='genres/initial_version'"
            ).fetchone():
                return
            config = initial_config()
            for item in config["genres"]:
                connection.execute(
                    "INSERT INTO genres(genre_id,parent_id,name,name_key,position) "
                    "VALUES(?,?,?,?,?)",
                    (
                        item["genre_id"],
                        item["parent_id"],
                        item["name"],
                        name_key(item["name"]),
                        item["position"],
                    ),
                )
            for item in config["aliases"]:
                connection.execute(
                    "INSERT INTO genre_aliases VALUES(?,?,?)",
                    (item["genre_id"], item["alias"], name_key(item["alias"])),
                )
            for item in config["meta_families"]:
                connection.execute(
                    "INSERT INTO genre_meta_families(meta_id,name,name_key) VALUES(?,?,?)",
                    (item["meta_id"], item["name"], name_key(item["name"])),
                )
                connection.executemany(
                    "INSERT INTO genre_meta_members VALUES(?,?)",
                    [(item["meta_id"], member) for member in item["members"]],
                )
            connection.execute(
                "INSERT INTO settings(key,value,updated_at_utc) VALUES(?,?,?)",
                ("genres/initial_version", encode(config["version"]), utc_now()),
            )

    @staticmethod
    def taxonomy_from(connection: sqlite3.Connection) -> Taxonomy:
        return Taxonomy(
            Genre(
                str(row["genre_id"]),
                row["parent_id"],
                str(row["name"]),
                int(row["position"]),
                bool(row["archived"]),
                int(row["revision"]),
            )
            for row in connection.execute("SELECT * FROM genres")
        )

    def taxonomy_snapshot(self) -> list[dict[str, Any]]:
        taxonomy = self.taxonomy_from(self.database.connection())
        return [
            dict(asdict(node), path=taxonomy.path(node.genre_id))
            for node in taxonomy.nodes.values()
        ]

    @staticmethod
    def states_from(
        connection: sqlite3.Connection, ids: Sequence[str]
    ) -> dict[str, dict[str, Any]]:
        result = {
            identity: {
                "revision": 0,
                "manual_edit": 0,
                "seed_run_id": None,
                "seed_folder": None,
                "links": [],
            }
            for identity in ids
        }
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            marks = ",".join("?" for _ in chunk)
            for row in connection.execute(
                f"SELECT * FROM genre_track_state WHERE track_id IN ({marks})", chunk
            ):
                result[str(row["track_id"])].update(
                    {
                        key: row[key]
                        for key in ("revision", "manual_edit", "seed_run_id", "seed_folder")
                    }
                )
            for row in connection.execute(
                f"SELECT * FROM track_genres WHERE track_id IN ({marks}) ORDER BY genre_id", chunk
            ):
                result[str(row["track_id"])]["links"].append(
                    {
                        key: row[key]
                        for key in ("genre_id", "provenance", "operation_id", "assigned_at_utc")
                    }
                )
        return result

    def track_assignments(self, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """One grouped read per chunk, never one query per QML delegate."""
        connection = self.database.connection()
        # Read tree and links from the same snapshot, even during concurrent edits.
        owns_snapshot = not connection.in_transaction
        if owns_snapshot:
            connection.execute("BEGIN")
        try:
            taxonomy = self.taxonomy_from(connection)
            states = self.states_from(connection, ids)
            result = {}
            for identity, state in states.items():
                assigned = [link["genre_id"] for link in state["links"]]
                result[identity] = {
                    "genreIds": assigned,
                    "mteeGenres": sorted(taxonomy.path(value) for value in assigned),
                    "genreFamilies": sorted(
                        taxonomy.path(value) for value in taxonomy.families(assigned)
                    ),
                    "genreRevision": state["revision"],
                    "genreSeedFolder": state["seed_folder"] or "",
                }
            return result
        finally:
            if owns_snapshot:
                connection.execute("ROLLBACK")

    @staticmethod
    def write_state(connection: sqlite3.Connection, identity: str, state: dict[str, Any]) -> None:
        connection.execute("DELETE FROM track_genres WHERE track_id=?", (identity,))
        connection.executemany(
            "INSERT INTO track_genres VALUES(?,?,?,?,?)",
            [
                (
                    identity,
                    link["genre_id"],
                    link["provenance"],
                    link["operation_id"],
                    link["assigned_at_utc"],
                )
                for link in state["links"]
            ],
        )
        connection.execute(
            "INSERT INTO genre_track_state VALUES(?,?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET "
            "revision=excluded.revision,manual_edit=excluded.manual_edit,"
            "seed_run_id=excluded.seed_run_id,seed_folder=excluded.seed_folder",
            (
                identity,
                state["revision"],
                state["manual_edit"],
                state["seed_run_id"],
                state["seed_folder"],
            ),
        )

    @staticmethod
    def record_operation(
        connection: sqlite3.Connection,
        operation_id: str,
        kind: str,
        before: dict[str, dict[str, Any]],
        after: dict[str, dict[str, Any]],
    ) -> None:
        connection.execute(
            "INSERT INTO genre_operations VALUES(?,?,'committed',NULL,?)",
            (operation_id, kind, utc_now()),
        )
        connection.executemany(
            "INSERT INTO genre_operation_items VALUES(?,?,?,?,?)",
            [
                (
                    operation_id,
                    identity,
                    encode(state),
                    encode(after[identity]),
                    after[identity]["revision"],
                )
                for identity, state in before.items()
            ],
        )

    def change_membership(
        self,
        track_ids: Sequence[str],
        genre_ids: Iterable[str],
        *,
        enabled: bool,
        expected_revisions: dict[str, int] | None = None,
        cancel: Callable[[], None] | None = None,
    ) -> str:
        identities = list(dict.fromkeys(track_ids))
        values = set(genre_ids)
        operation_id = str(uuid4())
        with self.database.transaction() as connection:
            taxonomy = self.taxonomy_from(connection)
            taxonomy.normalize(values)
            if enabled and any(taxonomy.nodes[value].archived for value in values):
                raise GenreError("Archived genres cannot receive new assignments")
            before = self.states_from(connection, identities)
            after = {}
            now = utc_now()
            for identity, state in before.items():
                if cancel:
                    cancel()
                if not connection.execute(
                    "SELECT 1 FROM tracks WHERE track_id=?", (identity,)
                ).fetchone():
                    raise GenreError(f"Missing track: {identity}")
                if (
                    expected_revisions is not None
                    and expected_revisions.get(identity) != state["revision"]
                ):
                    raise GenreError(f"Changed track: {identity}")
                existing = {link["genre_id"]: link for link in state["links"]}
                final = (
                    taxonomy.normalize(set(existing) | values)
                    if enabled
                    else taxonomy.remove(existing, values)
                )
                next_state = dict(
                    state,
                    revision=state["revision"] + 1,
                    manual_edit=1,
                    links=[
                        existing.get(value)
                        or {
                            "genre_id": value,
                            "provenance": "manual",
                            "operation_id": operation_id,
                            "assigned_at_utc": now,
                        }
                        for value in sorted(final)
                    ],
                )
                self.write_state(connection, identity, next_state)
                after[identity] = next_state
            self.record_operation(connection, operation_id, "manual_membership", before, after)
            if cancel:
                cancel()
        return operation_id

    def undo(self, operation_id: str, *, cancel: Callable[[], None] | None = None) -> str:
        inverse_id = str(uuid4())
        with self.database.transaction() as connection:
            operation = connection.execute(
                "SELECT * FROM genre_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if operation is None or operation["status"] != "committed":
                raise GenreError("Operation is missing or already undone")
            items = connection.execute(
                "SELECT * FROM genre_operation_items WHERE operation_id=?", (operation_id,)
            ).fetchall()
            current = self.states_from(connection, [str(item["target_id"]) for item in items])
            restore = {}
            taxonomy = self.taxonomy_from(connection)
            for item in items:
                identity = str(item["target_id"])
                if current[identity] != json.loads(item["after_json"]):
                    raise GenreError(f"Undo conflict: {identity}")
                if not connection.execute(
                    "SELECT 1 FROM tracks WHERE track_id=?", (identity,)
                ).fetchone():
                    raise GenreError(f"Missing track: {identity}")
                state = json.loads(item["before_json"])
                taxonomy.normalize(link["genre_id"] for link in state["links"])
                state["revision"] = current[identity]["revision"] + 1
                restore[identity] = state
            for identity, state in restore.items():
                if cancel:
                    cancel()
                self.write_state(connection, identity, state)
            self.record_operation(connection, inverse_id, "undo", current, restore)
            connection.execute(
                "UPDATE genre_operations SET status='undone',inverse_operation_id=? "
                "WHERE operation_id=?",
                (inverse_id, operation_id),
            )
            if cancel:
                cancel()
        return inverse_id

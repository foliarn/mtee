"""Targeted, reversible catalog changes. No filesystem metadata is involved."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from mtee.domain.genres import Genre, GenreError, Taxonomy, name_key
from mtee.persistence.genre_repository import GenreRepository, utc_now
from mtee.services.genre_seed_service import protect_destination


class GenreManagerRepository(GenreRepository):
    def catalog(self) -> dict[str, Any]:
        connection = self.database.connection()
        connection.execute("BEGIN")
        try:
            tree = self.taxonomy_from(connection)
            assignments: dict[str, set[str]] = {identity: set() for identity in tree.nodes}
            for row in connection.execute("SELECT track_id,genre_id FROM track_genres"):
                for identity in (row["genre_id"], *tree.ancestors(row["genre_id"])):
                    assignments[identity].add(row["track_id"])
            genres = self.taxonomy_snapshot()
            for node in genres:
                node["count"] = len(assignments[node["genre_id"]])
                node["aliases"] = [
                    r[0]
                    for r in connection.execute(
                        "SELECT alias FROM genre_aliases WHERE genre_id=? ORDER BY alias_key",
                        (node["genre_id"],),
                    )
                ]
                node["depth"] = len(tree.ancestors(node["genre_id"]))
                node["assignable"] = not any(
                    tree.nodes[i].archived
                    for i in (node["genre_id"], *tree.ancestors(node["genre_id"]))
                )
            genres.sort(
                key=lambda n: tuple(
                    (tree.nodes[i].position, tree.nodes[i].name)
                    for i in reversed((n["genre_id"], *tree.ancestors(n["genre_id"])))
                )
            )
            metas = [
                dict(row)
                for row in connection.execute("SELECT * FROM genre_meta_families ORDER BY name_key")
            ]
            for meta in metas:
                meta["members"] = [
                    r[0]
                    for r in connection.execute(
                        "SELECT genre_id FROM genre_meta_members WHERE meta_id=? ORDER BY genre_id",
                        (meta["meta_id"],),
                    )
                ]
            tags = [
                dict(row)
                for row in connection.execute("SELECT * FROM local_tags ORDER BY name_key")
            ]
            for tag in tags:
                tag["count"] = connection.execute(
                    "SELECT count(*) FROM track_local_tags WHERE tag_id=?", (tag["tag_id"],)
                ).fetchone()[0]
            return {"genres": genres, "metas": metas, "tags": tags}
        finally:
            connection.execute("ROLLBACK")

    @staticmethod
    def entity(connection: sqlite3.Connection, kind: str, identity: str) -> dict[str, Any]:
        table, key = {
            "genre": ("genres", "genre_id"),
            "meta": ("genre_meta_families", "meta_id"),
            "tag": ("local_tags", "tag_id"),
        }[kind]
        row = connection.execute(f"SELECT * FROM {table} WHERE {key}=?", (identity,)).fetchone()
        result: dict[str, Any] = {
            "revision": int(row["revision"]) if row else 0,
            "row": dict(row) if row else None,
        }
        if kind == "genre":
            result["aliases"] = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM genre_aliases WHERE genre_id=? ORDER BY alias_key", (identity,)
                )
            ]
            result["members"] = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM genre_meta_members WHERE genre_id=? ORDER BY meta_id",
                    (identity,),
                )
            ]
        if kind == "meta":
            result["members"] = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM genre_meta_members WHERE meta_id=? ORDER BY genre_id",
                    (identity,),
                )
            ]
        if kind == "tag":
            result["links"] = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM track_local_tags WHERE tag_id=? ORDER BY track_id", (identity,)
                )
            ]
        return result

    def edit(
        self,
        kind: str,
        action: str,
        identity: str,
        values: dict[str, Any],
        expected: int | None = None,
        cancel: Callable[[], None] | None = None,
    ) -> dict[str, str]:
        if kind not in {"genre", "meta", "tag"}:
            raise GenreError("Unknown catalog type")
        identity = identity or str(uuid4())
        operation = str(uuid4())
        backup = ""
        if action == "force_delete":
            if kind != "genre" or values.get("confirmation") != identity:
                raise GenreError("Confirm the selected subtree before deleting it")
            roots = [
                str(r[0])
                for r in self.database.connection().execute("SELECT path FROM library_roots")
            ]
            destination = self.database.backup_path_for(self.database.schema_version())
            protect_destination(destination, roots)
            backup = str(self.database.backup_to(destination))
        with self.database.transaction() as connection:
            before = {f"{kind}:{identity}": self.entity(connection, kind, identity)}
            state = before[f"{kind}:{identity}"]
            row = state["row"]
            if action == "create":
                if row is not None:
                    raise GenreError("Definition already exists")
            elif row is None or expected != row["revision"]:
                raise GenreError("Definition changed; reload before editing")
            table, key = {
                "genre": ("genres", "genre_id"),
                "meta": ("genre_meta_families", "meta_id"),
                "tag": ("local_tags", "tag_id"),
            }[kind]
            if action in {"delete", "force_delete"}:
                targets = {identity}
                if kind == "genre":
                    tree = self.taxonomy_from(connection)
                    targets |= {i for i in tree.nodes if identity in tree.ancestors(i)}
                    linked = connection.execute(
                        "SELECT 1 FROM track_genres WHERE genre_id=?", (identity,)
                    ).fetchone()
                    membership = state.get("members")
                    if action == "delete" and (len(targets) > 1 or linked or membership):
                        raise GenreError(
                            "This genre has children or links. Archive it or use Settings > "
                            "Library > Genres > Advanced."
                        )
                    all_ids = [
                        r[0]
                        for r in connection.execute("SELECT DISTINCT track_id FROM track_genres")
                    ]
                    all_states = self.states_from(connection, all_ids)
                    ids = [
                        i
                        for i, state in all_states.items()
                        if any(link["genre_id"] in targets for link in state["links"])
                    ]
                    track_before = self.states_from(connection, ids)
                    before.update({f"track:{i}": state for i, state in track_before.items()})
                    for i, track_state in track_before.items():
                        if cancel:
                            cancel()
                        changed = dict(
                            track_state,
                            revision=track_state["revision"] + 1,
                            manual_edit=1,
                            links=[
                                link
                                for link in track_state["links"]
                                if link["genre_id"] not in targets
                            ],
                        )
                        self.write_state(connection, i, changed)
                    for target in targets:
                        before[f"genre:{target}"] = self.entity(connection, "genre", target)
                    for target in sorted(
                        targets, key=lambda i: len(tree.ancestors(i)), reverse=True
                    ):
                        connection.execute("DELETE FROM genres WHERE genre_id=?", (target,))
                else:
                    if kind == "tag" and state["links"]:
                        raise GenreError("This tag has assignments; archive it instead")
                    connection.execute(f"DELETE FROM {table} WHERE {key}=?", (identity,))
            else:
                name = str(values.get("name", row["name"] if row else "")).strip()
                if not name_key(name):
                    raise GenreError("Enter a name")
                archived = int(values.get("archived", row["archived"] if row else 0))
                revision = row["revision"] + 1 if row else 0
                if kind == "genre":
                    parent = values.get("parent_id", row["parent_id"] if row else None) or None
                    default_position = (
                        row["position"]
                        if row
                        else connection.execute(
                            "SELECT COALESCE(MAX(position),-1)+1 FROM genres WHERE parent_id IS ?",
                            (parent,),
                        ).fetchone()[0]
                    )
                    position = int(values.get("position", default_position))
                    tree = self.taxonomy_from(connection)
                    candidate = Genre(identity, parent, name, position, bool(archived), revision)
                    Taxonomy(
                        [candidate if i == identity else n for i, n in tree.nodes.items()]
                        + ([] if row else [candidate])
                    )
                    if parent and tree.nodes[parent].archived:
                        raise GenreError("Cannot move into an archived parent")
                    connection.execute(
                        "INSERT INTO genres VALUES(?,?,?,?,?,?,?) ON CONFLICT(genre_id) DO "
                        "UPDATE SET "
                        "parent_id=excluded.parent_id,name=excluded.name,name_key=excluded.name_key,position=excluded.position,archived=excluded.archived,revision=excluded.revision",
                        (identity, parent, name, name_key(name), position, archived, revision),
                    )
                    if "aliases" in values:
                        connection.execute(
                            "DELETE FROM genre_aliases WHERE genre_id=?", (identity,)
                        )
                        for alias in dict.fromkeys(str(a).strip() for a in values["aliases"]):
                            if name_key(alias):
                                connection.execute(
                                    "INSERT INTO genre_aliases VALUES(?,?,?)",
                                    (identity, alias, name_key(alias)),
                                )
                    # Moving a node may create ancestor redundancy on existing tracks.
                    new_tree = self.taxonomy_from(connection)
                    ids = [
                        r[0]
                        for r in connection.execute("SELECT DISTINCT track_id FROM track_genres")
                    ]
                    for i, state in self.states_from(connection, ids).items():
                        if cancel:
                            cancel()
                        normalized = new_tree.normalize(link["genre_id"] for link in state["links"])
                        if len(normalized) != len(state["links"]):
                            before[f"track:{i}"] = state
                            self.write_state(
                                connection,
                                i,
                                dict(
                                    state,
                                    revision=state["revision"] + 1,
                                    links=[
                                        link
                                        for link in state["links"]
                                        if link["genre_id"] in normalized
                                    ],
                                ),
                            )
                elif kind == "meta":
                    connection.execute(
                        "INSERT INTO genre_meta_families VALUES(?,?,?,?,?) ON CONFLICT(meta_id) "
                        "DO UPDATE SET "
                        "name=excluded.name,name_key=excluded.name_key,archived=excluded.archived,revision=excluded.revision",
                        (identity, name, name_key(name), archived, revision),
                    )
                    if "members" in values:
                        tree = self.taxonomy_from(connection)
                        members = set(values["members"])
                        for member in members:
                            tree.ancestors(member)
                        connection.execute(
                            "DELETE FROM genre_meta_members WHERE meta_id=?", (identity,)
                        )
                        connection.executemany(
                            "INSERT INTO genre_meta_members VALUES(?,?)",
                            [(identity, m) for m in members],
                        )
                else:
                    color = values.get("color", row["color"] if row else None)
                    connection.execute(
                        "INSERT INTO local_tags VALUES(?,?,?,?,?,?) ON CONFLICT(tag_id) DO "
                        "UPDATE SET "
                        "name=excluded.name,name_key=excluded.name_key,color=excluded.color,archived=excluded.archived,revision=excluded.revision",
                        (identity, name, name_key(name), color, archived, revision),
                    )
            after = {
                target: (
                    self.states_from(connection, [target[6:]])[target[6:]]
                    if target.startswith("track:")
                    else self.entity(connection, *target.split(":", 1))
                )
                for target in before
            }
            self.record_operation(connection, operation, "catalog", before, after)
            if cancel:
                cancel()
        return {"operation": operation, "identity": identity, "backup": backup}

    @staticmethod
    def put_row(connection: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
        columns = list(row)
        connection.execute(
            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            list(row.values()),
        )

    def undo_catalog(self, operation: str) -> str:
        inverse = str(uuid4())
        with self.database.transaction() as connection:
            op = connection.execute(
                "SELECT * FROM genre_operations WHERE operation_id=?", (operation,)
            ).fetchone()
            if not op or op["status"] != "committed" or op["kind"] != "catalog":
                raise GenreError("Operation is missing or already undone")
            items = connection.execute(
                "SELECT * FROM genre_operation_items WHERE operation_id=?", (operation,)
            ).fetchall()
            before, restore = {}, {}
            for item in items:
                target = item["target_id"]
                kind, identity = target.split(":", 1)
                current = (
                    self.states_from(connection, [identity])[identity]
                    if kind == "track"
                    else self.entity(connection, kind, identity)
                )
                if not self.undo_state_matches(
                    connection, target, current, json.loads(item["after_json"]), op
                ):
                    raise GenreError(f"Undo conflict: {target}")
                before[target] = current
                state = json.loads(item["before_json"])
                state["revision"] = current["revision"] + 1
                if state.get("row"):
                    state["row"]["revision"] = state["revision"]
                restore[target] = state
            # Unlink changed tracks first, then restore definitions in parent order.
            for target in restore:
                if target.startswith("track:"):
                    connection.execute("DELETE FROM track_genres WHERE track_id=?", (target[6:],))
            defs = {
                target: state
                for target, state in restore.items()
                if not target.startswith("track:")
            }
            for target in defs:
                kind, identity = target.split(":", 1)
                if kind == "genre":
                    connection.execute("DELETE FROM genre_aliases WHERE genre_id=?", (identity,))
                    connection.execute(
                        "DELETE FROM genre_meta_members WHERE genre_id=?", (identity,)
                    )
                elif kind == "meta":
                    connection.execute(
                        "DELETE FROM genre_meta_members WHERE meta_id=?", (identity,)
                    )
            # Existing rows use UPDATE: deleting a parent would violate references.
            pending = dict(defs)
            while pending:
                progressed = False
                for target, state in list(pending.items()):
                    kind, identity = target.split(":", 1)
                    table, key = {
                        "genre": ("genres", "genre_id"),
                        "meta": ("genre_meta_families", "meta_id"),
                        "tag": ("local_tags", "tag_id"),
                    }[kind]
                    row = state["row"]
                    if (
                        row
                        and kind == "genre"
                        and row["parent_id"]
                        and not connection.execute(
                            "SELECT 1 FROM genres WHERE genre_id=?", (row["parent_id"],)
                        ).fetchone()
                    ):
                        continue
                    if row:
                        if connection.execute(
                            f"SELECT 1 FROM {table} WHERE {key}=?", (identity,)
                        ).fetchone():
                            cols = [c for c in row if c != key]
                            connection.execute(
                                f"UPDATE {table} SET "
                                + ",".join(f"{c}=?" for c in cols)
                                + f" WHERE {key}=?",
                                [row[c] for c in cols] + [identity],
                            )
                        else:
                            self.put_row(connection, table, row)
                    else:
                        connection.execute(f"DELETE FROM {table} WHERE {key}=?", (identity,))
                    del pending[target]
                    progressed = True
                if not progressed:
                    raise GenreError("Missing parent during undo")
            self.taxonomy_from(connection)
            for target, state in defs.items():
                kind, identity = target.split(":", 1)
                for row in state.get("aliases", []):
                    self.put_row(connection, "genre_aliases", row)
                for row in state.get("members", []):
                    self.put_row(connection, "genre_meta_members", row)
            for target, state in restore.items():
                if target.startswith("track:"):
                    self.write_state(connection, target[6:], state)
            self.record_operation(connection, inverse, "catalog", before, restore)
            connection.execute(
                "UPDATE genre_operations SET status='undone',inverse_operation_id=? "
                "WHERE operation_id=?",
                (inverse, operation),
            )
        return inverse

    @staticmethod
    def tag_state(connection: sqlite3.Connection, identity: str) -> dict[str, Any]:
        base = GenreRepository.states_from(connection, [identity])[identity]
        return {
            "revision": base["revision"],
            "links": [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM track_local_tags WHERE track_id=? ORDER BY tag_id", (identity,)
                )
            ],
        }

    def change_tags(
        self, ids: list[str], tag: str, enabled: bool, revisions: dict[str, int], cancel=None
    ) -> str:
        operation = str(uuid4())
        with self.database.transaction() as connection:
            definition = connection.execute(
                "SELECT * FROM local_tags WHERE tag_id=?", (tag,)
            ).fetchone()
            if not definition or (enabled and definition["archived"]):
                raise GenreError("Missing or archived local tag")
            before, after = {}, {}
            for identity in dict.fromkeys(ids):
                if cancel:
                    cancel()
                if not connection.execute(
                    "SELECT 1 FROM tracks WHERE track_id=?", (identity,)
                ).fetchone():
                    raise GenreError("Missing track")
                state = self.tag_state(connection, identity)
                if revisions.get(identity) != state["revision"]:
                    raise GenreError("Changed track; reload before tagging")
                before[f"tagtrack:{identity}"] = state
                if enabled:
                    connection.execute(
                        "INSERT OR IGNORE INTO track_local_tags VALUES(?,?,?,?)",
                        (identity, tag, operation, utc_now()),
                    )
                else:
                    connection.execute(
                        "DELETE FROM track_local_tags WHERE track_id=? AND tag_id=?",
                        (identity, tag),
                    )
                base = self.states_from(connection, [identity])[identity]
                self.write_state(connection, identity, dict(base, revision=base["revision"] + 1))
                after[f"tagtrack:{identity}"] = self.tag_state(connection, identity)
            self.record_operation(connection, operation, "tags", before, after)
            if cancel:
                cancel()
        return operation

    def undo_tags(self, operation: str) -> str:
        inverse = str(uuid4())
        with self.database.transaction() as connection:
            op = connection.execute(
                "SELECT * FROM genre_operations WHERE operation_id=?", (operation,)
            ).fetchone()
            if not op or op["status"] != "committed" or op["kind"] != "tags":
                raise GenreError("Operation is missing or already undone")
            before, after = {}, {}
            for item in connection.execute(
                "SELECT * FROM genre_operation_items WHERE operation_id=?", (operation,)
            ).fetchall():
                target = item["target_id"]
                identity = target.split(":", 1)[1]
                state = self.tag_state(connection, identity)
                if not self.undo_state_matches(
                    connection, target, state, json.loads(item["after_json"]), op
                ):
                    raise GenreError("Undo conflict: " + identity)
                before[target] = state
                restore = json.loads(item["before_json"])
                connection.execute("DELETE FROM track_local_tags WHERE track_id=?", (identity,))
                for row in restore["links"]:
                    self.put_row(connection, "track_local_tags", row)
                base = self.states_from(connection, [identity])[identity]
                self.write_state(connection, identity, dict(base, revision=base["revision"] + 1))
                after[target] = self.tag_state(connection, identity)
            self.record_operation(connection, inverse, "tags", before, after)
            connection.execute(
                "UPDATE genre_operations SET status='undone',inverse_operation_id=? "
                "WHERE operation_id=?",
                (inverse, operation),
            )
        return inverse

    def undo_any(self, operation: str) -> str:
        row = (
            self.database.connection()
            .execute("SELECT kind FROM genre_operations WHERE operation_id=?", (operation,))
            .fetchone()
        )
        if not row:
            raise GenreError("Missing operation")
        if row["kind"] == "catalog":
            return self.undo_catalog(operation)
        if row["kind"] == "tags":
            return self.undo_tags(operation)
        return self.undo(operation)

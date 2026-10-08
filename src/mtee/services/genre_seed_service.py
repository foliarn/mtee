"""Reviewable folder seeding, read-only preview and atomic guarded application."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from mtee.domain.genres import (
    RESOURCES,
    GenreError,
    initial_config,
    initial_taxonomy,
    jungle_or_breaks,
)
from mtee.persistence.database import Database
from mtee.persistence.genre_repository import GenreRepository, encode, utc_now


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def protect_destination(destination: Path, roots: list[str]) -> None:
    resolved = destination.resolve()
    if any(resolved.is_relative_to(Path(root).resolve()) for root in roots):
        raise GenreError("Destination is inside a protected library root")


def verified_copy(source: Path, destination: Path) -> Path:
    """Coherent WAL copy; exclusive destination and reopen verification."""
    connection = readonly(source)
    try:
        roots = [str(row[0]) for row in connection.execute("SELECT path FROM library_roots")]
        protect_destination(destination, roots)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.touch(exist_ok=False)
        target = sqlite3.connect(destination)
        try:
            connection.backup(target)
        finally:
            target.close()
        check = readonly(destination)
        try:
            if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise GenreError("Backup verification failed")
        finally:
            check.close()
        return destination
    finally:
        connection.close()


class GenreSeedService:
    def __init__(self, path: Path, *, mapping: dict[str, Any] | None = None) -> None:
        self.path = path.resolve()
        self.mapping = (
            mapping
            if mapping is not None
            else json.loads((RESOURCES / "folder_mapping.json").read_text(encoding="utf-8"))
        )
        self.config_hash = digest({"mapping": self.mapping, "taxonomy": initial_config()})
        self._validate_mapping()

    def _validate_mapping(self) -> None:
        taxonomy = initial_taxonomy()
        seen = set()
        if self.mapping.get("version") != 1:
            raise GenreError("Unsupported mapping version")
        for rule in self.mapping["rules"]:
            key = rule["folder"].replace("\\", "/")
            if key in seen or rule.get("scope") not in ("exact", "subtree"):
                raise GenreError("Duplicate or invalid folder rule")
            if key.startswith("/") or ".." in key.split("/"):
                raise GenreError("Folder rules must be relative")
            seen.add(key)
            taxonomy.normalize(rule.get("genres", []))
            if rule.get("rule") not in (None, "analysis_bpm"):
                raise GenreError("Unsupported folder rule")

    def preview(self, root_id: str) -> dict[str, Any]:
        connection = readonly(self.path)
        try:
            connection.execute("BEGIN")
            return self._preview(connection, root_id)
        finally:
            connection.close()

    def _preview(self, connection: sqlite3.Connection, root_id: str) -> dict[str, Any]:
        root = connection.execute(
            "SELECT root_id,path,name FROM library_roots WHERE root_id=?", (root_id,)
        ).fetchone()
        if root is None:
            raise GenreError("Unknown root UUID")
        schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if schema not in (20, 21):
            raise GenreError("Preview requires schema 020 or 021")
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT rt.track_id,rt.relative_path,rt.present,a.bpm "
                "FROM root_tracks rt JOIN tracks t USING(track_id) "
                "LEFT JOIN track_analysis a USING(track_id) "
                "WHERE rt.root_id=? ORDER BY rt.track_id",
                (root_id,),
            )
        ]
        for row in rows:
            if row["bpm"] is not None and not math.isfinite(row["bpm"]):
                row["bpm"] = "invalid:" + str(row["bpm"])
        initialized = schema == 21 and bool(
            connection.execute(
                "SELECT 1 FROM settings WHERE key='genres/initial_version'"
            ).fetchone()
        )
        taxonomy = GenreRepository.taxonomy_from(connection) if initialized else initial_taxonomy()
        node_data = sorted(
            (asdict(node) for node in taxonomy.nodes.values()), key=lambda item: item["genre_id"]
        )
        before = (
            GenreRepository.states_from(connection, [row["track_id"] for row in rows])
            if schema == 21
            else {
                row["track_id"]: {
                    "revision": 0,
                    "manual_edit": 0,
                    "seed_run_id": None,
                    "seed_folder": None,
                    "links": [],
                }
                for row in rows
            }
        )
        results = []
        summary: Counter[str] = Counter()
        folder_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            relative = str(row["relative_path"]).replace("\\", "/")
            folder = relative.rsplit("/", 1)[0] if "/" in relative else ""
            matching = [
                rule
                for rule in self.mapping["rules"]
                if folder == rule["folder"]
                or (rule["scope"] == "subtree" and folder.startswith(rule["folder"] + "/"))
            ]
            state = before[row["track_id"]]
            assigned: list[str] = []
            reason = "eligible"
            if not row["present"]:
                reason = "absent"
            elif state["manual_edit"] or state["seed_run_id"] or state["links"]:
                reason = "preserved"
            elif len(matching) > 1:
                reason = "mapping_conflict"
            elif not matching:
                reason = "unmapped"
            elif matching[0].get("excluded"):
                reason = "excluded"
            elif matching[0].get("rule") == "analysis_bpm":
                path = jungle_or_breaks(
                    row["bpm"] if isinstance(row["bpm"], (int, float)) else None
                )
                if path is None:
                    reason = "missing_bpm"
                else:
                    initial = initial_taxonomy()
                    assigned = [
                        node.genre_id
                        for node in initial.nodes.values()
                        if initial.path(node.genre_id) == path
                    ]
                    taxonomy.normalize(assigned)
            else:
                assigned = sorted(taxonomy.normalize(matching[0].get("genres", [])))
            if any(taxonomy.nodes[value].archived for value in assigned):
                raise GenreError("Seed references an archived genre")
            summary[reason] += 1
            if row["present"]:
                summary["present"] += 1
            if assigned:
                summary["assigned_tracks"] += 1
                summary["assignments"] += len(assigned)
                summary["hybrids"] += int(len(assigned) > 1)
                for family in taxonomy.families(assigned):
                    summary["family:" + taxonomy.path(family)] += 1
            elif row["present"] and reason != "preserved":
                summary["without_genre"] += 1
            folder_counts[folder][reason] += 1
            for value in assigned:
                folder_counts[folder][taxonomy.path(value)] += 1
            results.append(
                dict(
                    row,
                    folder=folder,
                    genres=assigned,
                    reason=reason,
                    paths=[taxonomy.path(value) for value in assigned],
                )
            )
        preconditions = {"root": dict(root), "rows": rows, "states": before, "taxonomy": node_data}
        plan = {
            "version": 1,
            "database": str(self.path),
            "root_id": root_id,
            "config_hash": self.config_hash,
            "preconditions_hash": digest(preconditions),
            "rows": results,
            "summary": dict(summary),
            "folders": {key: dict(value) for key, value in sorted(folder_counts.items())},
        }
        plan["integrity"] = digest(plan)
        return plan

    def write_report(self, plan: dict[str, Any], destination: Path) -> None:
        connection = readonly(self.path)
        try:
            protect_destination(
                destination,
                [str(row[0]) for row in connection.execute("SELECT path FROM library_roots")],
            )
        finally:
            connection.close()
        destination.mkdir(parents=True, exist_ok=True)
        # Reviewed reports are immutable; a refreshed preview uses a new directory.
        with (destination / "plan.json").open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        summary = plan["summary"]
        lines = [
            "# Aperçu des genres des morceaux",
            "",
            "Aucune modification de la base réelle.",
            "",
            f"{summary.get('present', 0)} morceaux présents ; "
            f"{summary.get('absent', 0)} absents ignorés.",
            f"{summary.get('assigned_tracks', 0)} morceaux recevront "
            f"{summary.get('assignments', 0)} affectations ; "
            f"{summary.get('hybrids', 0)} morceaux sont hybrides.",
            f"{summary.get('without_genre', 0)} présents restent sans genre, dont "
            f"{summary.get('excluded', 0)} exclus et "
            f"{summary.get('missing_bpm', 0)} sans BPM valide.",
            f"{summary.get('preserved', 0)} morceaux déjà traités ou corrigés seront conservés.",
            "",
            "Le lot a été essayé sur une copie lorsque cela est indiqué dans le compte rendu. "
            "Cet aperçu porte uniquement sur les genres locaux MTEE, "
            "sans écriture de fichiers audio.",
            "",
            "| Dossier | Présents | Absents | Affectations directes | Sans genre / conservés |",
            "|---|---:|---:|---|---|",
        ]
        reasons = {
            "eligible",
            "absent",
            "excluded",
            "preserved",
            "unmapped",
            "mapping_conflict",
            "missing_bpm",
        }
        for folder, values in plan["folders"].items():
            escaped = folder.replace("|", "\\|") or "(root)"
            counts = "; ".join(
                f"{key}: {value}" for key, value in values.items() if key not in reasons
            ).replace("|", "\\|")
            notes = "; ".join(
                f"{label}: {values[key]}"
                for key, label in [
                    ("excluded", "exclus"),
                    ("missing_bpm", "BPM absent/invalide"),
                    ("preserved", "conservés"),
                    ("unmapped", "sans correspondance"),
                    ("mapping_conflict", "conflit"),
                ]
                if values.get(key)
            )
            present = sum(values.get(key, 0) for key in reasons if key != "absent")
            lines.append(
                f"| {escaped} | {present} | {values.get('absent', 0)} | "
                f"{counts or '—'} | {notes or '—'} |"
            )
        with (destination / "summary.md").open("x", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")

    def apply(
        self, plan: dict[str, Any], *, cancel: Callable[[], None] | None = None
    ) -> dict[str, str]:
        connection = readonly(self.path)
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] == 21:
                for receipt in connection.execute(
                    "SELECT r.run_id,r.plan_json,r.backup_path FROM genre_seed_runs r "
                    "JOIN genre_operations o ON o.operation_id=r.run_id "
                    "WHERE r.root_id=? AND o.status='committed'",
                    (plan.get("root_id"),),
                ):
                    if plan == json.loads(receipt["plan_json"]) and plan["database"] == str(
                        self.path
                    ):
                        return {
                            "operation_id": receipt["run_id"],
                            "backup": receipt["backup_path"],
                            "already_applied": "true",
                        }
        finally:
            connection.close()
        if plan != self.preview(str(plan.get("root_id", ""))):
            raise GenreError(
                "Plan is stale, modified, or belongs to another database; regenerate preview"
            )
        if plan["summary"].get("mapping_conflict", 0):
            raise GenreError("Resolve mapping conflicts before applying")
        if not any(
            row["reason"] in ("eligible", "excluded", "missing_bpm") for row in plan["rows"]
        ):
            return {"operation_id": "", "backup": "", "already_applied": "true"}
        if cancel:
            cancel()
        connection = readonly(self.path)
        try:
            protect_destination(
                self.path,
                [str(row[0]) for row in connection.execute("SELECT path FROM library_roots")],
            )
            schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        finally:
            connection.close()
        backup = self.path.with_name(f"{self.path.name}.v{schema}.{uuid4().hex}.genre-seed.backup")
        verified_copy(self.path, backup)
        database = Database(self.path)
        try:
            database.migrate()
            repository = GenreRepository(database)
            repository.initialize()
            operation_id = str(uuid4())
            with database.transaction() as connection:
                if plan != self._preview(connection, plan["root_id"]):
                    raise GenreError("Plan changed during application; no assignments written")
                targets = [
                    row
                    for row in plan["rows"]
                    if row["reason"] not in ("preserved", "absent", "mapping_conflict", "unmapped")
                ]
                before = repository.states_from(connection, [row["track_id"] for row in targets])
                after = {}
                now = utc_now()
                connection.execute(
                    "INSERT INTO genre_seed_runs VALUES(?,?,?,?,?)",
                    (operation_id, plan["root_id"], encode(plan), str(backup), now),
                )
                for row in targets:
                    if cancel:
                        cancel()
                    identity = row["track_id"]
                    state = dict(
                        before[identity],
                        revision=before[identity]["revision"] + 1,
                        seed_run_id=operation_id,
                        seed_folder=row["folder"],
                        links=[
                            {
                                "genre_id": value,
                                "provenance": "folder",
                                "operation_id": operation_id,
                                "assigned_at_utc": now,
                            }
                            for value in row["genres"]
                        ],
                    )
                    repository.write_state(connection, identity, state)
                    connection.execute(
                        "INSERT INTO genre_seed_tracks VALUES(?,?,?)",
                        (operation_id, identity, row["relative_path"]),
                    )
                    after[identity] = state
                repository.record_operation(connection, operation_id, "folder_seed", before, after)
                if cancel:
                    cancel()
            return {"operation_id": operation_id, "backup": str(backup)}
        finally:
            database.close()

    def undo(self, operation_id: str) -> str:
        # Recovery does not apply migrations or restore the whole database.
        database = Database(self.path)
        try:
            if database.schema_version() != 21:
                raise GenreError("Recovery requires schema 021")
            connection = database.connection()
            protect_destination(
                self.path,
                [str(row[0]) for row in connection.execute("SELECT path FROM library_roots")],
            )
            return GenreRepository(database).undo(operation_id)
        finally:
            database.close()

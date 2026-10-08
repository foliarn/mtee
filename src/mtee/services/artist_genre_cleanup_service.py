"""Retire only proven plan-107 artist tags; preserve ambiguous/manual profiles."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from mtee.domain.genres import GenreError
from mtee.persistence.database import Database
from mtee.persistence.genre_repository import GenreRepository, encode
from mtee.services.genre_seed_service import digest, protect_destination, readonly


class ArtistGenreCleanupService:
    def __init__(self, path: Path):
        self.path = path.resolve()

    def preview(
        self, witness: Path | None = None, start: str = "", end: str = ""
    ) -> dict[str, Any]:
        baseline = {}
        if witness:
            with closing(readonly(witness)) as connection:
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise GenreError("The historical witness is not usable")
                baseline = {
                    r["artist_id"]: dict(r)
                    for r in connection.execute("SELECT * FROM artist_enrichment_reviews")
                }
        with closing(readonly(self.path)) as connection:
            current = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM artist_enrichment_reviews ORDER BY artist_id"
                )
            ]
        proposed = []
        ambiguous = []
        preserved_fields = [
            "decision",
            "roles_json",
            "bass_related",
            "spotify_url",
            "soundcloud_url",
            "notes",
            "identity_decision",
            "observation_json",
            "validated_at_utc",
        ]
        for row in current:
            try:
                record = json.loads(row["record_json"])
                tags = json.loads(row["tags_json"])
                added = record.get("genre_added")
                if not added:
                    continue
                original = baseline.get(row["artist_id"])
                saved = record.get("saved_at", "")
                evidence = bool(
                    original
                    and start
                    and end
                    and isinstance(added, list)
                    and isinstance(record.get("genre_sources"), dict)
                )
                added_keys = set()
                if evidence and original is not None:
                    evidence = (
                        datetime.fromisoformat(start)
                        <= datetime.fromisoformat(saved)
                        <= datetime.fromisoformat(end)
                        and record.get("tags") == tags
                        and all(row[field] == original[field] for field in preserved_fields)
                    )
                    old_tags = json.loads(original["tags_json"])
                    old_keys = {str(t).casefold() for t in old_tags}
                    added_keys = {str(t).casefold() for t in added}
                    evidence = (
                        evidence
                        and not (added_keys & old_keys)
                        and added_keys <= set(str(t).casefold() for t in tags)
                    )
                    evidence = evidence and added_keys <= set(
                        str(t).casefold() for t in record["genre_sources"]
                    )
                    evidence = (
                        evidence and set(str(t).casefold() for t in tags) == old_keys | added_keys
                    )
                if not evidence:
                    ambiguous.append(
                        {
                            "artist_id": row["artist_id"],
                            "added": added,
                            "reason": "The original import or a later manual edit "
                            "cannot be distinguished",
                        }
                    )
                    continue
                retained = [tag for tag in tags if str(tag).casefold() not in added_keys]
                next_record = dict(
                    record, tags=retained, genre_added=[], genre_sources={}, genre_retired_109=True
                )
                after = dict(row, tags_json=encode(retained), record_json=encode(next_record))
                proposed.append(
                    {"artist_id": row["artist_id"], "before": row, "after": after, "removed": added}
                )
            except (ValueError, TypeError, AttributeError):
                ambiguous.append(
                    {"artist_id": row["artist_id"], "reason": "Invalid or incomplete provenance"}
                )
        return {
            "version": 1,
            "database": str(self.path),
            "witness": str(witness.resolve()) if witness else "",
            "start": start,
            "end": end,
            "fingerprint": digest(current),
            "rows": proposed,
            "ambiguous": ambiguous,
            "summary": {
                "artists": len(proposed),
                "tags": sum(len(r["removed"]) for r in proposed),
                "ambiguous": len(ambiguous),
            },
        }

    def apply(self, plan: dict[str, Any]) -> dict[str, str]:
        witness = Path(plan["witness"]) if plan["witness"] else None
        if plan != self.preview(witness, plan["start"], plan["end"]):
            raise GenreError("Cleanup preview is stale or belongs to another database")
        if not plan["rows"]:
            return {"operation": "", "backup": ""}
        database = Database(self.path)
        operation = str(uuid4())
        try:
            roots = [
                str(r[0]) for r in database.connection().execute("SELECT path FROM library_roots")
            ]
            protect_destination(self.path, roots)
            backup = database.backup_path_for(database.schema_version())
            protect_destination(backup, roots)
            database.backup_to(backup)
            with database.transaction() as connection:
                current = [
                    dict(r)
                    for r in connection.execute(
                        "SELECT * FROM artist_enrichment_reviews ORDER BY artist_id"
                    )
                ]
                if digest(current) != plan["fingerprint"]:
                    raise GenreError("Cleanup preview is stale")
                before, after = {}, {}
                for item in plan["rows"]:
                    identity = item["artist_id"]
                    next_row = item["after"]
                    connection.execute(
                        "UPDATE artist_enrichment_reviews SET tags_json=?,record_json=? "
                        "WHERE artist_id=?",
                        (next_row["tags_json"], next_row["record_json"], identity),
                    )
                    before["artist:" + identity] = {"revision": 0, "row": item["before"]}
                    after["artist:" + identity] = {"revision": 1, "row": next_row}
                GenreRepository.record_operation(
                    connection, operation, "artist_cleanup", before, after
                )
            return {"operation": operation, "backup": str(backup)}
        finally:
            database.close()

    def undo(self, operation: str) -> str:
        database = Database(self.path)
        inverse = str(uuid4())
        try:
            roots = [
                str(r[0]) for r in database.connection().execute("SELECT path FROM library_roots")
            ]
            protect_destination(self.path, roots)
            with database.transaction() as connection:
                op = connection.execute(
                    "SELECT * FROM genre_operations WHERE operation_id=?", (operation,)
                ).fetchone()
                if not op or op["status"] != "committed" or op["kind"] != "artist_cleanup":
                    raise GenreError("Missing or already undone cleanup")
                before, after = {}, {}
                for item in connection.execute(
                    "SELECT * FROM genre_operation_items WHERE operation_id=?", (operation,)
                ).fetchall():
                    target = item["target_id"]
                    identity = target.split(":", 1)[1]
                    row = connection.execute(
                        "SELECT * FROM artist_enrichment_reviews WHERE artist_id=?", (identity,)
                    ).fetchone()
                    expected = json.loads(item["after_json"])
                    restore = json.loads(item["before_json"])
                    if not row or dict(row) != expected["row"]:
                        raise GenreError("Cleanup undo conflict: " + identity)
                    connection.execute(
                        "UPDATE artist_enrichment_reviews SET tags_json=?,record_json=? "
                        "WHERE artist_id=?",
                        (restore["row"]["tags_json"], restore["row"]["record_json"], identity),
                    )
                    before[target] = expected
                    after[target] = dict(restore, revision=2)
                GenreRepository.record_operation(
                    connection, inverse, "artist_cleanup_inverse", before, after
                )
                connection.execute(
                    "UPDATE genre_operations SET status='undone',inverse_operation_id=? "
                    "WHERE operation_id=?",
                    (inverse, operation),
                )
            return inverse
        finally:
            database.close()

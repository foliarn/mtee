"""Independent enrichment schema in the catalog DB; no core schema/version changes."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from artist_enrichment_pilot import now

MIGRATION = Path(__file__).parent / "artist-review-migrations/001_artist_enrichment.sql"


class ReviewDatabase:
    def __init__(self, path: Path):
        self.path = path.resolve()
        with closing(self.connect()) as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='artist_enrichment_schema'"
            ).fetchone()
            if exists:
                versions = connection.execute(
                    "SELECT version FROM artist_enrichment_schema ORDER BY version"
                ).fetchall()
                if versions != [(1,)]:
                    raise ValueError("Unsupported enrichment schema")
                return
            # Online SQLite backup includes committed WAL content.
            backup = self.path.with_name(
                self.path.name + ".before-enrichment-" + now().replace(":", "-") + ".bak"
            )
            with closing(sqlite3.connect(backup)) as target:
                connection.backup(target)
            try:
                connection.executescript(
                    "BEGIN IMMEDIATE;\n" + MIGRATION.read_text(encoding="utf8")
                )
                connection.execute("INSERT INTO artist_enrichment_schema VALUES (1, ?)", (now(),))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def connect(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def reviews(self) -> dict:
        with closing(self.connect()) as connection:
            return {
                aid: json.loads(record)
                for aid, record in connection.execute(
                    "SELECT artist_id,record_json FROM artist_enrichment_reviews"
                )
            }

    def save(self, records: dict, observations: dict) -> None:
        with closing(self.connect()) as connection, connection:
            for aid, r in records.items():
                connection.execute(
                    "INSERT INTO artist_enrichment_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(artist_id) DO UPDATE SET decision=excluded.decision, "
                    "roles_json=excluded.roles_json,bass_related=excluded.bass_related, "
                    "spotify_url=excluded.spotify_url,soundcloud_url=excluded.soundcloud_url, "
                    "tags_json=excluded.tags_json,notes=excluded.notes, "
                    "identity_decision=excluded.identity_decision, "
                    "validated_at_utc=excluded.validated_at_utc,record_json=excluded.record_json, "
                    "observation_json=excluded.observation_json",
                    (
                        aid,
                        r["decision"],
                        json.dumps(r["roles"]),
                        r["bass_related"],
                        r["spotify_url"],
                        r["soundcloud_url"],
                        json.dumps(r["tags"]),
                        r["notes"],
                        r["identity_decision"],
                        r["validated_at"],
                        json.dumps(r, ensure_ascii=False),
                        json.dumps(observations.get(aid, {}), ensure_ascii=False),
                    ),
                )

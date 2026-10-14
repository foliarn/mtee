"""Remove the artists that have no track at all from a MTEE database.

An artist is an orphan when no row of ``track_artist_credits`` names it: profiles left
behind by an analysis, or retired after a merge or a split. The default run only lists
them; ``--apply`` backs the database up first, then deletes the orphans with the rows
that hang on them (name observations, aliases, enrichment review). Credits, tracks,
files and the other artists are never touched. Close MTEE before applying.

    python scripts/archive/clean_orphan_artists.py --database mtee.sqlite3 --csv orphans.csv
    python scripts/archive/clean_orphan_artists.py --database mtee.sqlite3 --apply
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

_ORPHANS = (
    "SELECT a.artist_id, a.display_name, a.state, a.name_origin FROM artists a "
    "WHERE NOT EXISTS (SELECT 1 FROM track_artist_credits c WHERE c.artist_id=a.artist_id)"
)
_ATTACHED = {
    "observations": "SELECT COUNT(*) FROM artist_name_observations WHERE artist_id=?",
    "aliases": "SELECT COUNT(*) FROM artist_aliases WHERE artist_id=?",
    "reviews": "SELECT COUNT(*) FROM artist_enrichment_reviews WHERE artist_id=?",
}


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def find_orphans(connection: sqlite3.Connection) -> tuple[list[dict[str, object]], list[str]]:
    """Return ``(orphans to delete, names kept because another artist was merged into them)``."""
    tables = _tables(connection)
    orphans = [
        {"id": row[0], "name": row[1], "state": row[2], "origin": row[3]}
        for row in connection.execute(_ORPHANS + " ORDER BY a.state, a.display_name COLLATE NOCASE")
    ]
    ids = {str(item["id"]) for item in orphans}
    referenced = {
        str(row[0])
        for row in connection.execute(
            "SELECT merged_into FROM artists WHERE merged_into IS NOT NULL AND artist_id NOT IN "
            f"({_placeholders(len(ids))})",
            sorted(ids),
        )
    }
    kept = [str(item["name"]) for item in orphans if str(item["id"]) in referenced]
    result = [item for item in orphans if str(item["id"]) not in referenced]
    for item in result:
        for key, query in _ATTACHED.items():
            table = query.split("FROM ")[1].split(" ")[0]
            item[key] = (
                connection.execute(query, (item["id"],)).fetchone()[0] if table in tables else 0
            )
    return result, kept


def _placeholders(count: int) -> str:
    return ",".join("?" * count) if count else "''"


def delete_orphans(connection: sqlite3.Connection, ids: list[str]) -> dict[str, int]:
    """Delete ``ids`` and what hangs on them in one transaction; return the row counts."""
    tables = _tables(connection)
    counts = {"artists": 0, "observations": 0, "aliases": 0, "reviews": 0}
    connection.execute("BEGIN IMMEDIATE")
    try:
        before = set(connection.execute("PRAGMA foreign_key_check").fetchall())
        for artist_id in ids:
            if "artist_name_observations" in tables:
                counts["observations"] += connection.execute(
                    "DELETE FROM artist_name_observations WHERE artist_id=?", (artist_id,)
                ).rowcount
            if "artist_aliases" in tables:
                counts["aliases"] += connection.execute(
                    "DELETE FROM artist_aliases WHERE artist_id=?", (artist_id,)
                ).rowcount
            if "artist_enrichment_reviews" in tables:
                counts["reviews"] += connection.execute(
                    "DELETE FROM artist_enrichment_reviews WHERE artist_id=?", (artist_id,)
                ).rowcount
            connection.execute(
                "UPDATE artists SET merged_into=NULL WHERE artist_id=?", (artist_id,)
            )
            counts["artists"] += connection.execute(
                "DELETE FROM artists WHERE artist_id=?", (artist_id,)
            ).rowcount
        # Only the violations this cleanup would add count; older ones are not its business.
        violations = set(connection.execute("PRAGMA foreign_key_check").fetchall()) - before
        if violations:
            raise sqlite3.IntegrityError(f"{len(violations)} foreign key violations")
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    return counts


def backup(path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.before-orphan-cleanup-{stamp}.bak")
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="delete (a backup is made first)")
    parser.add_argument("--csv", type=Path, help="write the list of orphans to this file")
    args = parser.parse_args(argv)
    if not args.database.is_file():
        print(f"No database at {args.database}", file=sys.stderr)
        return 2

    with closing(sqlite3.connect(args.database, timeout=5)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        orphans, kept = find_orphans(connection)
        by_state: dict[str, int] = {}
        for item in orphans:
            by_state[str(item["state"])] = by_state.get(str(item["state"]), 0) + 1
        print(f"{len(orphans)} artists without any track: {by_state}")
        if kept:
            print(f"{len(kept)} kept, another artist was merged into them: {kept}")
        if args.csv:
            with args.csv.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(
                    handle,
                    ["id", "name", "state", "origin", "observations", "aliases", "reviews"],
                )
                writer.writeheader()
                writer.writerows(orphans)
            print(f"List written to {args.csv}")
        if not args.apply:
            print("Nothing deleted. Run again with --apply to delete them.")
            return 0
        if not orphans:
            return 0
        copy = backup(args.database)
        print(f"Backup: {copy}")
        counts = delete_orphans(connection, [str(item["id"]) for item in orphans])
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        print(f"Deleted {counts}; quick_check: {quick}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

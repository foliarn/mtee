"""The orphan-artist cleanup lists first, backs up, and deletes only artists without tracks."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "archive"))
from clean_orphan_artists import main

from mtee.persistence.database import Database
from mtee.plugins.artist_manager.repository import ArtistRepository


@pytest.fixture
def path(tmp_path: Path) -> Path:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    ArtistRepository(database)  # the artist tables belong to the artist manager plugin
    connection = database.connection()
    connection.execute("PRAGMA foreign_keys=ON")
    now = "2026-10-07T00:00:00+00:00"
    for artist_id, name, state, merged in (
        ("keep", "Hedex", "established", None),
        ("raw", "Hedex Bou", "provisional", None),
        ("gone", "Chase", "retired", None),
        ("target", "Nikita, the Wicked", "retired", None),
        ("old", "Nikita", "retired", "target"),
    ):
        connection.execute(
            "INSERT INTO artists VALUES(?,?,?, 'auto', ?, ?, ?, ?)",
            (artist_id, name, name.lower(), state, merged, now, now),
        )
    connection.execute("INSERT INTO artist_aliases VALUES('chase','gone','Chase')")
    connection.execute(
        "INSERT INTO artist_enrichment_reviews VALUES('gone','keep','[]',NULL,'','','[]','',"
        "'accepted','t','{}','{}')"
    )
    connection.commit()
    file = Path(database.path)
    database.close()
    return file


def _ids(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as connection:
        return [row[0] for row in connection.execute("SELECT artist_id FROM artists ORDER BY 1")]


def test_the_default_run_lists_and_changes_nothing(path: Path, capsys, tmp_path: Path) -> None:
    csv_path = tmp_path / "orphans.csv"
    assert main(["--database", str(path), "--csv", str(csv_path)]) == 0
    output = capsys.readouterr().out
    assert "Nothing deleted" in output
    assert csv_path.read_text("utf-8-sig").count("\n") >= 4
    assert len(_ids(path)) == 5
    assert not list(path.parent.glob("*.bak"))


def test_apply_backs_up_then_deletes_orphans_and_what_hangs_on_them(path: Path, capsys) -> None:
    with closing(sqlite3.connect(path)) as connection:
        # "keep" has a credit: it is not an orphan.
        connection.execute(
            "INSERT INTO track_artist_credits VALUES('missing-track','keep',0,'artist',1)"
        )
        connection.commit()
    assert main(["--database", str(path), "--apply"]) == 0
    assert "quick_check: ok" in capsys.readouterr().out
    # "old" was merged into "target": both have no track, so both go.
    assert _ids(path) == ["keep"]
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM artist_aliases").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM artist_enrichment_reviews").fetchone()[0] == 0
        )
    backups = list(path.parent.glob("*.before-orphan-cleanup-*.bak"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as connection:
        assert connection.execute("SELECT COUNT(*) FROM artists").fetchone()[0] == 5


def test_an_orphan_that_a_credited_artist_was_merged_into_is_kept(path: Path, capsys) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "INSERT INTO artists VALUES('heir','Heir','heir','auto','established','target','t','t')"
        )
        connection.execute("INSERT INTO track_artist_credits VALUES('x','heir',0,'artist',1)")
        connection.commit()
    assert main(["--database", str(path), "--apply"]) == 0
    assert "kept" in capsys.readouterr().out
    assert _ids(path) == ["heir", "target"]

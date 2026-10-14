import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "archive"))
from artist_enrichment_pilot import write_json
from artist_full_collection import import_validated_pilot, prepare_full
from artist_pilot_server import ReviewStore
from artist_review_database import ReviewDatabase


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(path) as c:
        c.executescript("""
            PRAGMA user_version=19;
            CREATE TABLE artists(artist_id TEXT PRIMARY KEY,display_name TEXT,state TEXT);
            CREATE TABLE track_artist_credits(track_id TEXT,artist_id TEXT,position INTEGER,
                                             role TEXT,confirmed INTEGER);
            CREATE TABLE track_artist_review(track_id TEXT,confirmed_title TEXT,review_state TEXT);
            CREATE TABLE track_locations(track_id TEXT,path TEXT,metadata_json TEXT);
            INSERT INTO track_locations VALUES('t','/fictional/a.mp3','{"genre":["Dance"]}');
            INSERT INTO track_locations VALUES('u','/fictional/b.mp3','{"title":["Unreviewed"]}');
            INSERT INTO track_artist_review VALUES('t','Confirmed song','confirmed');
            INSERT INTO track_artist_credits VALUES('t','0',0,'artist',1);
        """)
        c.executemany(
            "INSERT INTO artists VALUES(?,?,?)",
            [(str(i), f"Artist {i}", "established") for i in range(42)],
        )
    pilot = tmp_path / "pilot"
    pilot.mkdir()
    write_json(
        pilot / "artists.json",
        [{"artist_id": str(i), "display_name": f"Artist {i}"} for i in range(42)],
    )
    write_json(
        pilot / "observations.json",
        [{"artist_id": str(i), "roles": ["Producer"], "bass_related": True} for i in range(42)],
    )
    write_json(
        pilot / "review.json",
        {
            "0": {
                "decision": "exclude",
                "roles": ["MC"],
                "bass_related": False,
                "notes": "Personal choice",
                "saved_at": "earlier",
            }
        },
    )
    write_json(pilot / "musicbrainz.json", {"artists": {}})
    write_json(pilot / "sample.json", [])
    write_json(pilot / "summary.json", {})
    return path, pilot, tmp_path / "full"


def test_full_import_includes_unreviewed_tracks_and_uncredited_artists(catalog):
    path, pilot, output = catalog
    before = path.read_bytes()
    assert prepare_full(path, pilot, output) == {
        "tracks": 2,
        "artists": 42,
        "tracks_without_confirmed_credits": 1,
    }
    assert path.read_bytes() == before
    tracks = json.loads((output / "sample.json").read_text())
    assert next(t for t in tracks if t["track_id"] == "u")["credits"] == []
    assert (output / "review.json").read_bytes() == (pilot / "review.json").read_bytes()
    with pytest.raises(ValueError):
        prepare_full(path, pilot, output)


def test_42_pilot_choices_persist_once_and_survive_reopen(catalog):
    path, pilot, output = catalog
    prepare_full(path, pilot, output)
    store = ReviewStore(output, path)
    before = (output / "review.json").read_bytes()
    assert import_validated_pilot(path, pilot, output) == 42
    assert import_validated_pilot(path, pilot, output) == 0
    reopened = ReviewStore(output, path).effective_reviews()
    assert all(r["validated_at"] for r in reopened.values())
    assert reopened["0"]["roles"] == ["MC"]
    assert reopened["0"]["notes"] == "Personal choice"
    assert reopened["0"]["tags"] == ["idgaf"]
    store.save_page({"0": reopened["0"]})
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT count(*) FROM artist_enrichment_reviews").fetchone()[0] == 42
        assert c.execute("PRAGMA user_version").fetchone()[0] == 19
        assert c.execute("SELECT count(*) FROM artists").fetchone()[0] == 42
    assert (output / "review.json").read_bytes() == before
    backups = list(path.parent.glob("*.bak"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as c:
        assert not c.execute(
            "SELECT 1 FROM sqlite_master WHERE name='artist_enrichment_reviews'"
        ).fetchone()


def test_failed_database_batch_rolls_back_all_and_leaves_other_pages_pending(catalog):
    path, pilot, output = catalog
    prepare_full(path, pilot, output)
    store = ReviewStore(output, path)
    record = store.save_page({"0": store.effective_reviews()["0"]})["0"]
    invalid = {**record, "notes": "Changed", "validated_at": "now"}
    assert store.database is not None
    with pytest.raises(sqlite3.IntegrityError):
        store.database.save({"0": invalid, "missing": invalid}, {})
    records = ReviewDatabase(path).reviews()
    assert set(records) == {"0"}
    assert records["0"]["notes"] == "Personal choice"
    assert "validated_at" not in store.effective_reviews()["1"]

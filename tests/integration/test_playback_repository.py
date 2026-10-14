"""Playback schema and JSON session tests use only temporary SQLite files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mtee.domain.playback_queue import QueueEntry, QueueState
from mtee.persistence.database import MIGRATIONS_DIR, Database
from mtee.persistence.playback_repository import (
    PlaybackRepository,
    PlaybackSession,
    PlaybackSessionError,
)


def _session() -> PlaybackSession:
    first = QueueEntry.create("track-1", "context", snapshot={"title": "First"})
    duplicate_a = QueueEntry.create("track-9", "manual", snapshot={"title": "Nine"})
    duplicate_b = QueueEntry.create("track-9", "manual", snapshot={"title": "Nine"})
    queue = QueueState().start_context([first], 0).enqueue([duplicate_a, duplicate_b])
    return PlaybackSession(queue, position_us=2_345_678, write_sequence=1)


def test_repository_round_trip_rejects_stale_writer_and_invalid_json(tmp_path: Path) -> None:
    database = Database(tmp_path / "session.sqlite3")
    database.migrate()
    repository = PlaybackRepository(database)
    session = _session()
    assert repository.save(session)
    loaded = repository.load()
    assert loaded is not None
    assert loaded.position_us == 2_345_678
    assert loaded.queue.current is not None
    assert loaded.queue.current.entry_id == session.queue.current.entry_id
    assert [entry.track_id for entry in loaded.queue.upcoming] == ["track-9", "track-9"]
    assert len({entry.entry_id for entry in loaded.queue.upcoming}) == 2
    assert not repository.save(session)
    assert repository.load() == loaded

    malformed = {"version": 99, "write_sequence": 2}
    with database.transaction() as connection:
        connection.execute(
            "UPDATE playback_session SET value_json=? WHERE session_id='main'",
            (json.dumps(malformed),),
        )
    with pytest.raises(PlaybackSessionError, match="version"):
        repository.load()
    database.close()


def test_migration_from_17_keeps_data_and_creates_consistent_backup(tmp_path: Path) -> None:
    old_migrations = tmp_path / "old-migrations"
    old_migrations.mkdir()
    for source in MIGRATIONS_DIR.glob("*.sql"):
        if int(source.name[:3]) <= 17:
            shutil.copy2(source, old_migrations / source.name)
    path = tmp_path / "existing.sqlite3"
    old_database = Database(path, migrations_dir=old_migrations)
    old_database.migrate()
    with old_database.transaction() as connection:
        connection.execute(
            "INSERT INTO settings(key, value, updated_at_utc) VALUES (?, ?, ?)",
            ("queue-test-marker", '"preserved"', "2026-10-01T00:00:00Z"),
        )
    old_database.close()

    database = Database(path)
    applied = database.migrate()
    # Core migrations only: the artist and genre manager plugins ship their own (d32b64d).
    expected = sorted(
        int(source.name[:3]) for source in MIGRATIONS_DIR.glob("*.sql") if int(source.name[:3]) > 17
    )
    assert [migration.version for migration in applied] == expected
    assert database.schema_version() == expected[-1]
    assert (
        database.connection()
        .execute("SELECT value FROM settings WHERE key='queue-test-marker'")
        .fetchone()[0]
        == '"preserved"'
    )
    backups = list(tmp_path.glob("existing.sqlite3.v17.*.backup"))
    assert len(backups) == 1
    backup = Database(backups[0], migrations_dir=old_migrations)
    assert backup.schema_version() == 17
    assert (
        backup.connection()
        .execute("SELECT value FROM settings WHERE key='queue-test-marker'")
        .fetchone()[0]
        == '"preserved"'
    )
    backup.close()
    assert database.migrate() == []
    database.close()


def test_session_v2_round_trips_the_history_and_v1_loads_without_one(tmp_path: Path) -> None:
    from mtee.domain.playback_history import HistoryEntry

    database = Database(tmp_path / "history.sqlite3")
    database.migrate()
    repository = PlaybackRepository(database)
    history = (
        HistoryEntry(
            "7f6c0d3e-1f7b-4d2a-9d56-0a1d3f8e1b11",
            "track-3",
            {"title": "Three", "path": "C:/never/stored.wav"},
            "playlist:night",
            "Night drive",
            "2026-10-01T12:00:00+00:00",
        ),
    )
    base = _session()
    assert repository.save(PlaybackSession(base.queue, 1, 5, history))

    loaded = repository.load()

    assert loaded is not None
    assert loaded.history[0].track_id == "track-3"
    assert loaded.history[0].source_title == "Night drive"
    assert dict(loaded.history[0].snapshot) == {"title": "Three"}

    with database.transaction() as connection:
        stored = json.loads(
            connection.execute("SELECT value_json FROM playback_session").fetchone()[0]
        )
        stored["version"] = 1
        del stored["history"]
        connection.execute("UPDATE playback_session SET value_json=?", (json.dumps(stored),))
    old = repository.load()
    assert old is not None and old.history == ()

    stored["version"] = 2
    stored["history"] = [{"history_id": "not-a-uuid"}]
    with database.transaction() as connection:
        connection.execute("UPDATE playback_session SET value_json=?", (json.dumps(stored),))
    with pytest.raises(PlaybackSessionError):
        repository.load()
    database.close()

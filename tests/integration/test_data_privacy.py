"""Backup, scheduled restore and statistics reset on temporary SQLite files."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import (
    DEVICE_ID_KEY,
    PlayLogRepository,
    load_or_create_device_id,
)
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.data_privacy import (
    BackupValidationError,
    RestoreLayout,
    apply_pending_restore,
    back_up_database,
    cancel_pending_restore,
    default_backup_name,
    prune_safety_copies,
    read_pending_restore,
    reset_statistics,
    stage_restore,
    validate_backup,
)

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "data"
    directory.mkdir()
    return directory


@pytest.fixture
def live(data_dir: Path) -> Iterator[Database]:
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    SettingsRepository(database).set("probe", "current")
    yield database
    database.close()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe(path: Path) -> str | None:
    """Read the probe setting straight from a database file, without the application."""
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("SELECT value FROM settings WHERE key = 'probe'").fetchone()
        return str(row[0]) if row else None
    finally:
        connection.close()


def _layout(data_dir: Path) -> RestoreLayout:
    return RestoreLayout(data_dir)


def _event(track: str, heard_ms: int, counted: bool) -> PlayEvent:
    started = NOW - timedelta(hours=1)
    return PlayEvent(
        event_id=str(uuid4()),
        track=PlayedTrack(track_id=track, path=f"{track}.mp3", artist="A", title="T", album="B"),
        started_at=started,
        ended_at=started + timedelta(milliseconds=heard_ms),
        heard_ms=heard_ms,
        counted=counted,
    )


def test_backup_is_consistent_verified_and_never_overwritten(
    live: Database, data_dir: Path
) -> None:
    backup = back_up_database(live, data_dir / "backups" / "copy.sqlite3")
    info = validate_backup(
        backup, supported_version=live.supported_version, migrations=live.migrations
    )
    assert info.schema_version == live.supported_version
    assert info.track_count == 0
    assert _probe(backup) == "current"
    # A backup is one file: it must not keep the write-ahead log mode of the source.
    connection = sqlite3.connect(backup)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    finally:
        connection.close()
    assert not Path(f"{backup}-wal").exists()
    with pytest.raises(FileExistsError):
        back_up_database(live, backup)


def test_default_backup_name_carries_the_utc_time() -> None:
    assert default_backup_name(NOW) == "mtee-backup-20261014-120000.sqlite3"


def test_staging_schedules_a_copy_and_leaves_the_live_database_alone(
    live: Database, data_dir: Path
) -> None:
    backup = back_up_database(live, data_dir / "copy.sqlite3")
    SettingsRepository(live).set("probe", "changed-after-backup")
    live.close()
    database_path = data_dir / "mtee.sqlite3"
    before = _digest(database_path)
    layout = _layout(data_dir)

    pending = stage_restore(
        backup,
        layout,
        database_path=database_path,
        supported_version=Database(database_path).supported_version,
        migrations=Database(database_path).migrations,
        now=NOW,
    )

    assert pending.source_name == "copy.sqlite3"
    assert read_pending_restore(layout) is not None
    assert _digest(layout.pending_file) == _digest(backup)
    assert _digest(database_path) == before


def test_invalid_files_are_refused_and_nothing_is_scheduled(live: Database, data_dir: Path) -> None:
    text = data_dir / "notes.sqlite3"
    text.write_text("this is a plain text file, not a database", encoding="utf-8")
    layout = _layout(data_dir)
    with pytest.raises(BackupValidationError, match="SQLite"):
        stage_restore(
            text,
            layout,
            database_path=live.path,
            supported_version=live.supported_version,
            migrations=live.migrations,
            now=NOW,
        )
    assert read_pending_restore(layout) is None
    assert not layout.pending_file.exists()
    with pytest.raises(BackupValidationError, match="currently in use"):
        validate_backup(
            live.path,
            supported_version=live.supported_version,
            migrations=live.migrations,
            database_path=live.path,
        )


def test_a_backup_from_a_newer_build_is_refused(live: Database, data_dir: Path) -> None:
    newer = back_up_database(live, data_dir / "newer.sqlite3")
    connection = sqlite3.connect(newer)
    connection.execute(f"PRAGMA user_version = {live.supported_version + 1}")
    connection.close()
    with pytest.raises(BackupValidationError, match="Update MTEE"):
        validate_backup(newer, supported_version=live.supported_version, migrations=live.migrations)


def test_a_backup_with_an_altered_migration_history_is_refused(
    live: Database, data_dir: Path
) -> None:
    altered = back_up_database(live, data_dir / "altered.sqlite3")
    connection = sqlite3.connect(altered)
    connection.execute("UPDATE schema_migrations SET name = 'tampered' WHERE version = 2")
    connection.commit()
    connection.close()
    with pytest.raises(BackupValidationError, match="does not match"):
        validate_backup(
            altered, supported_version=live.supported_version, migrations=live.migrations
        )


def test_apply_at_start_replaces_the_database_and_keeps_a_safety_copy(
    live: Database, data_dir: Path
) -> None:
    SettingsRepository(live).set("probe", "backup-state")
    backup = back_up_database(live, data_dir / "good.sqlite3")
    SettingsRepository(live).set("probe", "current-state")
    live.close()
    database_path = data_dir / "mtee.sqlite3"
    layout = _layout(data_dir)
    stage_restore(
        backup,
        layout,
        database_path=database_path,
        supported_version=Database(database_path).supported_version,
        migrations=Database(database_path).migrations,
        now=NOW,
    )
    # A leftover write-ahead log belongs to the old file and must not survive the swap.
    Path(f"{database_path}-wal").write_bytes(b"old wal")

    outcome = apply_pending_restore(
        layout,
        database_path=database_path,
        supported_version=Database(database_path).supported_version,
        migrations=Database(database_path).migrations,
        now=NOW,
    )

    assert outcome is not None and outcome.applied
    assert outcome.safety_backup is not None
    assert _probe(outcome.safety_backup) == "current-state"
    assert _probe(database_path) == "backup-state"
    assert not Path(f"{database_path}-wal").exists()
    assert read_pending_restore(layout) is None
    assert not layout.pending_file.exists()
    assert "Restored the database" in layout.result_file.read_text(encoding="utf-8")
    reopened = Database(database_path)
    reopened.migrate()
    assert SettingsRepository(reopened).get("probe") == "backup-state"
    reopened.close()


def test_apply_without_a_schedule_does_nothing(data_dir: Path, live: Database) -> None:
    live.close()
    layout = _layout(data_dir)
    assert (
        apply_pending_restore(
            layout,
            database_path=data_dir / "mtee.sqlite3",
            supported_version=Database(data_dir / "mtee.sqlite3").supported_version,
            migrations=Database(data_dir / "mtee.sqlite3").migrations,
            now=NOW,
        )
        is None
    )
    # A copy without its marker is an interrupted staging: it is removed, never applied.
    layout.directory.mkdir(parents=True, exist_ok=True)
    layout.pending_file.write_bytes(b"partial")
    apply_pending_restore(
        layout,
        database_path=data_dir / "mtee.sqlite3",
        supported_version=live.supported_version,
        migrations=live.migrations,
        now=NOW,
    )
    assert not layout.pending_file.exists()
    assert _probe(data_dir / "mtee.sqlite3") == "current"


def test_a_damaged_copy_cancels_the_restore_and_keeps_the_live_database(
    live: Database, data_dir: Path
) -> None:
    backup = back_up_database(live, data_dir / "good.sqlite3")
    live.close()
    database_path = data_dir / "mtee.sqlite3"
    layout = _layout(data_dir)
    stage_restore(
        backup,
        layout,
        database_path=database_path,
        supported_version=Database(database_path).supported_version,
        migrations=Database(database_path).migrations,
        now=NOW,
    )
    layout.pending_file.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    before = _digest(database_path)

    outcome = apply_pending_restore(
        layout,
        database_path=database_path,
        supported_version=Database(database_path).supported_version,
        migrations=Database(database_path).migrations,
        now=NOW,
    )

    assert outcome is not None and not outcome.applied
    assert "cancelled" in outcome.message
    assert _digest(database_path) == before
    assert read_pending_restore(layout) is None
    assert not layout.pending_file.exists()


def test_an_unreadable_schedule_is_cancelled_with_a_message(live: Database, data_dir: Path) -> None:
    live.close()
    layout = _layout(data_dir)
    layout.directory.mkdir(parents=True, exist_ok=True)
    layout.pending_file.write_bytes(b"anything")
    layout.marker_file.write_text("{not json", encoding="utf-8")
    outcome = apply_pending_restore(
        layout,
        database_path=data_dir / "mtee.sqlite3",
        supported_version=live.supported_version,
        migrations=live.migrations,
        now=NOW,
    )
    assert outcome is not None and not outcome.applied
    assert not layout.marker_file.exists()
    assert not layout.pending_file.exists()


def test_cancelling_a_schedule_removes_both_files(live: Database, data_dir: Path) -> None:
    backup = back_up_database(live, data_dir / "good.sqlite3")
    layout = _layout(data_dir)
    stage_restore(
        backup,
        layout,
        database_path=live.path,
        supported_version=live.supported_version,
        migrations=live.migrations,
        now=NOW,
    )
    cancel_pending_restore(layout)
    assert read_pending_restore(layout) is None
    assert not layout.pending_file.exists()
    assert not layout.marker_file.exists()


def test_reset_statistics_removes_the_events_and_keeps_the_installation_id(
    live: Database,
) -> None:
    settings = SettingsRepository(live)
    device = load_or_create_device_id(settings)
    repository = PlayLogRepository(live)
    repository.insert_events([_event("a", 35_000, True), _event("b", 2_000, False)], device)
    assert repository.totals().sessions == 2

    removed = reset_statistics(repository)

    assert removed == 2
    assert repository.totals().sessions == 0
    assert settings.get(DEVICE_ID_KEY) == device


def _old_safety_copy(layout: RestoreLayout, stamp: str) -> Path:
    layout.directory.mkdir(parents=True, exist_ok=True)
    path = layout.directory / f"before-restore-{stamp}.sqlite3"
    path.write_bytes(b"older safety copy")
    return path


def test_a_successful_restore_keeps_only_the_three_newest_safety_copies(
    live: Database, data_dir: Path
) -> None:
    SettingsRepository(live).set("probe", "backup-state")
    backup = back_up_database(live, data_dir / "good.sqlite3")
    live.close()
    database_path = data_dir / "mtee.sqlite3"
    layout = _layout(data_dir)
    older = [_old_safety_copy(layout, f"2026010{day}T000000000000Z") for day in range(1, 6)]
    stage_restore(
        backup,
        layout,
        database_path=database_path,
        supported_version=Database(database_path).supported_version,
        migrations=Database(database_path).migrations,
        now=NOW,
    )

    outcome = apply_pending_restore(
        layout,
        database_path=database_path,
        supported_version=Database(database_path).supported_version,
        migrations=Database(database_path).migrations,
        now=NOW,
    )

    assert outcome is not None and outcome.applied and outcome.safety_backup is not None
    kept = sorted(layout.directory.glob("before-restore-*.sqlite3"))
    # The two oldest copies are removed; the three newest, the one just made included, stay.
    assert [path.name for path in kept] == [
        older[3].name,
        older[4].name,
        outcome.safety_backup.name,
    ]


def test_pruning_only_touches_safety_copies(data_dir: Path) -> None:
    layout = _layout(data_dir)
    layout.directory.mkdir(parents=True, exist_ok=True)
    copies = [_old_safety_copy(layout, f"2026010{day}T000000000000Z") for day in range(1, 4)]
    unrelated = layout.directory / "notes.sqlite3"
    unrelated.write_bytes(b"not a safety copy")
    renamed = layout.directory / "before-restore-keep.txt"
    renamed.write_text("not a copy", encoding="utf-8")

    removed = prune_safety_copies(layout, keep=1)

    assert [path.name for path in removed] == [copies[0].name, copies[1].name]
    assert copies[2].exists()
    assert unrelated.exists() and renamed.exists()


def test_pruning_needs_at_least_one_kept_copy(data_dir: Path) -> None:
    with pytest.raises(ValueError):
        prune_safety_copies(_layout(data_dir), keep=0)

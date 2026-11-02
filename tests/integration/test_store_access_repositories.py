"""Repositories behind the store access for sync (plan 125.6), on temporary databases.

The playlist revision and its migration 029, the play log cursor and the idempotent append of
events from other devices, the analysis import that keeps layers apart, and the settings
listeners. Only copies and temporary files are used.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.musical_key import MusicalKey
from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.domain.tracks import SourceRevision
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import MIGRATIONS_DIR, Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.play_log_repository import PlayLogEvent, PlayLogRepository
from mtee.persistence.playlists_repository import PlaylistsRepository, StaleRevisionError
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.playlist_service import PlaylistService

DEVICE = str(uuid4())
OTHER_DEVICE = str(uuid4())
START = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(tmp_path / "mtee.sqlite3")
    db.migrate()
    yield db
    db.close()


@pytest.fixture
def collection(tmp_path: Path, database: Database):
    library = LibraryRepository(database)
    root = library.add_root(tmp_path / "audio")
    generation = library.begin_scan(root["id"])
    ids = []
    for index, (title, artist) in enumerate([("One", "Ann"), ("Two", "Bob"), ("Three", "Cy")]):
        path = tmp_path / "audio" / f"{index}.wav"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"audio" + bytes([index]))
        ids.append(
            library.upsert_location(
                root["id"],
                path.name,
                path,
                SourceRevision.observe(path),
                MetadataSnapshot(
                    title=(title,), artist=(artist,), technical=TechnicalInfo(duration_us=4_000_000)
                ),
                generation,
            )
        )
    library.finish_scan(root["id"], generation, complete=True)
    repository = PlaylistsRepository(database)
    return library, repository, PlaylistService(repository, library), ids


# ------------------------------------------------------------------ migration 029


def _database_before_029(tmp_path: Path, name: str = "before") -> Database:
    """A database at schema 28, built from copies of the shipped scripts."""
    scripts = tmp_path / f"{name}-scripts"
    scripts.mkdir()
    for path in MIGRATIONS_DIR.glob("*.sql"):
        if path.name < "029_":
            shutil.copy(path, scripts / path.name)
    database = Database(tmp_path / f"{name}.sqlite3", migrations_dir=scripts)
    database.migrate()
    assert database.schema_version() == 28
    return database


def _revision_column(path: Path) -> bool:
    with sqlite3.connect(path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(playlists)")]
    return "revision" in columns


def test_migration_029_on_an_empty_database_gives_new_playlists_revision_one(
    database: Database,
) -> None:
    assert database.schema_version() == 30
    repository = PlaylistsRepository(database)
    identity = repository.create("Fresh")
    assert repository.playlist(identity)["revision"] == 1


def test_migration_029_on_a_populated_copy_starts_every_playlist_at_revision_one(
    tmp_path: Path,
) -> None:
    old = _database_before_029(tmp_path)
    connection = old.connection()
    connection.execute("INSERT INTO tracks(track_id) VALUES('t1')")
    for number in (1, 2):
        connection.execute(
            "INSERT INTO playlists(playlist_id, name, ordinal, version, updated_at_utc) "
            "VALUES(?, ?, ?, ?, '2026-10-01T00:00:00')",
            (f"p{number}", f"Playlist {number}", number, number * 3),
        )
    connection.execute(
        "INSERT INTO playlist_entries VALUES('e1', 'p1', 't1', 0, '{\"title\": \"One\"}')"
    )
    old.close()
    assert not _revision_column(tmp_path / "before.sqlite3")

    upgraded = Database(tmp_path / "before.sqlite3")
    try:
        assert [migration.version for migration in upgraded.migrate()] == [29, 30]
        assert upgraded.schema_version() == 30
        rows = upgraded.connection().execute(
            "SELECT playlist_id, version, revision FROM playlists ORDER BY playlist_id"
        )
        assert [tuple(row) for row in rows] == [("p1", 3, 1), ("p2", 6, 1)]  # version untouched
        entries = PlaylistsRepository(upgraded).entries("p1")
        assert [(entry["entry_id"], entry["track_id"]) for entry in entries] == [("e1", "t1")]
        assert upgraded.migrate() == []
    finally:
        upgraded.close()


def test_the_migration_is_preceded_by_a_backup_that_has_no_revision_column(
    tmp_path: Path,
) -> None:
    old = _database_before_029(tmp_path)
    old.connection().execute(
        "INSERT INTO playlists(playlist_id, name, ordinal, updated_at_utc) "
        "VALUES('p1', 'Kept', 1, '2026-10-01T00:00:00')"
    )
    old.close()

    upgraded = Database(tmp_path / "before.sqlite3")
    try:
        upgraded.migrate()
    finally:
        upgraded.close()

    backups = list(tmp_path.glob("before.sqlite3.v28.*.backup"))
    assert len(backups) == 1
    assert not _revision_column(backups[0])
    with sqlite3.connect(backups[0]) as saved:
        assert saved.execute("SELECT name FROM playlists").fetchall() == [("Kept",)]
    assert _revision_column(tmp_path / "before.sqlite3")


# ------------------------------------------------------------------ playlist revision


def test_every_change_of_a_playlist_raises_its_revision(collection) -> None:
    library, repository, service, ids = collection
    identity = repository.create("Road", entries=[])
    seen = [repository.playlist(identity)["revision"]]

    def changed(action) -> None:
        action()
        seen.append(repository.playlist(identity)["revision"])

    version = lambda: repository.playlist(identity)["version"]  # noqa: E731
    changed(lambda: service.add(identity, [ids[0], ids[1]]))
    entries = [entry["entry_id"] for entry in repository.entries(identity)]
    changed(lambda: repository.reorder(identity, entries[::-1], version()))
    changed(lambda: repository.remove(identity, entries[:1]))
    changed(lambda: repository.pin(identity, True))
    changed(
        lambda: repository.update(
            identity, name="Road 2", description="d", cover="", version=version()
        )
    )
    changed(lambda: service.replace_entries(identity, [ids[2]]))
    changed(lambda: repository.replace_entries_at_revision(identity, [], seen[-1]))
    folder = repository.create_folder("Sets")
    changed(lambda: repository.move(identity, folder))
    repository.add_entries(
        identity, [{"track_id": None, "snapshot": {"title": "Missing"}}], version()
    )
    seen.append(repository.playlist(identity)["revision"])
    entry = repository.entries(identity)[0]["entry_id"]
    changed(lambda: service.resolve(identity, entry, ids[1]))

    assert seen == list(range(1, len(seen) + 1))  # strictly +1 for each of the changes
    assert library.track(ids[0])  # nothing here touched the library


def test_a_folder_move_does_not_need_a_folder_revision(collection) -> None:
    _library, repository, _service, _ids = collection
    parent = repository.create_folder("Parent")
    child = repository.create_folder("Child")

    repository.move(child, parent, is_folder=True)

    assert [row["parent_id"] for row in repository.folders() if row["folder_id"] == child] == [
        parent
    ]


def test_the_library_removing_a_track_is_a_change_of_the_playlist(
    collection, database: Database
) -> None:
    _library, repository, service, ids = collection
    identity = repository.create("Gone")
    service.add(identity, [ids[0], ids[1]])
    before = repository.playlist(identity)["revision"]

    database.connection().execute("DELETE FROM tracks WHERE track_id = ?", (ids[0],))

    assert repository.playlist(identity)["revision"] == before + 1
    assert repository.entries(identity)[0]["track_id"] is None


def test_a_checked_replace_writes_and_returns_the_next_revision(collection) -> None:
    _library, repository, service, ids = collection
    identity = repository.create("Sync")
    start = repository.playlist(identity)["revision"]

    new_revision = service.replace_entries(identity, [ids[1], ids[0]], expected_revision=start)

    assert new_revision == start + 1 == service.revision(identity)
    assert [entry["track_id"] for entry in repository.entries(identity)] == [ids[1], ids[0]]
    # Unconditional replacement still works and also reports the revision it produced.
    assert service.replace_entries(identity, [ids[2]]) == start + 2


def test_a_stale_revision_is_refused_and_nothing_is_written(collection) -> None:
    _library, repository, service, ids = collection
    identity = repository.create("Sync")
    service.add(identity, [ids[0]])
    stale = repository.playlist(identity)["revision"]
    service.add(identity, [ids[1]])  # a change from the interface path
    entries_before = repository.entries(identity)

    with pytest.raises(StaleRevisionError) as refused:
        service.replace_entries(identity, [ids[2]], expected_revision=stale)

    assert refused.value.expected == stale
    assert refused.value.actual == stale + 1
    assert refused.value.readable
    assert repository.entries(identity) == entries_before
    assert service.revision(identity) == stale + 1
    with pytest.raises(LookupError):
        service.replace_entries("missing", [], expected_revision=1)
    assert service.revision("missing") is None


# ------------------------------------------------------------------ play log


def _local_event(track_id: str, minutes: int) -> PlayEvent:
    started = START + timedelta(minutes=minutes)
    return PlayEvent(
        event_id=str(uuid4()),
        track=PlayedTrack(track_id, f"C:/music/{track_id}.flac", "Ann", f"Title {track_id}", "LP"),
        started_at=started,
        ended_at=started + timedelta(seconds=200),
        heard_ms=200_000,
        counted=True,
    )


def _remote(event_id: str, minutes: int, device: str = OTHER_DEVICE) -> PlayLogEvent:
    started = START + timedelta(minutes=minutes)
    return PlayLogEvent(
        event_id=event_id,
        device_id=device,
        track_id="remote-track",
        started_at=started,
        ended_at=started + timedelta(seconds=90),
        heard_ms=90_000,
        counted=True,
        artist="Dee",
        title="Far away",
        album="Elsewhere",
        duration_us=180_000_000,
    )


def test_events_are_read_in_insertion_order_by_cursor(database: Database) -> None:
    log = PlayLogRepository(database)
    log.insert_events([_local_event("a", 30), _local_event("b", 20)], DEVICE)  # b starts first
    log.insert_remote_events([_remote("r1", 10)])  # the oldest start, stored last

    first, cursor = log.events_since(None, 2)
    second, last = log.events_since(cursor, 2)
    nothing, same = log.events_since(last, 2)

    assert [event.track_id for event in first] == ["a", "b"]  # stored order, not start time
    assert [event.event_id for event in second] == ["r1"]
    assert second[0].device_id == OTHER_DEVICE and first[0].device_id == DEVICE
    assert nothing == [] and same == last
    assert log.events_since(None, 10)[0] == first + second


def test_an_empty_log_keeps_the_cursor_and_a_bad_cursor_is_refused(database: Database) -> None:
    log = PlayLogRepository(database)

    assert log.events_since(None, 5) == ([], None)
    assert log.events_since("0", 5) == ([], "0")
    for bad in ("abc", "-1", "1.5", ""):
        with pytest.raises(ValueError):
            log.events_since(bad, 5)
    with pytest.raises(ValueError):
        log.events_since(None, 0)


def test_events_carry_no_path_and_keep_their_fields(database: Database) -> None:
    log = PlayLogRepository(database)
    local = _local_event("a", 0)
    log.insert_events([local], DEVICE)

    (event,), _ = log.events_since(None, 5)

    assert event == PlayLogEvent(
        event_id=local.event_id,
        device_id=DEVICE,
        track_id="a",
        started_at=local.started_at,
        ended_at=local.ended_at,
        heard_ms=200_000,
        counted=True,
        artist="Ann",
        title="Title a",
        album="LP",
        duration_us=0,
    )
    assert not hasattr(event, "path")


def test_remote_events_are_appended_once_and_keep_their_device(database: Database) -> None:
    log = PlayLogRepository(database)
    batch = [_remote("r1", 1), _remote("r2", 2, device=str(uuid4())), _remote("r3", 3)]

    assert log.insert_remote_events(batch) == 3
    assert log.insert_remote_events(batch) == 0  # the same batch twice: stored once
    overlapping = [_remote("r3", 3), _remote("r4", 4)]
    assert log.insert_remote_events(overlapping) == 1  # a seen id is skipped, not an error

    stored, _ = log.events_since(None, 10)
    assert [event.event_id for event in stored] == ["r1", "r2", "r3", "r4"]
    assert {event.device_id for event in stored} == {OTHER_DEVICE, batch[1].device_id}
    assert log.totals().sessions == 4
    row = database.connection().execute("SELECT path_at_play FROM play_events").fetchone()
    assert row[0] == ""


def test_an_invalid_remote_event_refuses_the_whole_batch(database: Database) -> None:
    log = PlayLogRepository(database)
    good = _remote("r1", 1)
    naive = PlayLogEvent(
        "r2", OTHER_DEVICE, "t", datetime(2026, 10, 1), datetime(2026, 10, 1), 1, True
    )

    with pytest.raises(ValueError):
        log.insert_remote_events([good, naive])
    with pytest.raises(ValueError):
        log.insert_remote_events([good, _remote("", 2)])
    with pytest.raises(ValueError):
        log.insert_remote_events([good, PlayLogEvent("r3", OTHER_DEVICE, "t", START, START, -1, 1)])  # type: ignore[arg-type]

    assert log.events_since(None, 10) == ([], None)
    assert log.insert_remote_events([]) == 0


def test_the_append_only_trigger_stays_after_remote_appends(database: Database) -> None:
    log = PlayLogRepository(database)
    log.insert_remote_events([_remote("r1", 1)])

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        database.connection().execute("UPDATE play_events SET heard_ms = 1")


# ------------------------------------------------------------------ analysis layers


def _add_track(database: Database, track_id: str) -> None:
    database.connection().execute("INSERT INTO tracks(track_id) VALUES(?)", (track_id,))


def test_an_imported_analysis_keeps_its_version_and_leaves_the_loudness_alone(
    database: Database,
) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.import_loudness(
        "t1",
        integrated_lufs=-9.5,
        sample_peak_dbfs=-0.4,
        loudness_version=1,
        source_duration_us=5_000_000,
    )

    repository.import_analysis(
        "t1",
        bpm=128.0,
        key=MusicalKey(7, True),
        bpm_user_edited=False,
        key_user_edited=True,
        source_duration_us=5_000_000,
        algorithm_version=1,
        analyzed_at_utc="2026-09-01T10:00:00+00:00",
    )

    stored = repository.get("t1")
    assert stored is not None
    assert (stored.bpm, stored.key, stored.key_user_edited) == (128.0, MusicalKey(7, True), True)
    assert (stored.algorithm_version, stored.analyzed_at_utc) == (
        1,
        "2026-09-01T10:00:00+00:00",
    )
    assert (stored.integrated_lufs, stored.sample_peak_dbfs, stored.loudness_version) == (
        -9.5,
        -0.4,
        1,
    )
    assert repository.is_current(stored, 5_000_000) is False  # an older algorithm: re-analyze


def test_a_local_edit_wins_over_an_imported_analysis(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.save_result("t1", bpm=120.0, key=MusicalKey(0, False), source_duration_us=1)
    repository.mark_user_edited(["t1"], "bpm")

    repository.import_analysis(
        "t1",
        bpm=170.0,
        key=MusicalKey(5, True),
        bpm_user_edited=False,
        key_user_edited=False,
        source_duration_us=1,
        algorithm_version=2,
        analyzed_at_utc="2026-10-01T00:00:00+00:00",
    )

    stored = repository.get("t1")
    assert stored is not None
    assert stored.bpm == 120.0 and stored.bpm_user_edited  # the edit here stays
    assert stored.key == MusicalKey(5, True) and not stored.key_user_edited


# ------------------------------------------------------------------ settings listeners


def test_listeners_hear_set_set_many_and_delete_once_committed(database: Database) -> None:
    settings = SettingsRepository(database)
    heard: list[tuple[str, str | None]] = []
    remove = settings.add_listener(lambda key: heard.append((key, settings.get(key))))

    settings.set("a", "1")
    settings.set_many({"b": "2", "c": "3"})
    settings.delete("a")
    remove()
    settings.set("d", "4")

    assert heard == [("a", "1"), ("b", "2"), ("c", "3"), ("a", None)]


def test_a_failing_listener_does_not_stop_the_others_or_the_write(
    database: Database, caplog: pytest.LogCaptureFixture
) -> None:
    settings = SettingsRepository(database)
    heard: list[str] = []

    def explodes(_key: str) -> None:
        raise RuntimeError("listener bug")

    settings.add_listener(explodes)
    settings.add_listener(heard.append)

    settings.set("a", "1")

    assert settings.get("a") == "1" and heard == ["a"]
    assert "listener bug" in caplog.text
    with pytest.raises(ValueError):
        settings.set_many({"": "x"})

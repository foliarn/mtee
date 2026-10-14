"""Permanent listening log: schema, append-only rows and statistics on temporary SQLite files."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from mtee.domain.play_log import ListeningPeriod, PlayedTrack, PlayEvent
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import (
    ALL_TIME,
    DEVICE_ID_KEY,
    DailyListening,
    PlayLogRepository,
    load_or_create_device_id,
)
from mtee.persistence.settings_repository import SettingsRepository

DEVICE = str(uuid4())
PARIS = timezone(timedelta(hours=2))


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(tmp_path / "mtee.sqlite3")
    db.migrate()
    yield db
    db.close()


def _event(
    track_id: str,
    started: datetime,
    *,
    heard_ms: int,
    counted: bool,
    album: str = "Album",
    title: str | None = None,
    duration_us: int = 200_000_000,
) -> PlayEvent:
    return PlayEvent(
        event_id=str(uuid4()),
        track=PlayedTrack(
            track_id=track_id,
            path=f"C:/music/{track_id}.flac",
            artist="Artist",
            title=title or f"Title {track_id}",
            album=album,
            duration_us=duration_us,
        ),
        started_at=started,
        ended_at=started + timedelta(milliseconds=heard_ms),
        heard_ms=heard_ms,
        counted=counted,
    )


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_migration_creates_the_append_only_table(database: Database) -> None:
    assert database.schema_version() == 24
    connection = database.connection()
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(play_events)")}
    assert {
        "event_id",
        "track_id",
        "path_at_play",
        "artist",
        "title",
        "album",
        "duration_us",
        "started_at_utc",
        "ended_at_utc",
        "heard_ms",
        "counted",
        "device_id",
    } <= columns
    indexes = {row["name"] for row in connection.execute("PRAGMA index_list(play_events)")}
    assert {"play_events_started", "play_events_track_started", "play_events_album_started"} <= (
        indexes
    )
    repository = PlayLogRepository(database)
    repository.insert_events(
        [_event("t1", _utc(2026, 10, 1, 9), heard_ms=1000, counted=False)], DEVICE
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("UPDATE play_events SET heard_ms = 0")


def test_insert_and_totals_include_partial_listening(database: Database) -> None:
    repository = PlayLogRepository(database)
    assert repository.totals().sessions == 0
    written = repository.insert_events(
        [
            _event("t1", _utc(2026, 10, 1, 9), heard_ms=200_000, counted=True),
            _event("t2", _utc(2026, 10, 1, 10), heard_ms=5_000, counted=False),
            _event("t1", _utc(2026, 10, 2, 10), heard_ms=31_000, counted=True),
        ],
        DEVICE,
    )
    assert written == 3
    totals = repository.totals()
    assert totals.listening_ms == 236_000
    assert totals.counted_plays == 2
    assert totals.sessions == 3
    assert repository.insert_events([], DEVICE) == 0
    with pytest.raises(ValueError):
        repository.insert_events([], "not-a-uuid")


def test_period_is_half_open_and_utc(database: Database) -> None:
    repository = PlayLogRepository(database)
    repository.insert_events(
        [
            _event("t1", _utc(2026, 10, 1, 0), heard_ms=1000, counted=False),
            _event("t1", _utc(2026, 10, 2, 0), heard_ms=2000, counted=False),
            _event("t1", _utc(2026, 10, 3, 0), heard_ms=4000, counted=False),
        ],
        DEVICE,
    )
    period = ListeningPeriod(_utc(2026, 10, 2, 0), _utc(2026, 10, 3, 0))
    totals = repository.totals(period)
    assert totals.listening_ms == 2000
    assert totals.sessions == 1
    # The same instant expressed in another offset selects the same rows.
    shifted = ListeningPeriod(
        datetime(2026, 10, 2, 2, tzinfo=PARIS), datetime(2026, 10, 3, 2, tzinfo=PARIS)
    )
    assert repository.totals(shifted).listening_ms == 2000
    assert repository.totals(ALL_TIME).sessions == 3
    with pytest.raises(ValueError):
        ListeningPeriod(datetime(2026, 10, 2), None)


def test_top_tracks_rank_counted_plays_and_keep_latest_snapshot(database: Database) -> None:
    repository = PlayLogRepository(database)
    repository.insert_events(
        [
            _event("a", _utc(2026, 10, 1, 9), heard_ms=60_000, counted=True, title="Old title"),
            _event("a", _utc(2026, 10, 5, 9), heard_ms=60_000, counted=True, title="New title"),
            _event("b", _utc(2026, 10, 2, 9), heard_ms=500_000, counted=False),
            _event("c", _utc(2026, 10, 3, 9), heard_ms=90_000, counted=True),
            _event("c", _utc(2026, 10, 4, 9), heard_ms=90_000, counted=True),
        ],
        DEVICE,
    )
    ranks = repository.top_tracks()
    # "b" has no counted play and is left out, however long it was heard. "a" and "c"
    # tie on counted plays; the longer listening time ranks "c" first.
    assert [rank.track_id for rank in ranks] == ["c", "a"]
    by_id = {rank.track_id: rank for rank in ranks}
    assert by_id["a"].counted_plays == 2
    assert by_id["a"].listening_ms == 120_000
    assert by_id["a"].title == "New title"
    assert by_id["a"].last_played == _utc(2026, 10, 5, 9)
    assert by_id["c"].counted_plays == 2
    assert [rank.track_id for rank in repository.top_tracks(limit=1)] == ["c"]
    with pytest.raises(ValueError):
        repository.top_tracks(limit=0)


def test_top_albums_group_by_album_tag(database: Database) -> None:
    repository = PlayLogRepository(database)
    repository.insert_events(
        [
            _event("a", _utc(2026, 10, 1, 9), heard_ms=60_000, counted=True, album="Blue"),
            _event("b", _utc(2026, 10, 1, 10), heard_ms=60_000, counted=True, album="Blue"),
            _event("c", _utc(2026, 10, 1, 11), heard_ms=60_000, counted=True, album="Red"),
            _event("d", _utc(2026, 10, 1, 12), heard_ms=60_000, counted=True, album=""),
            _event("e", _utc(2026, 10, 1, 13), heard_ms=9_000, counted=False, album="Green"),
        ],
        DEVICE,
    )
    albums = repository.top_albums()
    assert [(album.album, album.counted_plays) for album in albums] == [("Blue", 2), ("Red", 1)]
    assert albums[0].listening_ms == 120_000


def test_daily_listening_uses_the_local_calendar_day(database: Database) -> None:
    repository = PlayLogRepository(database)
    repository.insert_events(
        [
            # 23:30 UTC on the 1st is already the 2nd in Paris (UTC+2 in October).
            _event("a", _utc(2026, 10, 1, 23, 30), heard_ms=60_000, counted=True),
            _event("b", _utc(2026, 10, 2, 8, 0), heard_ms=30_000, counted=True),
            _event("c", _utc(2026, 10, 2, 9, 0), heard_ms=5_000, counted=False),
        ],
        DEVICE,
    )
    days = repository.daily_listening(zone=PARIS)
    assert days == [
        _daily(date(2026, 10, 2), 95_000, 2),
    ]
    utc_days = repository.daily_listening(zone=UTC)
    assert utc_days == [
        _daily(date(2026, 10, 1), 60_000, 1),
        _daily(date(2026, 10, 2), 35_000, 1),
    ]


def _daily(day: date, listening_ms: int, counted_plays: int) -> DailyListening:
    return DailyListening(day=day, listening_ms=listening_ms, counted_plays=counted_plays)


def test_track_play_stats_for_many_tracks_in_chunks(database: Database) -> None:
    repository = PlayLogRepository(database)
    many = [f"track-{index}" for index in range(900)]
    events = [
        _event(track_id, _utc(2026, 10, 1, 9), heard_ms=40_000, counted=True)
        for track_id in many[:850]
    ]
    events.append(_event("track-3", _utc(2026, 10, 9, 9), heard_ms=2_000, counted=False))
    repository.insert_events(events, DEVICE)

    stats = repository.track_play_stats(many)
    assert len(stats) == 850
    assert stats["track-3"].counted_plays == 1
    assert stats["track-3"].sessions == 2
    assert stats["track-3"].last_played == _utc(2026, 10, 9, 9)
    assert "track-899" not in stats

    windowed = repository.track_play_stats(
        ["track-3", "track-5"], ListeningPeriod(_utc(2026, 10, 5, 0), None)
    )
    assert set(windowed) == {"track-3"}
    assert windowed["track-3"].sessions == 1
    assert windowed["track-3"].counted_plays == 0
    assert repository.track_play_stats([]) == {}


def test_reset_deletes_every_event_and_keeps_the_device(database: Database) -> None:
    repository = PlayLogRepository(database)
    repository.insert_events(
        [_event("a", _utc(2026, 10, 1, 9), heard_ms=60_000, counted=True)], DEVICE
    )
    assert repository.reset() == 1
    assert repository.totals().sessions == 0
    assert repository.top_tracks() == []
    assert repository.reset() == 0


def test_device_identifier_is_created_once(database: Database) -> None:
    settings = SettingsRepository(database)
    first = load_or_create_device_id(settings)
    assert str(uuid4()) != first
    assert load_or_create_device_id(settings) == first
    assert settings.get(DEVICE_ID_KEY) == first

    settings.set(DEVICE_ID_KEY, "broken")
    replacement = load_or_create_device_id(settings)
    assert replacement != "broken"
    assert load_or_create_device_id(settings) == replacement

"""Append-only storage and read-only statistics of the permanent listening log.

Timestamps are stored as fixed-width UTC text, so SQLite compares them in time order.
The only deletion is ``reset``, the data-privacy action of the Settings page.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo
from uuid import UUID, uuid4

from mtee.domain.play_log import ListeningPeriod, PlayEvent
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository

__all__ = [
    "ALL_TIME",
    "AlbumRank",
    "ArtistTextPlays",
    "DailyListening",
    "ListeningTotals",
    "PlayLogEvent",
    "PlayLogRepository",
    "TrackPlayStats",
    "TrackRank",
    "load_or_create_device_id",
]

DEVICE_ID_KEY = "play_log.device_id"
ALL_TIME = ListeningPeriod()
_IN_CLAUSE_CHUNK = 400
_DEFAULT_LIMIT = 50


@dataclass(frozen=True, slots=True)
class PlayLogEvent:
    """One row of the log as it travels between devices.

    It carries no file path: a path belongs to one computer. ``track_id`` is the identifier
    the writing device knew the track by. Times are timezone-aware.
    """

    event_id: str
    device_id: str
    track_id: str
    started_at: datetime
    ended_at: datetime
    heard_ms: int
    counted: bool
    artist: str = ""
    title: str = ""
    album: str = ""
    duration_us: int = 0


@dataclass(frozen=True, slots=True)
class ListeningTotals:
    listening_ms: int
    counted_plays: int
    sessions: int


@dataclass(frozen=True, slots=True)
class TrackRank:
    track_id: str
    title: str
    artist: str
    album: str
    path: str
    counted_plays: int
    listening_ms: int
    last_played: datetime


@dataclass(frozen=True, slots=True)
class AlbumRank:
    album: str
    counted_plays: int
    listening_ms: int


@dataclass(frozen=True, slots=True)
class ArtistTextPlays:
    """Listening of one artist text as the log stored it, e.g. ``Chase & Status, Camo``.

    The text is not split here: the statistics split it with the artist rules.
    """

    artist: str
    counted_plays: int
    listening_ms: int


@dataclass(frozen=True, slots=True)
class DailyListening:
    """Listening attributed to the local calendar day its event started on."""

    day: date
    listening_ms: int
    counted_plays: int


@dataclass(frozen=True, slots=True)
class TrackPlayStats:
    track_id: str
    counted_plays: int
    sessions: int
    last_played: datetime


def load_or_create_device_id(settings: SettingsRepository) -> str:
    """Return the installation identifier, creating it once and keeping it afterwards."""
    stored = settings.get(DEVICE_ID_KEY)
    if stored:
        try:
            return str(UUID(stored))
        except ValueError:
            pass
    device_id = str(uuid4())
    settings.set(DEVICE_ID_KEY, device_id)
    return device_id


class PlayLogRepository:
    """Appends closed play events and answers the statistics queries."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def insert_events(self, events: Sequence[PlayEvent], device_id: str) -> int:
        """Append ``events`` in one transaction and return how many were written."""
        UUID(device_id)
        rows = [
            (
                event.event_id,
                event.track.track_id,
                event.track.path,
                event.track.artist,
                event.track.title,
                event.track.album,
                event.track.duration_us,
                _utc_text(event.started_at),
                _utc_text(event.ended_at),
                event.heard_ms,
                1 if event.counted else 0,
                device_id,
            )
            for event in events
        ]
        if not rows:
            return 0
        with self._database.transaction() as connection:
            connection.executemany(
                "INSERT INTO play_events (event_id, track_id, path_at_play, artist, title, "
                "album, duration_us, started_at_utc, ended_at_utc, heard_ms, counted, device_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def events_since(self, cursor: str | None, limit: int) -> tuple[list[PlayLogEvent], str | None]:
        """Return up to ``limit`` events stored after ``cursor``, in insertion order.

        ``play_events`` has no sequence column, so the order is the SQLite ``rowid``: it
        grows with every insert, whatever the start time of the event. The cursor is the
        ``rowid`` of the last event returned, written as text; ``None`` starts from the
        first event. The second value is the cursor to pass next time: that of the last
        event returned, or ``cursor`` itself when nothing is newer. The ``rowid`` of a table
        without an integer key may be renumbered by ``VACUUM`` (MTEE never runs it) and
        starts again after the log is reset, so a cursor is valid for one log only: a
        caller that sees the log shrink starts from ``None``. Events written by other
        devices are included; each carries its ``device_id``.
        """
        _check_limit(limit)
        after = _parse_cursor(cursor)
        rows = (
            self._database.connection()
            .execute(
                "SELECT rowid AS position, event_id, device_id, track_id, artist, title, album, "
                "duration_us, started_at_utc, ended_at_utc, heard_ms, counted "
                "FROM play_events WHERE rowid > ? ORDER BY rowid LIMIT ?",
                (after, limit),
            )
            .fetchall()
        )
        events = [
            PlayLogEvent(
                event_id=str(row["event_id"]),
                device_id=str(row["device_id"]),
                track_id=str(row["track_id"]),
                started_at=_parse_utc(row["started_at_utc"]),
                ended_at=_parse_utc(row["ended_at_utc"]),
                heard_ms=int(row["heard_ms"]),
                counted=bool(row["counted"]),
                artist=str(row["artist"]),
                title=str(row["title"]),
                album=str(row["album"]),
                duration_us=int(row["duration_us"]),
            )
            for row in rows
        ]
        return events, str(rows[-1]["position"]) if rows else cursor

    def insert_remote_events(self, events: Sequence[PlayLogEvent]) -> int:
        """Append events written by other devices; return how many were new.

        An event whose ``event_id`` is already stored is skipped, not an error, so the same
        batch can be sent twice. Each event keeps its own ``device_id``. The batch is checked
        first and written in one transaction: an invalid event refuses the whole batch with
        ``ValueError`` and nothing is stored. The path of a remote listening is unknown here
        and stored empty. The append-only trigger is not involved: rows are only inserted.
        """
        rows = [_remote_row(event) for event in events]
        if not rows:
            return 0
        inserted = 0
        with self._database.transaction() as connection:
            for row in rows:
                cursor = connection.execute(
                    "INSERT INTO play_events (event_id, track_id, path_at_play, artist, title, "
                    "album, duration_us, started_at_utc, ended_at_utc, heard_ms, counted, "
                    "device_id) VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(event_id) DO NOTHING",
                    row,
                )
                inserted += int(cursor.rowcount)
        return inserted

    def totals(self, period: ListeningPeriod = ALL_TIME) -> ListeningTotals:
        """Total heard time, counted plays and every listening session of the period."""
        where, params = _period_clause(period)
        row = (
            self._database.connection()
            .execute(
                "SELECT COALESCE(SUM(heard_ms), 0) AS listening_ms, "
                "COALESCE(SUM(counted), 0) AS counted_plays, COUNT(*) AS sessions "
                f"FROM play_events{where}",
                params,
            )
            .fetchone()
        )
        return ListeningTotals(
            listening_ms=int(row["listening_ms"]),
            counted_plays=int(row["counted_plays"]),
            sessions=int(row["sessions"]),
        )

    def top_tracks(
        self, period: ListeningPeriod = ALL_TIME, limit: int = _DEFAULT_LIMIT
    ) -> list[TrackRank]:
        """Tracks with at least one counted play, most played first.

        The title, artist, album and path come from the latest listening of the track.
        """
        _check_limit(limit)
        where, params = _period_clause(period)
        rows = (
            self._database.connection()
            .execute(
                "SELECT track_id, title, artist, album, path_at_play, "
                "SUM(counted) AS counted_plays, SUM(heard_ms) AS listening_ms, "
                "MAX(started_at_utc) AS last_played_utc "
                f"FROM play_events{where} GROUP BY track_id "
                "HAVING SUM(counted) > 0 "
                "ORDER BY counted_plays DESC, listening_ms DESC, track_id ASC LIMIT ?",
                (*params, limit),
            )
            .fetchall()
        )
        return [
            TrackRank(
                track_id=str(row["track_id"]),
                title=str(row["title"]),
                artist=str(row["artist"]),
                album=str(row["album"]),
                path=str(row["path_at_play"]),
                counted_plays=int(row["counted_plays"]),
                listening_ms=int(row["listening_ms"]),
                last_played=_parse_utc(row["last_played_utc"]),
            )
            for row in rows
        ]

    def top_albums(
        self, period: ListeningPeriod = ALL_TIME, limit: int = _DEFAULT_LIMIT
    ) -> list[AlbumRank]:
        """Albums (grouped by their album tag text) with at least one counted play."""
        _check_limit(limit)
        where, params = _period_clause(period, extra=("album <> ''",))
        rows = (
            self._database.connection()
            .execute(
                "SELECT album, SUM(counted) AS counted_plays, SUM(heard_ms) AS listening_ms "
                f"FROM play_events{where} GROUP BY album HAVING SUM(counted) > 0 "
                "ORDER BY counted_plays DESC, listening_ms DESC, album ASC LIMIT ?",
                (*params, limit),
            )
            .fetchall()
        )
        return [
            AlbumRank(
                album=str(row["album"]),
                counted_plays=int(row["counted_plays"]),
                listening_ms=int(row["listening_ms"]),
            )
            for row in rows
        ]

    def artist_texts(self, period: ListeningPeriod = ALL_TIME) -> list[ArtistTextPlays]:
        """Counted plays and heard time of each artist text of the period, most played first.

        Events without an artist text are left out. Every event counts for the heard time,
        counted or not, as the track ranking does.
        """
        where, params = _period_clause(period, extra=("artist <> ''",))
        rows = (
            self._database.connection()
            .execute(
                "SELECT artist, SUM(counted) AS counted_plays, SUM(heard_ms) AS listening_ms "
                f"FROM play_events{where} GROUP BY artist",
                params,
            )
            .fetchall()
        )
        return [
            ArtistTextPlays(
                artist=str(row["artist"]),
                counted_plays=int(row["counted_plays"]),
                listening_ms=int(row["listening_ms"]),
            )
            for row in rows
        ]

    def daily_listening(
        self, period: ListeningPeriod = ALL_TIME, *, zone: tzinfo | None = None
    ) -> list[DailyListening]:
        """Listening per calendar day, ascending, for the days that have events.

        ``zone`` defaults to the local time zone of the machine, applied to each event
        start, so the day boundaries follow daylight saving time. Days without events are
        not returned; a chart fills them in.
        """
        where, params = _period_clause(period)
        rows = (
            self._database.connection()
            .execute(
                f"SELECT started_at_utc, heard_ms, counted FROM play_events{where}",
                params,
            )
            .fetchall()
        )
        per_day: dict[date, list[int]] = {}
        for row in rows:
            started = _parse_utc(row["started_at_utc"])
            local_day = started.astimezone(zone).date()
            bucket = per_day.setdefault(local_day, [0, 0])
            bucket[0] += int(row["heard_ms"])
            bucket[1] += int(row["counted"])
        return [
            DailyListening(day=day, listening_ms=values[0], counted_plays=values[1])
            for day, values in sorted(per_day.items())
        ]

    def track_play_stats(
        self, track_ids: Iterable[str], period: ListeningPeriod = ALL_TIME
    ) -> dict[str, TrackPlayStats]:
        """Counted plays, sessions and last listening for many tracks in few queries.

        Tracks that were never listened to in the period are absent from the result.
        """
        identities = list(dict.fromkeys(str(track_id) for track_id in track_ids))
        result: dict[str, TrackPlayStats] = {}
        connection = self._database.connection()
        for start in range(0, len(identities), _IN_CLAUSE_CHUNK):
            chunk = identities[start : start + _IN_CLAUSE_CHUNK]
            where, params = _period_clause(
                period, extra=(f"track_id IN ({', '.join('?' * len(chunk))})",)
            )
            rows = connection.execute(
                "SELECT track_id, SUM(counted) AS counted_plays, COUNT(*) AS sessions, "
                f"MAX(started_at_utc) AS last_played_utc FROM play_events{where} "
                "GROUP BY track_id",
                (*chunk, *params),
            ).fetchall()
            for row in rows:
                track_id = str(row["track_id"])
                result[track_id] = TrackPlayStats(
                    track_id=track_id,
                    counted_plays=int(row["counted_plays"]),
                    sessions=int(row["sessions"]),
                    last_played=_parse_utc(row["last_played_utc"]),
                )
        return result

    def reset(self) -> int:
        """Delete every play event (the statistics reset) and return how many were removed."""
        with self._database.transaction() as connection:
            cursor = connection.execute("DELETE FROM play_events")
            return int(cursor.rowcount)


def _period_clause(
    period: ListeningPeriod, *, extra: tuple[str, ...] = ()
) -> tuple[str, tuple[str, ...]]:
    conditions: list[str] = list(extra)
    params: list[str] = []
    if period.start is not None:
        conditions.append("started_at_utc >= ?")
        params.append(_utc_text(period.start))
    if period.end is not None:
        conditions.append("started_at_utc < ?")
        params.append(_utc_text(period.end))
    if not conditions:
        return "", ()
    return " WHERE " + " AND ".join(conditions), tuple(params)


def _parse_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isascii() or not cursor.isdigit():
        raise ValueError("a play log cursor comes from a previous events_since call")
    return int(cursor)


def _remote_row(event: PlayLogEvent) -> tuple[object, ...]:
    """Check one event of another device and return its values in column order."""
    if not event.event_id or not event.device_id or not event.track_id:
        raise ValueError("a play event needs an event_id, a device_id and a track_id")
    if event.heard_ms < 0 or event.duration_us < 0:
        raise ValueError("heard_ms and duration_us cannot be negative")
    return (
        event.event_id,
        event.track_id,
        event.artist,
        event.title,
        event.album,
        event.duration_us,
        _utc_text(event.started_at),
        _utc_text(event.ended_at),
        event.heard_ms,
        1 if event.counted else 0,
        event.device_id,
    )


def _check_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer")


def _utc_text(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_utc(value: object) -> datetime:
    return datetime.fromisoformat(str(value)).astimezone(UTC)

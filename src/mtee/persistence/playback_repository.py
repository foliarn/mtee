"""Versioned, validated storage for the local playback session."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from mtee.domain.playback_queue import QueueEntry, QueueState
from mtee.persistence.database import Database

_SNAPSHOT_KEYS = (
    "id",
    "title",
    "artist",
    "album",
    "filename",
    "duration",
    "durationUs",
    "seconds",
    "cover",
    "status",
)


class PlaybackSessionError(ValueError):
    """The stored playback session is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class PlaybackSession:
    queue: QueueState
    position_us: int = 0
    write_sequence: int = 0


class PlaybackRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def load(self) -> PlaybackSession | None:
        row = (
            self._database.connection()
            .execute("SELECT value_json FROM playback_session WHERE session_id = 'main'")
            .fetchone()
        )
        if row is None:
            return None
        try:
            data = json.loads(str(row["value_json"]))
            return _decode(data)
        except (TypeError, ValueError, KeyError) as error:
            raise PlaybackSessionError(f"The saved playback session is invalid: {error}") from error

    def save(self, session: PlaybackSession) -> bool:
        if session.position_us < 0 or session.write_sequence < 0:
            raise PlaybackSessionError("Negative playback position or write sequence")
        session.queue.validate()
        encoded = json.dumps(_encode(session), ensure_ascii=False, separators=(",", ":"))
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with self._database.transaction() as connection:
            previous = connection.execute(
                "SELECT value_json FROM playback_session WHERE session_id = 'main'"
            ).fetchone()
            if previous is not None:
                try:
                    old_sequence = int(json.loads(str(previous["value_json"]))["write_sequence"])
                except (TypeError, ValueError, KeyError) as error:
                    raise PlaybackSessionError("Existing playback session is invalid") from error
                if old_sequence >= session.write_sequence:
                    return False
            connection.execute(
                "INSERT INTO playback_session(session_id, value_json, updated_at_utc) "
                "VALUES ('main', ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
                "value_json=excluded.value_json, updated_at_utc=excluded.updated_at_utc",
                (encoded, stamp),
            )
        return True


def _snapshot(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PlaybackSessionError("Entry snapshot is not an object")
    return {
        key: item
        for key in _SNAPSHOT_KEYS
        if (item := value.get(key)) is not None and isinstance(item, str | int | float | bool)
    }


def _encode_entry(entry: QueueEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "track_id": entry.track_id,
        "origin": entry.origin,
        "source": entry.source,
        "source_title": entry.source_title,
        "snapshot": _snapshot(entry.snapshot),
    }


def _decode_entry(data: Any) -> QueueEntry:
    if not isinstance(data, dict):
        raise PlaybackSessionError("Queue entry is not an object")
    entry_id = data["entry_id"]
    track_id = data["track_id"]
    origin = data["origin"]
    source = data["source"]
    source_title = data["source_title"]
    if not all(isinstance(item, str) for item in (entry_id, track_id, source, source_title)):
        raise PlaybackSessionError("Queue entry has invalid text fields")
    UUID(entry_id)
    if not track_id or origin not in ("manual", "context"):
        raise PlaybackSessionError("Queue entry has invalid track or origin")
    return QueueEntry(
        entry_id,
        track_id,
        cast(Literal["manual", "context"], origin),
        source,
        source_title,
        _snapshot(data.get("snapshot")),
    )


def _encode(session: PlaybackSession) -> dict[str, Any]:
    queue = session.queue
    return {
        "version": 1,
        "write_sequence": session.write_sequence,
        "position_us": session.position_us,
        "queue": {
            "revision": queue.revision,
            "past": [_encode_entry(entry) for entry in queue.past],
            "current": _encode_entry(queue.current) if queue.current else None,
            "upcoming": [_encode_entry(entry) for entry in queue.upcoming],
            "context_order": [_encode_entry(entry) for entry in queue.context_order],
            "source": queue.source,
            "source_title": queue.source_title,
            "shuffle": queue.shuffle,
            "repeat": queue.repeat,
        },
    }


def _decode(data: Any) -> PlaybackSession:
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("version"), int)
        or isinstance(data.get("version"), bool)
        or data.get("version") != 1
    ):
        raise PlaybackSessionError("Unsupported playback session version")
    position = data["position_us"]
    sequence = data["write_sequence"]
    queue_data = data["queue"]
    if (
        not isinstance(position, int)
        or isinstance(position, bool)
        or position < 0
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence < 0
        or not isinstance(queue_data, dict)
    ):
        raise PlaybackSessionError("Invalid playback position, sequence or queue")
    revision = queue_data["revision"]
    past = queue_data["past"]
    current = queue_data["current"]
    upcoming = queue_data["upcoming"]
    reference = queue_data["context_order"]
    source = queue_data["source"]
    source_title = queue_data["source_title"]
    shuffle = queue_data["shuffle"]
    repeat = queue_data["repeat"]
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or not all(isinstance(items, list) for items in (past, upcoming, reference))
        or not isinstance(source, str)
        or not isinstance(source_title, str)
        or not isinstance(shuffle, bool)
        or repeat not in ("off", "one", "all")
    ):
        raise PlaybackSessionError("Invalid queue structure")
    queue = QueueState(
        revision=revision,
        past=tuple(_decode_entry(entry) for entry in past),
        current=_decode_entry(current) if current is not None else None,
        upcoming=tuple(_decode_entry(entry) for entry in upcoming),
        context_order=tuple(_decode_entry(entry) for entry in reference),
        source=source,
        source_title=source_title,
        shuffle=shuffle,
        repeat=cast(Literal["off", "one", "all"], repeat),
    )
    queue.validate()
    return PlaybackSession(queue, position, sequence)

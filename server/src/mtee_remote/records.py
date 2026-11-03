"""Records shared by the MTEE desktops (and later the phones): play log, playlists, per-track
data and synced settings (milestone 126.7). The routes are in `routes/records.py`.

The values are opaque JSON. The server checks their shapes and sizes and stores them as they
are; it never reads what they mean. Every write that changes something adds one journal entry
of its kind (`play_events`, `playlist`, `track_data`, `settings`), so the other devices of the
user learn about it through `/api/v1/changes`. Every function takes the caller's user id, so a
user never sees another user's records.

- Play events are idempotent by `event_id`: a repeated event is skipped, not stored twice.
- A playlist has a revision. An update or a delete must name the revision it is based on
  (`base_revision`); any other revision is a `conflict` (409) that names the current one.
  A deleted playlist stays as a tombstone so that other devices learn about the deletion.
- A track data layer is replaced as a whole. `null` deletes the layer.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from mtee_remote import clock, journal
from mtee_remote.db import Database, Transaction
from mtee_remote.errors import ApiError

EVENT_MAX_BYTES = 16 * 1024
EVENTS_PER_CALL = 1000
EVENT_ID_MAX = 128
PLAYLIST_NAME_MAX = 500
PLAYLIST_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
ENTRY_MAX_BYTES = 16 * 1024
ENTRIES_MAX = 20000
TRACK_LAYER_MAX_BYTES = 64 * 1024
TRACK_LAYERS = ("analysis", "loudness", "corrections")
SETTING_MAX_BYTES = 16 * 1024
SETTINGS_PER_CALL = 200
SETTING_KEY_PATTERN = re.compile(r"[a-z0-9_./-]{1,100}")


def _now() -> str:
    return clock.to_iso(clock.utc_now())


def _text(value: Any, label: str, max_len: int) -> str:
    """Return `value` if it is text of 1 to `max_len` characters that can be stored."""
    if not isinstance(value, str) or not 1 <= len(value) <= max_len:
        raise ApiError("bad_request", f"{label} must be text of 1 to {max_len} characters.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ApiError("bad_request", f"{label} is not valid text.") from None
    return value


def _dump(value: Any, label: str, limit: int | None = None) -> str:
    """Return the JSON text of `value`; refuse NaN and text longer than `limit` characters.

    `ensure_ascii` is on (the default), so the length of the text is its size in bytes.
    """
    try:
        text = json.dumps(value, separators=(",", ":"), allow_nan=False)
    except ValueError:
        raise ApiError("bad_request", f"{label} is not valid JSON.") from None
    if limit is not None and len(text) > limit:
        raise ApiError("bad_request", f"{label} is larger than {limit} bytes.")
    return text


def _check_playlist_id(playlist_id: str) -> None:
    if PLAYLIST_ID_PATTERN.fullmatch(playlist_id) is None:
        raise ApiError("bad_request", "The playlist id is not valid.")


def _conflict(current: int, base: int | None) -> ApiError:
    sent = "no base revision" if base is None else f"base revision {base}"
    return ApiError(
        "conflict",
        f"The playlist changed on the server: current revision {current}, the request had {sent}.",
    )


# -- play log -----------------------------------------------------------------------------


def add_play_events(db: Database, user_id: str, device_id: str, events: Any) -> dict[str, int]:
    """Store a batch of play events of the caller's device; return how many were new.

    Each event is a JSON object with an `event_id`. The whole object is kept as the payload.
    An event whose `event_id` the user already has is skipped. One journal entry
    `play_events` `{count, last_seq}` is added when something was stored.
    """
    if not isinstance(events, list):
        raise ApiError("bad_request", "The field 'events' must be a list.")
    if len(events) > EVENTS_PER_CALL:
        raise ApiError("bad_request", f"A call may send at most {EVENTS_PER_CALL} events.")
    prepared: list[tuple[str, str]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ApiError("bad_request", f"Event {index} must be a JSON object.")
        event_id = _text(event.get("event_id"), f"Event {index}: 'event_id'", EVENT_ID_MAX)
        prepared.append((event_id, _dump(event, f"Event {index}", EVENT_MAX_BYTES)))

    inserted = 0
    last_seq = 0
    now = _now()
    with db.transaction() as tx:
        for event_id, text in prepared:
            cursor = tx.conn.execute(
                "INSERT INTO play_events(user_id, event_id, device_id, payload_json,"
                " received_at_utc) VALUES (?,?,?,?,?)"
                " ON CONFLICT(user_id, event_id) DO NOTHING",
                (user_id, event_id, device_id, text, now),
            )
            if cursor.rowcount == 1:
                inserted += 1
                last_seq = int(cursor.lastrowid or 0)
        if inserted:
            journal.append(
                tx, user_id, "play_events", None, {"count": inserted, "last_seq": last_seq}
            )
    return {"inserted": inserted, "skipped": len(prepared) - inserted}


def list_play_events(db: Database, user_id: str, since: int, limit: int) -> dict[str, Any]:
    """Return up to `limit` play events of the user after sequence `since`, oldest first."""
    rows = (
        db.conn()
        .execute(
            "SELECT seq, event_id, device_id, payload_json FROM play_events"
            " WHERE user_id = ? AND seq > ? ORDER BY seq LIMIT ?",
            (user_id, since, limit + 1),
        )
        .fetchall()
    )
    page = rows[:limit]
    return {
        "events": [
            {
                "seq": row["seq"],
                "event_id": row["event_id"],
                "device_id": row["device_id"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in page
        ],
        "next": page[-1]["seq"] if page else since,
        "more": len(rows) > limit,
    }


# -- playlists ----------------------------------------------------------------------------


def _playlist_meta(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "playlist_id": row["playlist_id"],
        "name": row["name"],
        "revision": row["revision"],
        "deleted": bool(row["deleted"]),
        "updated_at_utc": row["updated_at_utc"],
        "updated_by_device_id": row["updated_by_device_id"],
    }


def list_playlists(db: Database, user_id: str) -> list[dict[str, Any]]:
    """Return every playlist of the user, deleted ones (tombstones) included, without entries."""
    rows = (
        db.conn()
        .execute(
            "SELECT playlist_id, name, revision, deleted, updated_at_utc, updated_by_device_id"
            " FROM record_playlists WHERE user_id = ? ORDER BY playlist_id",
            (user_id,),
        )
        .fetchall()
    )
    return [_playlist_meta(row) for row in rows]


def get_playlist(db: Database, user_id: str, playlist_id: str) -> dict[str, Any]:
    """Return one playlist with its entries; `not_found` when the user has no such playlist."""
    row = (
        db.conn()
        .execute(
            "SELECT playlist_id, name, revision, deleted, updated_at_utc, updated_by_device_id,"
            " entries_json FROM record_playlists WHERE user_id = ? AND playlist_id = ?",
            (user_id, playlist_id),
        )
        .fetchone()
    )
    if row is None:
        raise ApiError("not_found", "Unknown playlist.")
    return {**_playlist_meta(row), "entries": json.loads(row["entries_json"])}


def put_playlist(
    db: Database,
    user_id: str,
    device_id: str,
    playlist_id: str,
    *,
    name: Any,
    entries: Any,
    base_revision: int | None,
) -> dict[str, Any]:
    """Create or replace a whole playlist; return it with its new revision.

    - Absent playlist and `base_revision` None: created at revision 1.
    - Existing playlist (also a deleted one) whose revision equals `base_revision`: replaced,
      revision + 1, and it is no longer deleted.
    - Anything else: `conflict` (409), the message names the current revision.
    Journal entry `playlist` `{playlist_id, revision, deleted: false}`.
    """
    _check_playlist_id(playlist_id)
    name = _text(name, "The field 'name'", PLAYLIST_NAME_MAX)
    if not isinstance(entries, list):
        raise ApiError("bad_request", "The field 'entries' must be a list.")
    if len(entries) > ENTRIES_MAX:
        raise ApiError("bad_request", f"A playlist may hold at most {ENTRIES_MAX} entries.")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ApiError("bad_request", f"Entry {index} must be a JSON object.")
        _dump(entry, f"Entry {index}", ENTRY_MAX_BYTES)
    entries_text = _dump(entries, "The entries")
    now = _now()

    with db.transaction() as tx:
        row = tx.conn.execute(
            "SELECT revision FROM record_playlists WHERE user_id = ? AND playlist_id = ?",
            (user_id, playlist_id),
        ).fetchone()
        if row is None:
            if base_revision is not None:
                raise _conflict(0, base_revision)
            revision = 1
            tx.conn.execute(
                "INSERT INTO record_playlists(user_id, playlist_id, name, revision, entries_json,"
                " deleted, updated_at_utc, updated_by_device_id) VALUES (?,?,?,?,?,0,?,?)",
                (user_id, playlist_id, name, revision, entries_text, now, device_id),
            )
        else:
            current = int(row["revision"])
            if base_revision != current:
                raise _conflict(current, base_revision)
            revision = current + 1
            tx.conn.execute(
                "UPDATE record_playlists SET name = ?, revision = ?, entries_json = ?,"
                " deleted = 0, updated_at_utc = ?, updated_by_device_id = ?"
                " WHERE user_id = ? AND playlist_id = ?",
                (name, revision, entries_text, now, device_id, user_id, playlist_id),
            )
        journal.append(
            tx,
            user_id,
            "playlist",
            None,
            {"playlist_id": playlist_id, "revision": revision, "deleted": False},
        )
    return {
        "playlist_id": playlist_id,
        "name": name,
        "revision": revision,
        "deleted": False,
        "updated_at_utc": now,
        "updated_by_device_id": device_id,
        "entries": entries,
    }


def delete_playlist(
    db: Database, user_id: str, device_id: str, playlist_id: str, base_revision: int
) -> dict[str, Any]:
    """Mark a playlist deleted (revision + 1) and return its metadata.

    `base_revision` must equal the stored revision, else `conflict` (409). The entries are kept.
    Journal entry `playlist` `{playlist_id, revision, deleted: true}`.
    """
    _check_playlist_id(playlist_id)
    now = _now()
    with db.transaction() as tx:
        row = tx.conn.execute(
            "SELECT name, revision FROM record_playlists WHERE user_id = ? AND playlist_id = ?",
            (user_id, playlist_id),
        ).fetchone()
        if row is None:
            raise ApiError("not_found", "Unknown playlist.")
        current = int(row["revision"])
        if base_revision != current:
            raise _conflict(current, base_revision)
        revision = current + 1
        tx.conn.execute(
            "UPDATE record_playlists SET deleted = 1, revision = ?, updated_at_utc = ?,"
            " updated_by_device_id = ? WHERE user_id = ? AND playlist_id = ?",
            (revision, now, device_id, user_id, playlist_id),
        )
        journal.append(
            tx,
            user_id,
            "playlist",
            None,
            {"playlist_id": playlist_id, "revision": revision, "deleted": True},
        )
        name = row["name"]
    return {
        "playlist_id": playlist_id,
        "name": name,
        "revision": revision,
        "deleted": True,
        "updated_at_utc": now,
        "updated_by_device_id": device_id,
    }


# -- track data --------------------------------------------------------------------------


def _owned_item(conn: sqlite3.Connection, user_id: str, item_id: str) -> None:
    """Raise `not_found` unless the item exists and belongs to the user (any state)."""
    row = conn.execute(
        "SELECT 1 FROM items WHERE item_id = ? AND user_id = ?", (item_id, user_id)
    ).fetchone()
    if row is None:
        raise ApiError("not_found", "Unknown item.")


def get_track_data(db: Database, user_id: str, item_id: str) -> dict[str, Any]:
    """Return the layers stored for the user's item; a layer that was never set is absent."""
    conn = db.conn()
    _owned_item(conn, user_id, item_id)
    rows = conn.execute(
        "SELECT layer, value_json FROM record_track_data WHERE user_id = ? AND item_id = ?",
        (user_id, item_id),
    ).fetchall()
    return {
        "item_id": item_id,
        "layers": {row["layer"]: json.loads(row["value_json"]) for row in rows},
    }


def put_track_data(
    db: Database, user_id: str, item_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Set or delete (`null`) the layers given in `changes`; return the item's layers.

    Layers that are not in `changes` keep their value. Only `TRACK_LAYERS` are accepted.
    Journal entry `track_data` `{item_id, layers}` lists the layers that were given.
    """
    unknown = sorted(set(changes) - set(TRACK_LAYERS))
    if unknown:
        raise ApiError("bad_request", f"'{unknown[0]}' is not a track data layer.")
    texts: dict[str, str | None] = {}
    for layer in TRACK_LAYERS:
        if layer in changes:
            value = changes[layer]
            label = f"The track data layer '{layer}'"
            texts[layer] = None if value is None else _dump(value, label, TRACK_LAYER_MAX_BYTES)
    now = _now()
    with db.transaction() as tx:
        _owned_item(tx.conn, user_id, item_id)
        for layer, text in texts.items():
            if text is None:
                tx.conn.execute(
                    "DELETE FROM record_track_data WHERE user_id = ? AND item_id = ? AND layer = ?",
                    (user_id, item_id, layer),
                )
            else:
                _upsert_track_layer(tx, user_id, item_id, layer, text, now)
        if texts:
            journal.append(
                tx,
                user_id,
                "track_data",
                item_id,
                {"item_id": item_id, "layers": sorted(texts)},
            )
    return get_track_data(db, user_id, item_id)


def _upsert_track_layer(
    tx: Transaction, user_id: str, item_id: str, layer: str, text: str, now: str
) -> None:
    tx.conn.execute(
        "INSERT INTO record_track_data(user_id, item_id, layer, value_json, updated_at_utc)"
        " VALUES (?,?,?,?,?) ON CONFLICT(user_id, item_id, layer) DO UPDATE SET"
        " value_json = excluded.value_json, updated_at_utc = excluded.updated_at_utc",
        (user_id, item_id, layer, text, now),
    )


# -- synced settings ---------------------------------------------------------------------


def get_settings(db: Database, user_id: str) -> dict[str, Any]:
    """Return every synced setting of the user as a `key: value` object."""
    rows = (
        db.conn()
        .execute(
            "SELECT key, value_json FROM record_settings WHERE user_id = ? ORDER BY key",
            (user_id,),
        )
        .fetchall()
    )
    return {row["key"]: json.loads(row["value_json"]) for row in rows}


def put_settings(db: Database, user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Set or delete (`null`) the given settings; return all the user's settings.

    Keys match `SETTING_KEY_PATTERN`. Journal entry `settings` `{keys}` lists the keys given.
    """
    if len(changes) > SETTINGS_PER_CALL:
        raise ApiError("bad_request", f"A call may change at most {SETTINGS_PER_CALL} settings.")
    texts: dict[str, str | None] = {}
    for key, value in changes.items():
        if SETTING_KEY_PATTERN.fullmatch(key) is None:
            raise ApiError("bad_request", f"The setting key '{key}' is not allowed.")
        label = f"The setting '{key}'"
        texts[key] = None if value is None else _dump(value, label, SETTING_MAX_BYTES)
    now = _now()
    with db.transaction() as tx:
        for key, text in sorted(texts.items()):
            if text is None:
                tx.conn.execute(
                    "DELETE FROM record_settings WHERE user_id = ? AND key = ?", (user_id, key)
                )
            else:
                tx.conn.execute(
                    "INSERT INTO record_settings(user_id, key, value_json, updated_at_utc)"
                    " VALUES (?,?,?,?) ON CONFLICT(user_id, key) DO UPDATE SET"
                    " value_json = excluded.value_json, updated_at_utc = excluded.updated_at_utc",
                    (user_id, key, text, now),
                )
        if texts:
            journal.append(tx, user_id, "settings", None, {"keys": sorted(texts)})
    return get_settings(db, user_id)

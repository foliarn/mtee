"""The records of MTEE Remote: play log, playlists, track data and synced settings (plan 126.7).

Each record goes to the server through the ``records`` routes and is kept here through the core's
own services: the play log (``context.play_log``), the playlists (``context.playlists``, with the
revision check of ``replace_entries``), the analysis, loudness and corrections
(``context.track_data``)
and the allow-listed settings (``context.synced_settings``). Nothing here writes SQL into a core
table, and nothing reads or writes an audio file.

Push (in each pass that sends, so in Auto mode and after Apply) sends this device's play events, its
playlists, the track data layers that changed and the synced settings that changed. Pull (on a
fetch, when the journal has ``play_events``, ``playlist``, ``track_data`` or ``settings``) brings in
the other devices' records. A track is matched with an item through ``remote_links`` or, for a
server-only track, through ``remote_server_items.source_track_id``. A playlist is synced only when
each of its entries is on the server. A record that was received is remembered (its revision or its
digest), so it is never sent back. A failing part is logged and the other parts still run.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import uuid
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any, TypeVar

from mtee.domain.jobs import JobCancelledError
from mtee.plugins.api import (
    CapabilityUnavailableError,
    CreditCorrection,
    PlayLogEvent,
    PluginContext,
    SettingNotSyncedError,
    StaleRevisionError,
    TrackAnalysisData,
    TrackLoudnessData,
)

from .client import ApiError, NetworkError, RemoteClient
from .store import CONFLICT_OPEN, RemoteStore, insert_conflict, utc_now, write_log

T = TypeVar("T")

PLAY_PUSH_CURSOR = "play_local"
PLAY_PULL_CURSOR = "play_server"
PLAY_PAGE = 500
LAYERS = ("analysis", "loudness", "corrections")

# Plugin settings (kept in the ``plugins.remote.`` namespace of the core settings).
SYNCED_KEYS_SETTING = "synced_keys"
SETTINGS_SENT_SETTING = "settings_sent"
RETIRED_PLAYLISTS_SETTING = "retired_playlists"
SKIPPED_SETTING = "skipped_records"

KIND_PLAYLIST = "playlist_both_changed"
KEEP_LOCAL = "keep_local"
KEEP_SERVER = "keep_server"
KEEP_BOTH = "keep_both"

SETTING_LABELS = {
    "playback/normalization": "Loudness normalization",
    "profile/display_name": "Display name",
    "playlists/columns": "Playlist columns",
    "plugins.enabled": "Plugins switched on",
}


class PlaylistRefusedError(Exception):
    """A playlist choice that cannot be done now; nothing was changed, and the conflict stays."""

    readable = True


class PlaylistObsoleteError(Exception):
    """The situation of a playlist conflict no longer holds; the conflict resolves as obsolete."""

    readable = True


@dataclasses.dataclass(frozen=True)
class PlaylistLink:
    """A local playlist and its server copy, with the revisions both had when they last agreed."""

    local_playlist_id: str
    server_playlist_id: str
    synced_local_revision: int
    synced_server_revision: int


# -- mapping of tracks and items ---------------------------------------------------------------
def item_of_track(store: RemoteStore, track_id: str) -> str | None:
    """The server item of a local track: its link, or the item of a server-only track."""
    conn = store.connection()
    row = conn.execute(
        "SELECT item_id FROM remote_links WHERE track_id = ?", (track_id,)
    ).fetchone()
    if row is not None:
        return str(row["item_id"])
    row = conn.execute(
        "SELECT item_id FROM remote_server_items WHERE source_track_id = ?", (track_id,)
    ).fetchone()
    return None if row is None else str(row["item_id"])


def track_of_item(store: RemoteStore, item_id: str) -> str | None:
    """The local track of a server item: its link, or the server-only track of the item."""
    conn = store.connection()
    row = conn.execute("SELECT track_id FROM remote_links WHERE item_id = ?", (item_id,)).fetchone()
    if row is not None:
        return str(row["track_id"])
    row = conn.execute(
        "SELECT source_track_id FROM remote_server_items WHERE item_id = ?", (item_id,)
    ).fetchone()
    if row is None or row["source_track_id"] is None:
        return None
    return str(row["source_track_id"])


# -- the plugin's own small state ----------------------------------------------------------------
def _cursor(store: RemoteStore, name: str) -> str | None:
    row = (
        store.connection()
        .execute("SELECT value FROM remote_cursors WHERE name = ?", (name,))
        .fetchone()
    )
    return None if row is None else str(row["value"])


def _set_cursor(store: RemoteStore, name: str, value: str) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_cursors (name, value) VALUES (?, ?)"
            " ON CONFLICT (name) DO UPDATE SET value = excluded.value",
            (name, value),
        )


def _log(store: RemoteStore, text: str, level: str = "info") -> None:
    with store.transaction() as conn:
        write_log(conn, text, level)


def _dict_setting(context: PluginContext, key: str) -> dict[str, Any]:
    value = context.settings.get_json(key, {})
    return dict(value) if isinstance(value, dict) else {}


def _list_setting(context: PluginContext, key: str) -> list[str]:
    value = context.settings.get_json(key, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def _skip_once(
    context: PluginContext, store: RemoteStore, key: str, revision: int, text: str
) -> None:
    """Log a record that is left out of the sync, once for each revision of it."""
    skipped = _dict_setting(context, SKIPPED_SETTING)
    if skipped.get(key) == revision:
        return
    skipped[key] = revision
    context.settings.set_json(SKIPPED_SETTING, skipped)
    _log(store, text, "warning")


def _readable(error: BaseException) -> str:
    if isinstance(error, ApiError):
        return error.message
    if isinstance(error, NetworkError):
        return str(error)
    if getattr(error, "readable", False):
        return str(error)
    return f"{type(error).__name__}: {error}"


@contextlib.contextmanager
def _guarded(store: RemoteStore, label: str) -> Iterator[None]:
    """One part of the records: a failure is logged, and the other parts still run.

    A context that is not available (``CapabilityUnavailableError``) is not an error: it is silent.
    """
    try:
        yield
    except JobCancelledError:
        raise
    except CapabilityUnavailableError:
        return
    except Exception as error:
        _log(store, f"{label} was not synced: {_readable(error)}", "warning")


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _load_json(text: str | None) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


# -- play log ------------------------------------------------------------------------------------
def push_play_events(context: PluginContext, store: RemoteStore, client: RemoteClient) -> int:
    """Send the play events of this device after the stored cursor; return how many were sent.

    The cursor is stored after each page the server took, so a cut run sends the rest next time.
    """
    own = context.play_log.device_id
    cursor = _cursor(store, PLAY_PUSH_CURSOR)
    items: dict[str, str | None] = {}
    sent = 0
    while True:
        try:
            events, next_cursor = context.play_log.events_since(cursor, PLAY_PAGE)
        except ValueError:
            # The log was reset: the numbers of the old log are void, so it is read from its start.
            cursor = None
            events, next_cursor = context.play_log.events_since(None, PLAY_PAGE)
        payloads: list[dict[str, Any]] = []
        for event in events:
            if event.device_id != own:
                continue
            if event.track_id not in items:
                items[event.track_id] = item_of_track(store, event.track_id)
            payloads.append(_play_payload(event, items[event.track_id]))
        if payloads:
            client.post_play_events(payloads)
            sent += len(payloads)
        if next_cursor is not None:
            cursor = next_cursor
            _set_cursor(store, PLAY_PUSH_CURSOR, cursor)
        if len(events) < PLAY_PAGE:
            return sent


def _play_payload(event: PlayLogEvent, item_id: str | None) -> dict[str, Any]:
    """The event as the server keeps it: every field of the log, its item and its display values."""
    return {
        "event_id": event.event_id,
        "device_id": event.device_id,
        "track_id": event.track_id,
        "item_id": item_id,
        "started_at": event.started_at.isoformat(),
        "ended_at": event.ended_at.isoformat(),
        "heard_ms": event.heard_ms,
        "counted": event.counted,
        "title": event.title,
        "artist": event.artist,
        "artists": [event.artist] if event.artist else [],
        "album": event.album,
        "duration_us": event.duration_us,
    }


def pull_play_events(context: PluginContext, store: RemoteStore, client: RemoteClient) -> int:
    """Store the play events of the other devices; return how many were new.

    Events of this device are skipped. An event whose item is not on this computer is skipped and
    counted (one log line per pass). The cursor is stored after each page.
    """
    own = context.play_log.device_id
    cursor = int(_cursor(store, PLAY_PULL_CURSOR) or 0)
    received = 0
    skipped = 0
    while True:
        page = client.play_events(since=cursor, limit=PLAY_PAGE)
        events: list[PlayLogEvent] = []
        for raw in page.events:
            payload = raw.get("payload")
            if not isinstance(payload, dict) or payload.get("device_id") == own:
                continue
            item_id = payload.get("item_id")
            track_id = track_of_item(store, item_id) if isinstance(item_id, str) else None
            if track_id is None:
                skipped += 1
                continue
            try:
                events.append(_play_event(payload, track_id))
            except (KeyError, TypeError, ValueError):
                skipped += 1
        if events:
            received += _append_remote(context, store, events)
        cursor = page.next
        _set_cursor(store, PLAY_PULL_CURSOR, str(cursor))
        if not page.more:
            break
    if skipped:
        _log(
            store,
            f"{skipped} play events of other devices were skipped: their tracks are not on this "
            "computer.",
        )
    return received


def _play_event(payload: dict[str, Any], track_id: str) -> PlayLogEvent:
    artist = payload.get("artist")
    if not isinstance(artist, str):
        artists = payload.get("artists")
        artist = "; ".join(str(part) for part in artists) if isinstance(artists, list) else ""
    return PlayLogEvent(
        event_id=str(payload["event_id"]),
        device_id=str(payload["device_id"]),
        track_id=track_id,
        started_at=datetime.fromisoformat(str(payload["started_at"])),
        ended_at=datetime.fromisoformat(str(payload["ended_at"])),
        heard_ms=int(payload["heard_ms"]),
        counted=bool(payload["counted"]),
        artist=artist,
        title=_text(payload.get("title")),
        album=_text(payload.get("album")),
        duration_us=_count(payload.get("duration_us")),
    )


def _append_remote(context: PluginContext, store: RemoteStore, events: list[PlayLogEvent]) -> int:
    """Append a batch; one invalid event refuses it all, so the events are tried one by one."""
    try:
        return int(context.play_log.append_remote(events))
    except ValueError:
        added = 0
        refused = 0
        for event in events:
            try:
                added += int(context.play_log.append_remote([event]))
            except ValueError:
                refused += 1
        if refused:
            _log(store, f"{refused} play events of other devices were refused.", "warning")
        return added


# -- track data ----------------------------------------------------------------------------------
def digest_of(value: Any) -> str:
    """The SHA-256 of the canonical JSON of a layer."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _layer_values(context: PluginContext, track_id: str) -> dict[str, Any]:
    """The layers of a track that hold data, as the JSON the server keeps."""
    data = context.track_data.read(track_id)
    values: dict[str, Any] = {}
    if data.analysis is not None:
        values["analysis"] = dataclasses.asdict(data.analysis)
    if data.loudness is not None:
        values["loudness"] = dataclasses.asdict(data.loudness)
    if data.corrections:
        values["corrections"] = [
            {"credit_text": correction.credit_text, "mode": correction.mode}
            for correction in data.corrections
        ]
    return values


def _stored_digests(store: RemoteStore, item_id: str) -> dict[str, str]:
    rows = (
        store.connection()
        .execute("SELECT layer, digest FROM remote_track_data_sync WHERE item_id = ?", (item_id,))
        .fetchall()
    )
    return {str(row["layer"]): str(row["digest"]) for row in rows}


def _store_digests(store: RemoteStore, item_id: str, digests: Mapping[str, str]) -> None:
    with store.transaction() as conn:
        for layer, digest in digests.items():
            conn.execute(
                "INSERT INTO remote_track_data_sync (item_id, layer, digest) VALUES (?, ?, ?)"
                " ON CONFLICT (item_id, layer) DO UPDATE SET digest = excluded.digest",
                (item_id, layer, digest),
            )


def _write_layer(context: PluginContext, track_id: str, layer: str, value: Any) -> None:
    """Store one received layer through the core, which keeps its own rules (an edited key wins)."""
    if layer == "analysis":
        context.track_data.write_analysis(track_id, _analysis_of(value))
    elif layer == "loudness":
        context.track_data.write_loudness(track_id, _loudness_of(value))
    elif layer == "corrections":
        if not isinstance(value, list):
            raise ValueError("The corrections layer is not a list.")
        corrections = [
            CreditCorrection(credit_text=str(entry["credit_text"]), mode=str(entry["mode"]))
            for entry in value
            if isinstance(entry, dict)
        ]
        context.track_data.write_corrections(track_id, corrections)


def _analysis_of(value: Any) -> TrackAnalysisData:
    if not isinstance(value, dict):
        raise ValueError("The analysis layer is not an object.")
    names = {field.name for field in dataclasses.fields(TrackAnalysisData)}
    return TrackAnalysisData(**{key: item for key, item in value.items() if key in names})


def _loudness_of(value: Any) -> TrackLoudnessData:
    if not isinstance(value, dict):
        raise ValueError("The loudness layer is not an object.")
    names = {field.name for field in dataclasses.fields(TrackLoudnessData)}
    return TrackLoudnessData(**{key: item for key, item in value.items() if key in names})


def _receive_layer(
    context: PluginContext,
    store: RemoteStore,
    item_id: str,
    track_id: str,
    layer: str,
    value: Any,
) -> None:
    """Write a received layer, then remember the digest of what the core now holds (no echo)."""
    incoming = digest_of(value)
    _write_layer(context, track_id, layer, value)
    current = _layer_values(context, track_id).get(layer)
    _store_digests(store, item_id, {layer: incoming if current is None else digest_of(current)})


def push_track_data(context: PluginContext, store: RemoteStore, client: RemoteClient) -> int:
    """Send the layers of the linked tracks that changed; return how many items were sent.

    A layer this device has never sent is first compared with the server: where the server already
    holds it, the server's layer is received instead, so a first sync never overwrites it.
    """
    sent = 0
    links = store.connection().execute("SELECT item_id, track_id FROM remote_links").fetchall()
    for row in links:
        item_id = str(row["item_id"])
        track_id = str(row["track_id"])
        values = _layer_values(context, track_id)
        if not values:
            continue
        stored = _stored_digests(store, item_id)
        unseen = [layer for layer in values if layer not in stored]
        refused: set[str] = set()
        if unseen:
            try:
                server_layers = client.track_data(item_id)
            except ApiError as error:
                if error.status == 404:
                    continue
                raise
            for layer in unseen:
                if layer not in server_layers:
                    continue
                try:
                    _receive_layer(context, store, item_id, track_id, layer, server_layers[layer])
                except (ValueError, LookupError, KeyError, TypeError) as error:
                    # The server's layer was not applied: the local one must not replace it.
                    refused.add(layer)
                    _log(store, f"A {layer} of another device was not applied: {error}", "warning")
            values = _layer_values(context, track_id)
            stored = _stored_digests(store, item_id)
        changed = {
            layer: value
            for layer, value in values.items()
            if layer not in refused and stored.get(layer) != digest_of(value)
        }
        if not changed:
            continue
        client.put_track_data(item_id, changed)
        _store_digests(
            store, item_id, {layer: digest_of(value) for layer, value in changed.items()}
        )
        sent += 1
    return sent


def pull_track_data(
    context: PluginContext, store: RemoteStore, client: RemoteClient, item_id: str
) -> int:
    """Receive the layers of one item for its local track; return how many were written."""
    track_id = track_of_item(store, item_id)
    if track_id is None:
        return 0
    try:
        layers = client.track_data(item_id)
    except ApiError as error:
        if error.status == 404:
            return 0
        raise
    stored = _stored_digests(store, item_id)
    written = 0
    for layer in LAYERS:
        if layer not in layers or stored.get(layer) == digest_of(layers[layer]):
            continue
        try:
            _receive_layer(context, store, item_id, track_id, layer, layers[layer])
        except (ValueError, LookupError, KeyError, TypeError) as error:
            _log(store, f"A {layer} of another device was not applied: {error}", "warning")
            continue
        written += 1
    return written


# -- synced settings -------------------------------------------------------------------------
def setting_label(key: str) -> str:
    return SETTING_LABELS.get(key, key)


def enabled_keys(context: PluginContext) -> list[str]:
    """The synced settings this device sends and receives: all of them, unless switched off."""
    allowed = sorted(context.synced_settings.keys)
    chosen = context.settings.get_json(SYNCED_KEYS_SETTING, None)
    if not isinstance(chosen, list):
        return allowed
    return [key for key in allowed if key in chosen]


def travel_rows(context: PluginContext) -> list[dict[str, Any]]:
    """One row per synced setting for the Settings page: its key, its label and its switch."""
    enabled = set(enabled_keys(context))
    keys = sorted(context.synced_settings.keys, key=setting_label)
    return [{"key": key, "label": setting_label(key), "enabled": key in enabled} for key in keys]


def set_travel(context: PluginContext, key: str, value: bool) -> None:
    """Switch one synced setting on or off; ``ValueError`` for a key that may not travel."""
    if key not in context.synced_settings.keys:
        raise ValueError(f"{key} cannot travel between devices.")
    chosen = set(enabled_keys(context))
    if value:
        chosen.add(key)
    else:
        chosen.discard(key)
    context.settings.set_json(SYNCED_KEYS_SETTING, sorted(chosen))


def _as_text(value: Any) -> str:
    """A setting as the core stores it: plain text, or the JSON text of the value."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _apply_settings(
    context: PluginContext, store: RemoteStore, values: Mapping[str, str]
) -> dict[str, str]:
    """Write the received settings one by one; return the ones the core accepted."""
    applied: dict[str, str] = {}
    for key, text in values.items():
        try:
            context.synced_settings.write({key: text})
        except (SettingNotSyncedError, ValueError) as error:
            _log(
                store,
                f"The setting {setting_label(key)} of another device was not applied: {error}",
                "warning",
            )
            continue
        applied[key] = text
    return applied


def pull_settings(context: PluginContext, store: RemoteStore, client: RemoteClient) -> int:
    """Apply the synced settings the server changed since this device last sent or received them.

    A key the server still holds as this device last left it is not applied, so a local change that
    has not been sent yet is never undone by the echo of this device's own push.
    """
    server = client.records_settings()
    sent = _dict_setting(context, SETTINGS_SENT_SETTING)
    incoming = {key: _as_text(server[key]) for key in enabled_keys(context) if key in server}
    changed = {key: text for key, text in incoming.items() if sent.get(key) != text}
    applied = _apply_settings(context, store, changed)
    sent.update(applied)
    context.settings.set_json(SETTINGS_SENT_SETTING, sent)
    return len(applied)


def push_settings(context: PluginContext, store: RemoteStore, client: RemoteClient) -> int:
    """Send the enabled synced settings whose value differs from the last one sent or received."""
    current = context.synced_settings.read()
    sent = _dict_setting(context, SETTINGS_SENT_SETTING)
    unseen = [key for key in enabled_keys(context) if key in current and key not in sent]
    if unseen:
        # First contact with a key: the server's value comes first, so a new device keeps it.
        pull_settings(context, store, client)
        sent = _dict_setting(context, SETTINGS_SENT_SETTING)
        current = context.synced_settings.read()
    changed = {
        key: current[key]
        for key in enabled_keys(context)
        if key in current and sent.get(key) != current[key]
    }
    if not changed:
        return 0
    client.put_records_settings(changed)
    sent.update(changed)
    context.settings.set_json(SETTINGS_SENT_SETTING, sent)
    return len(changed)


# -- playlists -----------------------------------------------------------------------------------
def _local_playlist_ids(context: PluginContext) -> list[str]:
    """The identifiers of the local playlists.

    The playlist service has no listing, so this reads the core's ``playlists`` table (read only).
    """
    rows = (
        context.database.connection()
        .execute("SELECT playlist_id FROM playlists ORDER BY playlist_id")
        .fetchall()
    )
    return [str(row[0]) for row in rows]


def _links(store: RemoteStore) -> dict[str, PlaylistLink]:
    rows = store.connection().execute("SELECT * FROM remote_playlists").fetchall()
    return {
        str(row["local_playlist_id"]): PlaylistLink(
            str(row["local_playlist_id"]),
            str(row["server_playlist_id"]),
            _count(row["synced_local_revision"]),
            _count(row["synced_server_revision"]),
        )
        for row in rows
    }


def _set_link(store: RemoteStore, link: PlaylistLink) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO remote_playlists (local_playlist_id, server_playlist_id,"
            " synced_local_revision, synced_server_revision, synced_at_utc)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (local_playlist_id) DO UPDATE SET"
            " server_playlist_id = excluded.server_playlist_id,"
            " synced_local_revision = excluded.synced_local_revision,"
            " synced_server_revision = excluded.synced_server_revision,"
            " synced_at_utc = excluded.synced_at_utc",
            (
                link.local_playlist_id,
                link.server_playlist_id,
                link.synced_local_revision,
                link.synced_server_revision,
                utc_now(),
            ),
        )


def _drop_link(store: RemoteStore, local_playlist_id: str) -> None:
    with store.transaction() as conn:
        conn.execute(
            "DELETE FROM remote_playlists WHERE local_playlist_id = ?", (local_playlist_id,)
        )


def _local_entries(
    context: PluginContext, store: RemoteStore, local_playlist_id: str
) -> tuple[list[dict[str, str]], int]:
    """The entries of a local playlist as items, and how many of them are not on the server."""
    items: list[dict[str, str]] = []
    missing = 0
    for entry in context.playlists.entries(local_playlist_id):
        item_id = item_of_track(store, entry.track_id) if entry.track_id else None
        if item_id is None:
            missing += 1
            continue
        items.append({"item_id": item_id, "title": entry.title, "artist": entry.artist})
    return items, missing


def _server_tracks(store: RemoteStore, entries: list[Any]) -> tuple[list[str], int]:
    """The local tracks of the entries of a server playlist, and how many of them are not here."""
    tracks: list[str] = []
    missing = 0
    for entry in entries:
        item_id = entry.get("item_id") if isinstance(entry, dict) else None
        track_id = track_of_item(store, item_id) if isinstance(item_id, str) else None
        if track_id is None:
            missing += 1
        elif track_id not in tracks:
            tracks.append(track_id)
    return tracks, missing


def _server_items(entries: list[Any]) -> list[dict[str, str]]:
    """The entries of a server playlist, as they are sent back to the server."""
    items: list[dict[str, str]] = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("item_id"), str):
            items.append(
                {
                    "item_id": entry["item_id"],
                    "title": _text(entry.get("title")),
                    "artist": _text(entry.get("artist")),
                }
            )
    return items


def _open_playlist_conflicts(store: RemoteStore) -> set[str]:
    """The local playlists that have an open conflict (they wait for the person)."""
    rows = (
        store.connection()
        .execute("SELECT local_json FROM remote_conflicts WHERE state <> 'resolved'")
        .fetchall()
    )
    found: set[str] = set()
    for row in rows:
        data = _load_json(row["local_json"])
        if data.get("kind") == KIND_PLAYLIST and isinstance(data.get("local_playlist_id"), str):
            found.add(str(data["local_playlist_id"]))
    return found


def _not_synced(name: str, count: int, where: str) -> str:
    noun = "track is" if count == 1 else "tracks are"
    return f"{name} is not synced: {count} {noun} not on {where}."


def sync_playlists(context: PluginContext, store: RemoteStore, client: RemoteClient) -> int:
    """Bring the playlists of both sides together; return how many changed in this pass.

    Each linked playlist is compared with the revisions both sides had when they last agreed
    (``remote_playlists``). A change on one side is sent or applied; a change on both sides becomes
    a conflict row. A local playlist without a link is created on the server, and a server playlist
    without a link is created here when all its tracks are here. A deleted server copy is not
    applied
    here (there is no delete on this side): the local playlist stays and is never sent again.
    """
    changed = 0
    server = {
        str(meta["playlist_id"]): meta for meta in client.playlists() if "playlist_id" in meta
    }
    links = _links(store)
    local_ids = set(_local_playlist_ids(context))
    retired = _list_setting(context, RETIRED_PLAYLISTS_SETTING)
    open_conflicts = _open_playlist_conflicts(store)
    for local_id, link in sorted(links.items()):
        if local_id in open_conflicts:
            continue
        with _guarded(store, f"The playlist {local_id}"):
            changed += _sync_linked(
                context,
                store,
                client,
                link,
                server.get(link.server_playlist_id),
                local_id in local_ids,
                retired,
                open_conflicts,
            )
    linked_now = _links(store)
    for local_id in sorted(local_ids):
        if local_id in linked_now or local_id in retired or local_id in open_conflicts:
            continue
        with _guarded(store, f"The playlist {local_id}"):
            changed += _push_new(context, store, client, local_id)
    linked_servers = {link.server_playlist_id for link in linked_now.values()}
    for playlist_id, meta in server.items():
        if playlist_id in linked_servers or meta.get("deleted"):
            continue
        with _guarded(store, f"The server playlist {playlist_id}"):
            changed += _pull_new(context, store, client, meta)
    return changed


def _sync_linked(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    link: PlaylistLink,
    meta: dict[str, Any] | None,
    exists_here: bool,
    retired: list[str],
    open_conflicts: set[str],
) -> int:
    if not exists_here:
        return _delete_on_server(store, client, link, meta)
    if meta is None or meta.get("deleted"):
        name = context.playlists.name(link.local_playlist_id) or link.local_playlist_id
        _drop_link(store, link.local_playlist_id)
        if link.local_playlist_id not in retired:
            retired.append(link.local_playlist_id)
            context.settings.set_json(RETIRED_PLAYLISTS_SETTING, retired)
        _log(store, f"{name} was deleted on the server; it stays on this computer.")
        return 0
    return _sync_one(context, store, client, link, meta, open_conflicts)


def _delete_on_server(
    store: RemoteStore,
    client: RemoteClient,
    link: PlaylistLink,
    meta: dict[str, Any] | None,
) -> int:
    """A local playlist that is gone: its server copy is deleted too, with its revision checked."""
    if meta is None or meta.get("deleted"):
        _drop_link(store, link.local_playlist_id)
        return 0
    name = _text(meta.get("name")) or link.local_playlist_id
    try:
        client.delete_playlist(link.server_playlist_id, base_revision=_count(meta.get("revision")))
    except ApiError as error:
        if error.status != 409:
            raise
        _log(
            store,
            f"{name} changed on the server; its deletion is sent again in a later pass.",
            "warning",
        )
        return 0
    _drop_link(store, link.local_playlist_id)
    _log(store, f"{name} was deleted here, so it is deleted on the server too.")
    return 1


def _sync_one(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    link: PlaylistLink,
    meta: dict[str, Any],
    open_conflicts: set[str],
) -> int:
    local_id = link.local_playlist_id
    server_id = link.server_playlist_id
    local_rev = context.playlists.revision(local_id)
    if local_rev is None:
        return 0
    server_rev = _count(meta.get("revision"))
    local_changed = local_rev > link.synced_local_revision
    server_changed = server_rev > link.synced_server_revision
    if not local_changed and not server_changed:
        return 0
    name = context.playlists.name(local_id) or local_id
    if local_changed:
        entries, missing = _local_entries(context, store, local_id)
        if missing:
            _skip_once(
                context,
                store,
                f"local:{local_id}",
                local_rev,
                _not_synced(name, missing, "the server"),
            )
            return 0
        if server_changed:
            _open_conflict(store, link, name, local_rev, entries, client.playlist(server_id))
            open_conflicts.add(local_id)
            return 0
        try:
            sent = client.put_playlist(server_id, name, entries, base_revision=server_rev)
        except ApiError as error:
            if error.status != 409:
                raise
            # The server moved on since the revision this device had: both sides changed.
            _open_conflict(store, link, name, local_rev, entries, client.playlist(server_id))
            open_conflicts.add(local_id)
            return 0
        _set_link(store, PlaylistLink(local_id, server_id, local_rev, _count(sent.get("revision"))))
        return 1
    full = client.playlist(server_id)
    tracks, missing = _server_tracks(store, full.get("entries") or [])
    if missing:
        _skip_once(
            context,
            store,
            f"server:{server_id}",
            server_rev,
            _not_synced(name, missing, "this computer"),
        )
        return 0
    try:
        new_rev = context.playlists.replace_entries(local_id, tracks, expected_revision=local_rev)
    except StaleRevisionError:
        return 0  # the playlist moved here meanwhile: the next pass sees both changes
    _set_link(store, PlaylistLink(local_id, server_id, new_rev, _count(full.get("revision"))))
    server_name = _text(full.get("name"))
    if server_name and server_name != name:
        _log(store, f"Renamed on the server to {server_name}; the name here is kept.", "warning")
    return 1


def _open_conflict(
    store: RemoteStore,
    link: PlaylistLink,
    name: str,
    local_rev: int,
    entries: list[dict[str, str]],
    full: dict[str, Any],
) -> None:
    """Record a playlist changed on both sides; both track lists are kept in the row."""
    local_view = {
        "kind": KIND_PLAYLIST,
        "local_playlist_id": link.local_playlist_id,
        "server_playlist_id": link.server_playlist_id,
        "name": name,
        "relative_path": name,
        "revision": local_rev,
        "entries": entries,
    }
    server_view = {
        "kind": KIND_PLAYLIST,
        "local_playlist_id": link.local_playlist_id,
        "server_playlist_id": link.server_playlist_id,
        "name": _text(full.get("name")) or name,
        "relative_path": name,
        "revision": _count(full.get("revision")),
        "entries": _server_items(full.get("entries") or []),
    }
    with store.transaction() as conn:
        insert_conflict(
            conn,
            track_id=None,
            item_id=None,
            local=local_view,
            server=server_view,
            state=CONFLICT_OPEN,
        )
        write_log(conn, f"{name} changed on this computer and on the server.", "warning")


def _push_new(
    context: PluginContext, store: RemoteStore, client: RemoteClient, local_id: str
) -> int:
    """A local playlist without a server copy: it is created on the server under a new id."""
    revision = context.playlists.revision(local_id)
    if revision is None:
        return 0
    name = context.playlists.name(local_id) or local_id
    entries, missing = _local_entries(context, store, local_id)
    if missing:
        _skip_once(
            context, store, f"local:{local_id}", revision, _not_synced(name, missing, "the server")
        )
        return 0
    server_id = uuid.uuid4().hex
    sent = client.put_playlist(server_id, name, entries, base_revision=None)
    _set_link(store, PlaylistLink(local_id, server_id, revision, _count(sent.get("revision"))))
    return 1


def _pull_new(
    context: PluginContext, store: RemoteStore, client: RemoteClient, meta: dict[str, Any]
) -> int:
    """A server playlist without a local copy: it is created here, when all its tracks are here."""
    server_id = str(meta["playlist_id"])
    full = client.playlist(server_id)
    name = _text(full.get("name")) or server_id
    tracks, missing = _server_tracks(store, full.get("entries") or [])
    if missing:
        _skip_once(
            context,
            store,
            f"server:{server_id}",
            _count(full.get("revision")),
            _not_synced(name, missing, "this computer"),
        )
        return 0
    local_id = context.playlists.create(name, tracks)
    revision = context.playlists.revision(local_id) or 1
    _set_link(store, PlaylistLink(local_id, server_id, revision, _count(full.get("revision"))))
    _log(store, f"New playlist from the server: {name}.")
    return 1


def resolve_playlist_conflict(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    local: Mapping[str, Any],
    action: str,
) -> str:
    """Carry out one choice on a playlist changed on both sides; return the sentence for the person.

    ``PlaylistObsoleteError`` when a side no longer has the playlist;
    ``PlaylistRefusedError`` when the choice cannot be carried out now (nothing was changed, and
    the conflict stays open).
    """
    local_id = _text(local.get("local_playlist_id"))
    link = _links(store).get(local_id)
    if link is None:
        raise PlaylistObsoleteError("This playlist is no longer linked to its server copy.")
    name = context.playlists.name(local_id)
    if name is None:
        raise PlaylistObsoleteError("This playlist no longer exists on this computer.")
    try:
        full = client.playlist(link.server_playlist_id)
    except ApiError as error:
        if error.status == 404:
            raise PlaylistObsoleteError("The playlist is no longer on the server.") from error
        raise
    if full.get("deleted"):
        raise PlaylistObsoleteError("The playlist was deleted on the server.")
    server_rev = _count(full.get("revision"))
    local_rev = context.playlists.revision(local_id) or 0
    if action == KEEP_LOCAL:
        return _keep_local(context, store, client, link, name, local_rev, server_rev)
    if action == KEEP_SERVER:
        return _keep_server(context, store, link, name, local_rev, server_rev, full)
    if action == KEEP_BOTH:
        return _keep_both(context, store, client, link, name, local_rev, server_rev, full)
    raise PlaylistRefusedError("This choice does not apply to this conflict.")


def _keep_local(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    link: PlaylistLink,
    name: str,
    local_rev: int,
    server_rev: int,
) -> str:
    entries, missing = _local_entries(context, store, link.local_playlist_id)
    if missing:
        raise PlaylistRefusedError(
            _not_synced(name, missing, "the server") + " Nothing was changed."
        )
    try:
        sent = client.put_playlist(link.server_playlist_id, name, entries, base_revision=server_rev)
    except ApiError as error:
        if error.status == 409:
            raise PlaylistRefusedError(
                "The server copy changed again. Nothing was changed."
            ) from error
        raise
    _set_link(
        store,
        PlaylistLink(
            link.local_playlist_id,
            link.server_playlist_id,
            local_rev,
            _count(sent.get("revision")),
        ),
    )
    return "The server's copy now has this computer's tracks."


def _keep_server(
    context: PluginContext,
    store: RemoteStore,
    link: PlaylistLink,
    name: str,
    local_rev: int,
    server_rev: int,
    full: dict[str, Any],
) -> str:
    tracks, missing = _server_tracks(store, full.get("entries") or [])
    if missing:
        raise PlaylistRefusedError(
            _not_synced(name, missing, "this computer") + " Nothing was changed."
        )
    try:
        new_rev = context.playlists.replace_entries(
            link.local_playlist_id, tracks, expected_revision=local_rev
        )
    except StaleRevisionError as error:
        raise PlaylistRefusedError(
            "This playlist changed here again. Nothing was changed."
        ) from error
    _set_link(
        store,
        PlaylistLink(link.local_playlist_id, link.server_playlist_id, new_rev, server_rev),
    )
    return "This computer's playlist now has the server's tracks."


def _keep_both(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    link: PlaylistLink,
    name: str,
    local_rev: int,
    server_rev: int,
    full: dict[str, Any],
) -> str:
    local_entries, local_missing = _local_entries(context, store, link.local_playlist_id)
    server_tracks, server_missing = _server_tracks(store, full.get("entries") or [])
    if local_missing or server_missing:
        raise PlaylistRefusedError("Some tracks are not on both sides. Nothing was changed.")
    copy_name = f"{name} (server)"
    # The server's version becomes a local copy and is sent as a new playlist first, so nothing is
    # lost if the replacement of the server copy below fails.
    copy_id = context.playlists.create(copy_name, server_tracks)
    copy_server_id = uuid.uuid4().hex
    copy_sent = client.put_playlist(
        copy_server_id, copy_name, _server_items(full.get("entries") or []), base_revision=None
    )
    _set_link(
        store,
        PlaylistLink(
            copy_id,
            copy_server_id,
            context.playlists.revision(copy_id) or 1,
            _count(copy_sent.get("revision")),
        ),
    )
    try:
        sent = client.put_playlist(
            link.server_playlist_id, name, local_entries, base_revision=server_rev
        )
    except ApiError as error:
        if error.status == 409:
            raise PlaylistRefusedError(
                f'The server copy changed again. "{copy_name}" was made; the server is unchanged.'
            ) from error
        raise
    _set_link(
        store,
        PlaylistLink(
            link.local_playlist_id,
            link.server_playlist_id,
            local_rev,
            _count(sent.get("revision")),
        ),
    )
    return (
        f"This computer's \"{name}\" is on the server, and the server's version is kept "
        f'as "{copy_name}".'
    )


# -- one pass ------------------------------------------------------------------------------------
def push_records(context: PluginContext, store: RemoteStore, client: RemoteClient) -> None:
    """The records push of a pass: play log, playlists, track data and settings, in turn."""
    with _guarded(store, "The play log"):
        push_play_events(context, store, client)
    with _guarded(store, "The playlists"):
        sync_playlists(context, store, client)
    with _guarded(store, "The track data"):
        push_track_data(context, store, client)
    with _guarded(store, "The synced settings"):
        push_settings(context, store, client)


def pull_records(
    context: PluginContext,
    store: RemoteStore,
    client: RemoteClient,
    *,
    kinds: set[str],
    items: set[str],
) -> None:
    """The records pull of a fetch: what the journal reported, in the same order."""
    if "play_events" in kinds:
        with _guarded(store, "The play log"):
            pull_play_events(context, store, client)
    if "playlist" in kinds:
        with _guarded(store, "The playlists"):
            sync_playlists(context, store, client)
    for item_id in sorted(items):
        with _guarded(store, "The track data"):
            pull_track_data(context, store, client, item_id)
    if "settings" in kinds:
        with _guarded(store, "The synced settings"):
            pull_settings(context, store, client)

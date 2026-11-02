"""Core store of the tracks that plugins provide without a file (table ``plugin_source_tracks``).

Each such track has a normal row in ``tracks`` (a per-machine UUID). This repository keeps the
mapping ``(plugin_id, source_key) -> track_id`` and the display metadata. It never touches
``track_locations`` or ``root_tracks``: a track without a file is not part of any library folder.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.source_tracks import SourceTrack, SourceTrackEntry
from mtee.domain.tracks import TrackId
from mtee.persistence.database import Database

__all__ = ["SourceTrackRepository"]


class SourceTrackRepository:
    """Upsert, remove and list the tracks of one plugin; every call is idempotent."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def upsert(
        self, plugin_id: str, tracks: Sequence[SourceTrack]
    ) -> tuple[dict[str, str], list[str]]:
        """Store ``tracks`` and return ``({source_key: track_id}, changed track ids)``.

        A key that is already stored keeps its ``track_id``, also after ``remove``: the track
        becomes available again with the new metadata. Storing the same values twice changes
        nothing (the revision rises only when the metadata changed). One transaction: a track
        listed twice keeps its last version.
        """
        if not plugin_id:
            raise ValueError("A plugin identifier is required.")
        latest = {track.source_key: track for track in tracks}
        now = datetime.now(UTC).isoformat(timespec="seconds")
        identities: dict[str, str] = {}
        changed_ids: list[str] = []
        with self._database.transaction() as connection:
            for key, track in latest.items():
                encoded = json.dumps(track.snapshot().to_dict(), ensure_ascii=False, sort_keys=True)
                row = connection.execute(
                    "SELECT track_id,metadata_json,album_artist,available,revision "
                    "FROM plugin_source_tracks WHERE plugin_id=? AND source_key=?",
                    (plugin_id, key),
                ).fetchone()
                if row is None:
                    track_id = str(TrackId.new())
                    changed_ids.append(track_id)
                    connection.execute("INSERT INTO tracks(track_id) VALUES(?)", (track_id,))
                    connection.execute(
                        "INSERT INTO plugin_source_tracks(plugin_id,source_key,track_id,"
                        "metadata_json,album_artist,available,revision,updated_at_utc) "
                        "VALUES(?,?,?,?,?,1,0,?)",
                        (plugin_id, key, track_id, encoded, track.album_artist, now),
                    )
                else:
                    track_id = str(row["track_id"])
                    changed = (
                        str(row["metadata_json"]) != encoded
                        or str(row["album_artist"]) != track.album_artist
                    )
                    if changed or not row["available"]:
                        changed_ids.append(track_id)
                        connection.execute(
                            "UPDATE plugin_source_tracks SET metadata_json=?,album_artist=?,"
                            "available=1,revision=?,updated_at_utc=? "
                            "WHERE plugin_id=? AND source_key=?",
                            (
                                encoded,
                                track.album_artist,
                                int(row["revision"]) + (1 if changed else 0),
                                now,
                                plugin_id,
                                key,
                            ),
                        )
                identities[key] = track_id
        return identities, changed_ids

    def remove(self, plugin_id: str, source_keys: Iterable[str]) -> list[str]:
        """Make the tracks unavailable and return the ``track_id`` of those that changed.

        The row and its ``track_id`` stay, so playlist entries and play log rows survive. An
        unknown key, or a track already removed, is ignored.
        """
        changed: list[str] = []
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._database.transaction() as connection:
            for key in dict.fromkeys(source_keys):
                row = connection.execute(
                    "SELECT track_id FROM plugin_source_tracks "
                    "WHERE plugin_id=? AND source_key=? AND available=1",
                    (plugin_id, key),
                ).fetchone()
                if row is None:
                    continue
                connection.execute(
                    "UPDATE plugin_source_tracks SET available=0,updated_at_utc=? "
                    "WHERE plugin_id=? AND source_key=?",
                    (now, plugin_id, key),
                )
                changed.append(str(row["track_id"]))
        return changed

    def entries(self, plugin_id: str, *, available_only: bool = False) -> list[SourceTrackEntry]:
        """Return every track stored for the plugin, sorted by key."""
        rows = (
            self._database.connection()
            .execute(
                "SELECT source_key,track_id,metadata_json,album_artist,available "
                "FROM plugin_source_tracks WHERE plugin_id=? "
                + ("AND available=1 " if available_only else "")
                + "ORDER BY source_key",
                (plugin_id,),
            )
            .fetchall()
        )
        return [
            SourceTrackEntry(
                track_id=str(row["track_id"]),
                track=SourceTrack.from_snapshot(
                    str(row["source_key"]),
                    MetadataSnapshot.from_dict(json.loads(str(row["metadata_json"]))),
                    str(row["album_artist"]),
                ),
                available=bool(row["available"]),
            )
            for row in rows
        ]

    def origin(self, track_id: str) -> tuple[str, str] | None:
        """Return ``(plugin_id, source_key)`` of a track that has no file, else ``None``."""
        row = (
            self._database.connection()
            .execute(
                "SELECT plugin_id,source_key FROM plugin_source_tracks WHERE track_id=?",
                (track_id,),
            )
            .fetchone()
        )
        return (str(row["plugin_id"]), str(row["source_key"])) if row is not None else None

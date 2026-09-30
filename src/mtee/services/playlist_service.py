"""Playlist presentation and musical duplicate checks on local metadata."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from mtee.domain.playlists import LIKED_PLAYLIST_ID, musical_identity, portable_snapshot
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository


class AmbiguousPlaylistAddError(ValueError):
    def __init__(self, track_ids: list[str]) -> None:
        super().__init__(
            "Some tracks have incomplete title or artist tags. Confirm distinct songs."
        )
        self.track_ids = track_ids


class PlaylistService:
    def __init__(self, repository: PlaylistsRepository, library: LibraryRepository) -> None:
        self.repository = repository
        self.library = library
        self.lock = threading.RLock()

    def rows(self, identity: str) -> list[dict[str, Any]]:
        if identity == LIKED_PLAYLIST_ID:
            entries = [
                {"entry_id": "like:" + track_id, "track_id": track_id, "snapshot": {}}
                for track_id in self.repository.liked_ids()
            ]
        else:
            entries = self.repository.entries(identity)
        liked = set(self.repository.liked_ids())
        rows = []
        for entry in entries:
            track_id = entry["track_id"] or ""
            current = self.library.track(track_id) if track_id else {}
            available = bool(
                current
                and current.get("rootId")
                and current.get("status") == "readable"
                and Path(current["path"]).is_file()
            )
            row = dict(current or entry["snapshot"])
            row.update(
                {
                    "id": entry["entry_id"],
                    "entryId": entry["entry_id"],
                    "trackId": track_id,
                    "available": available,
                    "liked": track_id in liked,
                    "cover": row.get("cover", -1),
                    "artist": row.get("artist", ""),
                    "title": row.get("title", "Unavailable track"),
                    "key": row.get("key", ""),
                    "coverUrl": row.get("coverUrl", "") if available else "",
                }
            )
            rows.append(row)
        return rows

    def add(self, identity: str, track_ids: list[str], *, confirm_unknown: bool = False) -> int:
        with self.lock:
            playlist = self.repository.playlist(identity)
            existing = self.rows(identity)
            ids = {r["trackId"] for r in existing}
            musical = {key for r in existing if (key := musical_identity(r)) is not None}
            additions = []
            uncertain = []
            for track_id in dict.fromkeys(track_ids):
                track = self.library.track(track_id)
                if not track:
                    raise LookupError("A selected track is no longer in the library.")
                source = self.library.source_record(track_id)
                if source is not None and not source.snapshot.title:
                    track["identityUncertain"] = True
                key = musical_identity(track)
                if track_id in ids or (key is not None and key in musical):
                    continue
                if key is None and (existing or additions) and not confirm_unknown:
                    uncertain.append(track_id)
                additions.append({"track_id": track_id, "snapshot": portable_snapshot(track)})
                ids.add(track_id)
                if key is not None:
                    musical.add(key)
            if uncertain:
                raise AmbiguousPlaylistAddError(track_ids)
            if additions:
                self.repository.add_entries(identity, additions, playlist["version"])
            return len(additions)

    def memberships(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        music: dict[Any, set[str]] = {}
        for playlist in self.repository.playlists():
            identity = playlist["playlist_id"]
            for row in self.rows(identity):
                if row["trackId"]:
                    result.setdefault(row["trackId"], []).append(identity)
                key = musical_identity(row)
                if key is not None:
                    music.setdefault(key, set()).add(identity)
        for row in self.repository.database.connection().execute(
            "SELECT track_id,metadata_json FROM track_locations"
        ):
            tags = json.loads(row["metadata_json"])
            title = tags.get("title", [])
            artist = tags.get("artist", [])
            key = musical_identity(
                {"title": title[0] if title else "", "artist": ", ".join(artist)}
            )
            if key is not None and key in music:
                result[row["track_id"]] = sorted(set(result.get(row["track_id"], [])) | music[key])
        return result

    def toggle(self, identity: str, track_ids: list[str], *, confirm_unknown: bool = False) -> None:
        with self.lock:
            entries = self.rows(identity)
            selected = set(track_ids)
            keys = {
                key
                for track_id in selected
                if (key := musical_identity(self.library.track(track_id))) is not None
            }
            matching = [
                e
                for e in entries
                if e["trackId"] in selected
                or (musical_identity(e) is not None and musical_identity(e) in keys)
            ]
            represented = {e["trackId"] for e in matching}
            represented_keys = {musical_identity(e) for e in matching}
            if selected and all(
                track_id in represented
                or (
                    musical_identity(self.library.track(track_id)) is not None
                    and musical_identity(self.library.track(track_id)) in represented_keys
                )
                for track_id in selected
            ):
                self.repository.remove(identity, [e["entryId"] for e in matching])
            else:
                self.add(identity, track_ids, confirm_unknown=confirm_unknown)

    def liked_aliases(self) -> list[str]:
        liked = set(self.repository.liked_ids())
        keys = {
            key
            for identity in liked
            if (key := musical_identity(self.library.track(identity))) is not None
        }
        for row in self.repository.database.connection().execute(
            "SELECT track_id,metadata_json FROM track_locations"
        ):
            tags = json.loads(row["metadata_json"])
            title = tags.get("title", [])
            artist = tags.get("artist", [])
            key = musical_identity(
                {"title": title[0] if title else "", "artist": ", ".join(artist)}
            )
            if key is not None and key in keys:
                liked.add(row["track_id"])
        return sorted(liked)

    def toggle_like(self, track_id: str) -> None:
        with self.lock:
            liked = self.repository.liked_ids()
            key = musical_identity(self.library.track(track_id))
            matching = [
                identity
                for identity in liked
                if identity == track_id
                or (key is not None and musical_identity(self.library.track(identity)) == key)
            ]
            if matching:
                for identity in matching:
                    self.repository.like(identity, False)
            else:
                self.repository.like(track_id, True)

    def resolve(self, identity: str, entry_id: str, track_id: str) -> None:
        with self.lock:
            track = self.library.track(track_id)
            if not track:
                raise LookupError("Choose a track from the local library.")
            key = musical_identity(track)
            for row in self.rows(identity):
                if row["entryId"] != entry_id and (
                    row["trackId"] == track_id or (key is not None and musical_identity(row) == key)
                ):
                    raise ValueError("This song is already in the playlist.")
            self.repository.resolve(
                identity,
                entry_id,
                track_id,
                portable_snapshot(track),
                self.repository.playlist(identity)["version"],
            )

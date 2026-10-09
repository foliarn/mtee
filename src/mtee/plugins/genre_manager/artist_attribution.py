"""Conservative genre contributions from reviewed tracks to confirmed artists."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mtee.persistence.database import Database
from mtee.plugins.genre_manager.repository import _now

RULES_VERSION = 1
_VERSION = re.compile(r"\b(remix|flip|bootleg)\b", re.IGNORECASE)
_ORIGINAL = re.compile(r"\boriginal\s+(mix|version)\b", re.IGNORECASE)
_NAMED_VERSION = re.compile(
    r"(?:\(|\[|\s-\s)([^()\[\]]+?)\s+(?:remix|flip|bootleg)\b", re.IGNORECASE
)


def _signature(title: str, credits: list[dict[str, str]]) -> str:
    payload = [title, [[row["id"], row["name"], row["role"]] for row in credits]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def choose_artists(
    title: str, credits: list[dict[str, str]], manual: Sequence[str] | None = None
) -> tuple[list[str], str]:
    """Return contributor IDs or an abstention reason; never create an artist identity."""
    if not credits:
        return [], "No confirmed artist credits"
    identifiers = {row["id"] for row in credits}
    if manual is not None:
        if not manual or not set(manual) <= identifiers:
            return [], "The explicit choice no longer matches the credits"
        return list(dict.fromkeys(manual)), ""
    remixers = [row["id"] for row in credits if row["role"] == "remixer"]
    titled_version = bool(_VERSION.search(title))
    named = _NAMED_VERSION.search(title)
    if named:
        named_key = named.group(1).strip().casefold()
        matches = [row["id"] for row in credits if row["name"].casefold() == named_key]
        if len(matches) != 1:
            return [], "Version name is absent from or ambiguous in confirmed credits"
        if remixers and matches[0] not in remixers:
            return [], "Title and confirmed remixer role disagree"
        return remixers or matches, ""
    if remixers:
        if _ORIGINAL.search(title):
            return [], "Original label conflicts with confirmed remixer credits"
        return remixers, ""
    if titled_version:
        return [], "Remix, Flip or Bootleg without an identified remixer"
    if _ORIGINAL.search(title):
        return [row["id"] for row in credits if row["role"] == "artist"], ""
    return [], "Version is not established from title and confirmed roles"


class ArtistAttribution:
    """Keep calculated contributions apart from artist profile tags and manual edits."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def _credits(self, track_id: str) -> list[dict[str, str]]:
        return [
            {
                "id": str(row["artist_id"]),
                "name": str(row["display_name"]),
                "role": str(row["role"]),
            }
            for row in self._database.connection().execute(
                "SELECT c.artist_id,a.display_name,c.role FROM track_artist_credits c "
                "JOIN artists a ON a.artist_id=c.artist_id "
                "WHERE c.track_id=? AND c.confirmed=1 ORDER BY c.position",
                (track_id,),
            )
        ]

    def _title(self, track_id: str) -> str:
        row = (
            self._database.connection()
            .execute(
                "SELECT COALESCE(NULLIF(confirmed_title,''),NULLIF(proposed_title,''),"
                "NULLIF(original_title,''),'') FROM track_artist_review WHERE track_id=?",
                (track_id,),
            )
            .fetchone()
        )
        if row and row[0]:
            return str(row[0])
        location = (
            self._database.connection()
            .execute(
                "SELECT path,metadata_json FROM track_locations WHERE track_id=?",
                (track_id,),
            )
            .fetchone()
        )
        if location is not None:
            metadata = json.loads(str(location["metadata_json"]))
            titles = metadata.get("title") or []
            if titles:
                return str(titles[0])
            return Path(str(location["path"])).stem
        return ""

    def refresh(self, track_ids: Sequence[str] | None = None) -> int:
        """Reconcile reviewed assignments; stale/removed reviews lose contributions."""
        connection = self._database.connection()
        if track_ids is None:
            track_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT track_id FROM gm_track_state UNION "
                    "SELECT track_id FROM gm_artist_contributions UNION "
                    "SELECT track_id FROM gm_artist_uncertainties"
                )
            ]
        changed = 0
        for track_id in dict.fromkeys(track_ids):
            title = ""
            state = connection.execute(
                "SELECT genre_revision,reviewed_revision FROM gm_track_state WHERE track_id=?",
                (track_id,),
            ).fetchone()
            genres = [
                str(row[0])
                for row in connection.execute(
                    "SELECT genre_id FROM gm_track_genres WHERE track_id=? ORDER BY position",
                    (track_id,),
                )
            ]
            contributions: list[tuple[str, str, str]] = []
            uncertainties: list[tuple[str, str]] = []
            if state is not None and state["genre_revision"] == state["reviewed_revision"]:
                title = self._title(track_id)
                credits = self._credits(track_id)
                signature = _signature(title, credits)
                decision = connection.execute(
                    "SELECT credit_signature,artist_ids_json FROM gm_artist_decisions "
                    "WHERE track_id=?",
                    (track_id,),
                ).fetchone()
                manual: list[str] | None = None
                if decision is not None and decision["credit_signature"] == signature:
                    manual = list(json.loads(str(decision["artist_ids_json"])))
                artists, reason = choose_artists(title, credits, manual)
                if decision is not None and decision["credit_signature"] != signature:
                    artists, reason = [], "Confirmed credits or title changed; review attribution"
                if artists:
                    source = "manual" if manual is not None else "rule"
                    contributions = [
                        (artist_id, genre_id, source)
                        for artist_id in artists
                        for genre_id in genres
                    ]
                else:
                    uncertainties = [(genre_id, reason) for genre_id in genres]
            with self._database.transaction() as transaction:
                transaction.execute(
                    "DELETE FROM gm_artist_contributions WHERE track_id=?", (track_id,)
                )
                transaction.execute(
                    "DELETE FROM gm_artist_uncertainties WHERE track_id=?", (track_id,)
                )
                transaction.executemany(
                    "INSERT INTO gm_artist_contributions(track_id,artist_id,genre_id,"
                    "decision_source,rules_version,updated_at_utc) VALUES(?,?,?,?,?,?)",
                    [
                        (track_id, artist_id, genre_id, source, RULES_VERSION, _now())
                        for artist_id, genre_id, source in contributions
                    ],
                )
                transaction.executemany(
                    "INSERT INTO gm_artist_uncertainties(track_id,genre_id,reason,"
                    "title_excerpt,rules_version,updated_at_utc) VALUES(?,?,?,?,?,?)",
                    [
                        (track_id, genre_id, reason, title[:160], RULES_VERSION, _now())
                        for genre_id, reason in uncertainties
                    ],
                )
            changed += 1
        return changed

    def choose(self, track_id: str, artist_ids: Sequence[str]) -> None:
        """Persist an explicit subset of existing confirmed credits, then recalculate."""
        credits = self._credits(track_id)
        if not artist_ids or not set(artist_ids) <= {row["id"] for row in credits}:
            raise ValueError("Choose at least one confirmed artist credit")
        state = (
            self._database.connection()
            .execute(
                "SELECT genre_revision,reviewed_revision FROM gm_track_state WHERE track_id=?",
                (track_id,),
            )
            .fetchone()
        )
        if state is None or state["genre_revision"] != state["reviewed_revision"]:
            raise ValueError("Review the track classification first")
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO gm_artist_decisions(track_id,credit_signature,artist_ids_json,"
                "updated_at_utc) VALUES(?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET "
                "credit_signature=excluded.credit_signature,"
                "artist_ids_json=excluded.artist_ids_json,updated_at_utc=excluded.updated_at_utc",
                (
                    track_id,
                    _signature(self._title(track_id), credits),
                    json.dumps(list(dict.fromkeys(artist_ids))),
                    _now(),
                ),
            )
        self.refresh([track_id])

    def uncertainties(self) -> list[dict[str, Any]]:
        connection = self._database.connection()
        rows = connection.execute(
            "SELECT u.track_id,u.genre_id,u.reason,u.title_excerpt,g.name AS genre_name "
            "FROM gm_artist_uncertainties u JOIN gm_genres g ON g.genre_id=u.genre_id "
            "ORDER BY u.updated_at_utc DESC,u.track_id"
        )
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            identity = str(row["track_id"])
            if identity not in grouped:
                grouped[identity] = {
                    "trackId": identity,
                    "title": str(row["title_excerpt"]),
                    "reason": str(row["reason"]),
                    "genres": [],
                    "credits": self._credits(identity),
                }
            grouped[identity]["genres"].append(str(row["genre_name"]))
        return list(grouped.values())

    def artist_genres(self, artist_id: str) -> list[dict[str, Any]]:
        """Read calculated, provenanced genres for an artist page, never profile tags."""
        rows = self._database.connection().execute(
            "SELECT c.genre_id,g.name,c.decision_source,c.track_id "
            "FROM gm_artist_contributions c JOIN gm_genres g ON g.genre_id=c.genre_id "
            "WHERE c.artist_id=? ORDER BY g.name,c.track_id",
            (artist_id,),
        )
        grouped: dict[str, dict[str, Any]] = defaultdict(dict)
        for row in rows:
            identity = str(row["genre_id"])
            if not grouped[identity]:
                grouped[identity] = {
                    "id": identity,
                    "name": str(row["name"]),
                    "trackIds": [],
                    "sources": [],
                }
            grouped[identity]["trackIds"].append(str(row["track_id"]))
            grouped[identity]["sources"].append(str(row["decision_source"]))
        return list(grouped.values())

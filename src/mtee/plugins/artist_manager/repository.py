"""Artists, their credits, the review of every track and the journal of applications.

The tags of a file, the credits proposed or confirmed here, and the journal of what was
written on disk are kept apart: ``track_locations.metadata_json`` stays the observation
of the real tags, ``track_artist_credits`` with ``confirmed = 0`` is the working draft,
and ``confirmed = 1`` is the credit the catalog uses. A review row is created once per
track and is never reset by a new analysis.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from mtee.domain.artists import (
    CATEGORIES,
    RULES_VERSION,
    Proposal,
    choose_spelling,
    clean_name,
    is_usable_title,
    normalize_key,
)
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.plugins.artist_manager.profile import (
    HIDDEN_TAG,
    ArtistProfile,
    is_hidden,
    normalize_roles,
    normalize_tags,
)
from mtee.plugins.registry import prepare_plugin_schema

__all__ = ["ArtistRepository", "StageResult", "revision_from_json"]

DONE_STATES = ("succeeded",)
UNFINISHED_APPLY = ("queued", "running", "failed", "cancelled")


class StageResult:
    """Outcome of staging a confirmation."""

    def __init__(
        self,
        operation_id: str,
        staged: list[str],
        incomplete: list[str],
        stale: list[str],
    ) -> None:
        self.operation_id = operation_id
        self.staged = staged
        self.incomplete = incomplete
        self.stale = stale


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ArtistRepository:
    """SQLite access of the artist manager."""

    def __init__(self, database: Database) -> None:
        # Opening the repository loads the plugin: its tables are created on first use only.
        prepare_plugin_schema(database, "artist_manager")
        self._database = database

    # ------------------------------------------------------------------ workflow

    def workflow(self) -> dict[str, Any]:
        """Return the persistent state of the first run, deciding its mode on first use.

        The mode is decided before any profile exists: no established artist means a
        guided run, otherwise the categories are free. Creating provisional profiles
        later never changes it.
        """
        connection = self._database.connection()
        row = connection.execute("SELECT * FROM artist_workflow WHERE workflow_id=1").fetchone()
        if row is None:
            with self._database.transaction() as transaction:
                self._ensure_workflow(transaction)
            row = connection.execute("SELECT * FROM artist_workflow WHERE workflow_id=1").fetchone()
        return dict(row)

    @staticmethod
    def _ensure_workflow(connection: sqlite3.Connection) -> None:
        if connection.execute("SELECT 1 FROM artist_workflow WHERE workflow_id=1").fetchone():
            return
        established = connection.execute(
            "SELECT COUNT(*) FROM artists WHERE state='established'"
        ).fetchone()[0]
        mode = "free" if established else "guided"
        connection.execute(
            "INSERT INTO artist_workflow(workflow_id,mode,created_at_utc) VALUES(1,?,?)",
            (mode, _now()),
        )

    def register_cohort(self, track_ids: Iterable[str]) -> bool:
        """Record the tracks of the first complete pass; it is registered only once."""
        identities = list(dict.fromkeys(str(value) for value in track_ids))
        with self._database.transaction() as connection:
            self._ensure_workflow(connection)
            row = connection.execute(
                "SELECT cohort_registered FROM artist_workflow WHERE workflow_id=1"
            ).fetchone()
            if row["cohort_registered"]:
                return False
            connection.executemany(
                "INSERT OR IGNORE INTO artist_cohort(track_id) "
                "SELECT ? WHERE EXISTS (SELECT 1 FROM tracks WHERE track_id=?)",
                [(track_id, track_id) for track_id in identities],
            )
            connection.execute("UPDATE artist_workflow SET cohort_registered=1 WHERE workflow_id=1")
            return True

    def has_review(self, track_id: str) -> bool:
        return (
            self._database.connection()
            .execute("SELECT 1 FROM track_artist_review WHERE track_id=?", (track_id,))
            .fetchone()
            is not None
        )

    def missing_reviews(self, track_ids: Sequence[str]) -> list[str]:
        """Return the tracks of ``track_ids`` that have no review row yet."""
        if not track_ids:
            return []
        connection = self._database.connection()
        found: set[str] = set()
        identities = list(track_ids)
        for start in range(0, len(identities), 500):
            chunk = identities[start : start + 500]
            marks = ",".join("?" * len(chunk))
            found.update(
                str(row[0])
                for row in connection.execute(
                    f"SELECT track_id FROM track_artist_review WHERE track_id IN ({marks})", chunk
                )
            )
        return [track_id for track_id in identities if track_id not in found]

    def steps(self) -> dict[str, Any]:
        """Return the state of the three categories and update the persistent unlocking."""
        with self._database.transaction() as connection:
            self._ensure_workflow(connection)
            workflow = dict(
                connection.execute("SELECT * FROM artist_workflow WHERE workflow_id=1").fetchone()
            )
            missing = connection.execute(
                "SELECT COUNT(*) FROM artist_cohort c JOIN track_locations l "
                "ON l.track_id=c.track_id AND l.status='readable' "
                "WHERE NOT EXISTS (SELECT 1 FROM track_artist_review r WHERE r.track_id=c.track_id)"
            ).fetchone()[0]
            cohort_total = connection.execute("SELECT COUNT(*) FROM artist_cohort").fetchone()[0]
            ready = bool(workflow["cohort_registered"]) and missing == 0
            remaining_all = {
                str(row["category"]): int(row["n"])
                for row in connection.execute(
                    "SELECT category, COUNT(*) AS n FROM track_artist_review "
                    "WHERE NOT (review_state='confirmed' AND apply_state='succeeded') "
                    "GROUP BY category"
                )
            }
            remaining_cohort = {
                str(row["category"]): int(row["n"])
                for row in connection.execute(
                    "SELECT r.category AS category, COUNT(*) AS n FROM track_artist_review r "
                    "JOIN artist_cohort c ON c.track_id=r.track_id "
                    "WHERE NOT (r.review_state='confirmed' AND r.apply_state='succeeded') "
                    "GROUP BY r.category"
                )
            }
            unfinished = connection.execute(
                "SELECT COUNT(*) FROM track_artist_review WHERE review_state='confirmed' "
                "AND apply_state IN ('queued','running','failed','cancelled')"
            ).fetchone()[0]
            complete = {
                category: ready and remaining_cohort.get(category, 0) == 0
                for category in CATEGORIES
            }
            guided = workflow["mode"] == "guided" and not workflow["completed"]
            unlocked = int(workflow["unlocked_step"])
            for index, category in enumerate(CATEGORIES[:-1]):
                if complete[category]:
                    unlocked = max(unlocked, index + 1)
            finished = bool(workflow["completed"])
            if guided and all(complete.values()) and unfinished == 0:
                finished = True
            if finished != bool(workflow["completed"]) or unlocked != workflow["unlocked_step"]:
                connection.execute(
                    "UPDATE artist_workflow SET completed=?, unlocked_step=? WHERE workflow_id=1",
                    (int(finished), unlocked),
                )
            free = workflow["mode"] == "free" or finished
            categories: dict[str, Any] = {}
            for index, category in enumerate(CATEGORIES):
                accessible = free or index <= unlocked
                categories[category] = {
                    "remaining": remaining_all.get(category, 0),
                    "complete": complete[category],
                    "accessible": accessible,
                    "lockedBy": "" if accessible else CATEGORIES[index - 1],
                }
            return {
                "mode": "free" if free else "guided",
                "completed": finished,
                "cohortRegistered": bool(workflow["cohort_registered"]),
                "cohortTotal": int(cohort_total),
                "cohortMissing": int(missing),
                "cohortReady": ready,
                "unfinishedApplications": int(unfinished),
                "categories": categories,
            }

    # ------------------------------------------------------------------- artists

    @staticmethod
    def _resolve_artist(
        connection: sqlite3.Connection, name: str, *, manual: bool, create: bool = True
    ) -> str | None:
        display = clean_name(name)
        key = normalize_key(display)
        if not key:
            return None
        alias = connection.execute(
            "SELECT a.artist_id FROM artist_aliases al JOIN artists a ON a.artist_id=al.artist_id "
            "WHERE al.alias_key=? AND a.state<>'retired'",
            (key,),
        ).fetchone()
        if alias is not None:
            return str(alias[0])
        existing = connection.execute(
            "SELECT artist_id FROM artists WHERE name_key=? AND state<>'retired'", (key,)
        ).fetchone()
        if existing is not None:
            return str(existing[0])
        if not create:
            return None
        artist_id = str(uuid.uuid4())
        now = _now()
        connection.execute(
            "INSERT INTO artists(artist_id,display_name,name_key,name_origin,state,"
            "created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?)",
            (artist_id, display, key, "manual" if manual else "auto", "provisional", now, now),
        )
        return artist_id

    @staticmethod
    def _refresh_spelling(connection: sqlite3.Connection, artist_id: str) -> None:
        row = connection.execute(
            "SELECT display_name, name_origin FROM artists WHERE artist_id=?", (artist_id,)
        ).fetchone()
        if row is None or row["name_origin"] == "manual":
            return
        observed = [
            str(item[0])
            for item in connection.execute(
                "SELECT o.spelling FROM artist_name_observations o "
                "LEFT JOIN track_locations l ON l.track_id=o.track_id "
                "WHERE o.artist_id=? ORDER BY l.path_key, o.provenance, o.spelling",
                (artist_id,),
            )
        ]
        chosen = choose_spelling(observed, str(row["display_name"]))
        if chosen and chosen != row["display_name"]:
            connection.execute(
                "UPDATE artists SET display_name=?, updated_at_utc=? WHERE artist_id=?",
                (chosen, _now(), artist_id),
            )

    @staticmethod
    def _refresh_states(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE artists SET state='established', updated_at_utc=? "
            "WHERE state='provisional' AND EXISTS "
            "(SELECT 1 FROM track_artist_credits c WHERE c.artist_id=artists.artist_id "
            "AND c.confirmed=1)",
            (_now(),),
        )
        connection.execute(
            "UPDATE artists SET state='provisional', updated_at_utc=? "
            "WHERE state='established' AND NOT EXISTS "
            "(SELECT 1 FROM track_artist_credits c WHERE c.artist_id=artists.artist_id "
            "AND c.confirmed=1)",
            (_now(),),
        )

    def artist_names(self, query: str = "", *, limit: int = 12) -> list[dict[str, Any]]:
        """Return the active profiles whose name contains ``query``, for the suggestion list."""
        needle = normalize_key(query)
        rows = (
            self._database.connection()
            .execute(
                "SELECT artist_id, display_name, state FROM artists WHERE state<>'retired' "
                "ORDER BY display_name COLLATE NOCASE"
            )
            .fetchall()
        )
        found: list[dict[str, Any]] = []
        for row in rows:
            if needle and needle not in normalize_key(str(row["display_name"])):
                continue
            found.append(
                {
                    "id": str(row["artist_id"]),
                    "name": str(row["display_name"]),
                    "established": row["state"] == "established",
                }
            )
            if len(found) >= limit:
                break
        return found

    def artist(self, artist_id: str) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute("SELECT * FROM artists WHERE artist_id=?", (artist_id,))
            .fetchone()
        )
        if row is None:
            return None
        return {
            "id": str(row["artist_id"]),
            "name": str(row["display_name"]),
            "state": str(row["state"]),
            "manual": row["name_origin"] == "manual",
        }

    def protected_names(self) -> list[str]:
        """Return the names, and former spellings, of the profiles that hold a comma or ``&``.

        Such a profile is one artist: reading a credit never cuts it.
        """
        rows = (
            self._database.connection()
            .execute(
                "SELECT a.display_name AS name FROM artists a WHERE a.state<>'retired' "
                "UNION SELECT al.spelling FROM artist_aliases al "
                "JOIN artists a ON a.artist_id=al.artist_id WHERE a.state<>'retired'"
            )
            .fetchall()
        )
        return sorted(
            {str(row[0]) for row in rows if "," in str(row[0]) or "&" in str(row[0])},
            key=str.casefold,
        )

    def record_tag_credit(
        self,
        track_id: str,
        names: Sequence[str],
        title: str | None,
        *,
        revision: SourceRevision,
        original_artists: Sequence[str] = (),
    ) -> list[str]:
        """Make the credit just written to the tags the confirmed credit of a track.

        The track leaves every artist it no longer names; an artist left with no track
        at all is retired. Returns the ids of the profiles that were touched.
        """
        wanted = [clean_name(name) for name in names if clean_name(name)]
        with self._database.transaction() as connection:
            if (
                connection.execute("SELECT 1 FROM tracks WHERE track_id=?", (track_id,)).fetchone()
                is None
            ):
                return []
            old_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT artist_id FROM track_artist_credits WHERE track_id=?",
                    (track_id,),
                )
            ]
            roles = {
                str(row["artist_id"]): str(row["role"])
                for row in connection.execute(
                    "SELECT artist_id, role FROM track_artist_credits WHERE track_id=? "
                    "ORDER BY confirmed",
                    (track_id,),
                )
            }
            new_ids: list[str] = []
            spellings: dict[str, str] = {}
            for name in wanted:
                artist_id = self._resolve_artist(connection, name, manual=True)
                if artist_id is not None and artist_id not in new_ids:
                    new_ids.append(artist_id)
                    spellings[artist_id] = name
            self._ensure_workflow(connection)
            now = _now()
            category = "from_tags" if new_ids else "needs_input"
            state = "confirmed" if new_ids else "pending"
            apply = "succeeded" if new_ids else "none"
            row = connection.execute(
                "SELECT confirmed_title, proposed_title FROM track_artist_review WHERE track_id=?",
                (track_id,),
            ).fetchone()
            if row is None:
                shown = clean_name(title or "")
                connection.execute(
                    "INSERT INTO track_artist_review(track_id,category,initial_category,"
                    "review_state,apply_state,source_size_bytes,source_mtime_ns,"
                    "source_generation,original_artists_json,original_title,proposal_source,"
                    "proposed_title,confirmed_title,rules_version,created_at_utc,"
                    "updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        track_id,
                        category,
                        category,
                        state,
                        apply,
                        revision.size_bytes,
                        revision.mtime_ns,
                        revision.generation,
                        json.dumps(list(original_artists), ensure_ascii=False),
                        shown,
                        "tags",
                        shown,
                        shown if new_ids else None,
                        RULES_VERSION,
                        now,
                        now,
                    ),
                )
            else:
                shown = (
                    clean_name(title)
                    if title
                    else str(row["confirmed_title"] or row["proposed_title"] or "")
                )
                connection.execute(
                    "UPDATE track_artist_review SET category=?, review_state=?, apply_state=?, "
                    "apply_error='', apply_note='', proposed_title=?, confirmed_title=?, "
                    "decision_version=decision_version+1, updated_at_utc=? WHERE track_id=?",
                    (category, state, apply, shown, shown if new_ids else None, now, track_id),
                )
            self._write_credits(connection, track_id, 1, new_ids, roles)
            self._write_credits(connection, track_id, 0, new_ids, roles)
            marks = ",".join("?" * len(new_ids))
            connection.execute(
                "DELETE FROM artist_name_observations WHERE track_id=? "
                + (f"AND (artist_id NOT IN ({marks}) OR provenance='manual')" if new_ids else ""),
                (track_id, *new_ids),
            )
            for artist_id, spelling in spellings.items():
                connection.execute(
                    "INSERT OR IGNORE INTO artist_name_observations"
                    "(artist_id,track_id,spelling,provenance) VALUES(?,?,?,?)",
                    (artist_id, track_id, spelling, "manual"),
                )
            touched = set(old_ids) | set(new_ids)
            for artist_id in set(old_ids) - set(new_ids):
                used = connection.execute(
                    "SELECT 1 FROM track_artist_credits WHERE artist_id=? LIMIT 1", (artist_id,)
                ).fetchone()
                if used is None:
                    connection.execute(
                        "DELETE FROM artist_name_observations WHERE artist_id=?", (artist_id,)
                    )
                    connection.execute(
                        "UPDATE artists SET state='retired', updated_at_utc=? WHERE artist_id=?",
                        (now, artist_id),
                    )
            for artist_id in new_ids:
                self._refresh_spelling(connection, artist_id)
            self._refresh_states(connection)
            return sorted(touched)

    # -------------------------------------------------------------------- review

    def ingest(
        self,
        track_id: str,
        proposal: Proposal,
        *,
        revision: SourceRevision,
        original_artists: Sequence[str],
        original_title: str,
    ) -> bool:
        """Record the proposal of a track once; a track already reviewed is left alone."""
        with self._database.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM track_artist_review WHERE track_id=?", (track_id,)
            ).fetchone():
                return False
            known = connection.execute("SELECT 1 FROM tracks WHERE track_id=?", (track_id,))
            if known.fetchone() is None:
                return False
            self._ensure_workflow(connection)
            now = _now()
            connection.execute(
                "INSERT INTO track_artist_review(track_id,category,initial_category,"
                "source_size_bytes,source_mtime_ns,source_generation,original_artists_json,"
                "original_title,proposal_source,note,proposed_title,rules_version,"
                "created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    track_id,
                    proposal.category,
                    proposal.category,
                    revision.size_bytes,
                    revision.mtime_ns,
                    revision.generation,
                    json.dumps(list(original_artists), ensure_ascii=False),
                    original_title,
                    proposal.source,
                    proposal.note,
                    proposal.title,
                    RULES_VERSION,
                    now,
                    now,
                ),
            )
            touched: set[str] = set()
            position = 0
            for entry in proposal.credits:
                artist_id = self._resolve_artist(connection, entry.name, manual=False)
                if artist_id is None:
                    continue
                if connection.execute(
                    "SELECT 1 FROM track_artist_credits WHERE track_id=? AND confirmed=0 "
                    "AND artist_id=?",
                    (track_id, artist_id),
                ).fetchone():
                    continue
                connection.execute(
                    "INSERT INTO track_artist_credits(track_id,artist_id,position,role,confirmed) "
                    "VALUES(?,?,?,?,0)",
                    (track_id, artist_id, position, entry.role),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO artist_name_observations"
                    "(artist_id,track_id,spelling,provenance) VALUES(?,?,?,?)",
                    (artist_id, track_id, clean_name(entry.name), proposal.source),
                )
                touched.add(artist_id)
                position += 1
            for artist_id in touched:
                self._refresh_spelling(connection, artist_id)
            return True

    def reconsider_spellings(self) -> None:
        """Recompute the automatic spelling of every profile from all the observations."""
        with self._database.transaction() as connection:
            for row in connection.execute(
                "SELECT artist_id FROM artists WHERE state<>'retired'"
            ).fetchall():
                self._refresh_spelling(connection, str(row[0]))

    def review(self, track_id: str) -> dict[str, Any] | None:
        rows = self.review_rows(track_ids=[track_id], include_done=True)
        return rows[0] if rows else None

    def review_rows(
        self,
        *,
        category: str = "",
        track_ids: Sequence[str] | None = None,
        include_done: bool = False,
    ) -> list[dict[str, Any]]:
        """Return the review rows of a category, with their draft credits, by file name."""
        connection = self._database.connection()
        conditions = ["1=1"]
        parameters: list[Any] = []
        if category:
            conditions.append("r.category=?")
            parameters.append(category)
        if track_ids is not None:
            if not track_ids:
                return []
            marks = ",".join("?" * len(track_ids))
            conditions.append(f"r.track_id IN ({marks})")
            parameters.extend(track_ids)
        if not include_done:
            conditions.append("NOT (r.review_state='confirmed' AND r.apply_state='succeeded')")
        rows = connection.execute(
            "SELECT r.*, l.path AS path FROM track_artist_review r "
            "LEFT JOIN track_locations l ON l.track_id=r.track_id "
            f"WHERE {' AND '.join(conditions)}",
            parameters,
        ).fetchall()
        credits = self._credit_map(connection, [str(row["track_id"]) for row in rows], confirmed=0)
        result: list[dict[str, Any]] = []
        for row in rows:
            track_id = str(row["track_id"])
            names = credits.get(track_id, [])
            title = str(row["proposed_title"])
            path = str(row["path"] or "")
            result.append(
                {
                    "trackId": track_id,
                    "filename": PurePath(path).name if path else track_id,
                    "path": path,
                    "title": title,
                    "credits": names,
                    "artists": ", ".join(item["name"] for item in names),
                    "category": str(row["category"]),
                    "reviewState": str(row["review_state"]),
                    "applyState": str(row["apply_state"]),
                    "applyError": str(row["apply_error"]),
                    "applyNote": str(row["apply_note"]),
                    "note": str(row["note"]),
                    "source": str(row["proposal_source"]),
                    "originalTitle": str(row["original_title"]),
                    "originalArtists": json.loads(str(row["original_artists_json"])),
                    "version": int(row["decision_version"]),
                    "incomplete": not names or not is_usable_title(title),
                }
            )
        result.sort(key=lambda item: (item["filename"].casefold(), item["filename"]))
        return result

    @staticmethod
    def _credit_map(
        connection: sqlite3.Connection, track_ids: Sequence[str], *, confirmed: int
    ) -> dict[str, list[dict[str, Any]]]:
        found: dict[str, list[dict[str, Any]]] = {}
        for start in range(0, len(track_ids), 500):
            chunk = list(track_ids[start : start + 500])
            marks = ",".join("?" * len(chunk))
            for row in connection.execute(
                "SELECT c.track_id, c.artist_id, c.role, a.display_name, a.state "
                "FROM track_artist_credits c JOIN artists a ON a.artist_id=c.artist_id "
                f"WHERE c.confirmed=? AND c.track_id IN ({marks}) "
                "ORDER BY c.track_id, c.position",
                [confirmed, *chunk],
            ):
                found.setdefault(str(row["track_id"]), []).append(
                    {
                        "id": str(row["artist_id"]),
                        "name": str(row["display_name"]),
                        "role": str(row["role"]),
                        "established": row["state"] == "established",
                    }
                )
        return found

    def category_artists(self, category: str) -> list[dict[str, Any]]:
        """Return each artist of the unfinished tracks of a category and its track count."""
        rows = self.review_rows(category=category)
        counts: dict[str, dict[str, Any]] = {}
        for row in rows:
            for credit in row["credits"]:
                entry = counts.setdefault(
                    credit["id"],
                    {"id": credit["id"], "name": credit["name"], "tracks": 0, "trackIds": []},
                )
                entry["tracks"] += 1
                entry["trackIds"].append(row["trackId"])
        return sorted(counts.values(), key=lambda item: (item["name"].casefold(), item["name"]))

    def save_draft(
        self,
        track_id: str,
        title: str,
        entries: Sequence[tuple[str, str]],
        *,
        category: str = "",
    ) -> int:
        """Replace the draft of a track; returns its new decision version.

        Each entry is ``(artist_id, typed_name)``. A selected profile is kept only while
        the typed text still equals its name; any other text is a free entry that finds
        or creates a profile and never renames the profile that was selected. The
        typed text is literal: commas and ``&`` are not split here.
        """
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT category FROM track_artist_review WHERE track_id=?", (track_id,)
            ).fetchone()
            if row is None:
                raise KeyError(track_id)
            ordered: list[str] = []
            for artist_id, typed in entries:
                name = clean_name(typed)
                if not name:
                    continue
                resolved: str | None = None
                if artist_id:
                    selected = connection.execute(
                        "SELECT artist_id, display_name FROM artists WHERE artist_id=? "
                        "AND state<>'retired'",
                        (artist_id,),
                    ).fetchone()
                    if selected is not None and normalize_key(
                        str(selected["display_name"])
                    ) == normalize_key(name):
                        resolved = str(selected["artist_id"])
                if resolved is None:
                    resolved = self._resolve_artist(connection, name, manual=True)
                if resolved is not None and resolved not in ordered:
                    ordered.append(resolved)
            roles = {
                str(item["artist_id"]): str(item["role"])
                for item in connection.execute(
                    "SELECT artist_id, role FROM track_artist_credits "
                    "WHERE track_id=? AND confirmed=0",
                    (track_id,),
                )
            }
            self._write_credits(connection, track_id, 0, ordered, roles)
            new_category = category if category in CATEGORIES else str(row["category"])
            connection.execute(
                "UPDATE track_artist_review SET proposed_title=?, category=?, "
                "decision_version=decision_version+1, review_state='pending', "
                "apply_state='none', apply_error='', apply_note='', updated_at_utc=? "
                "WHERE track_id=?",
                (clean_name(title), new_category, _now(), track_id),
            )
            return int(
                connection.execute(
                    "SELECT decision_version FROM track_artist_review WHERE track_id=?", (track_id,)
                ).fetchone()[0]
            )

    @staticmethod
    def _write_credits(
        connection: sqlite3.Connection,
        track_id: str,
        confirmed: int,
        artist_ids: Sequence[str],
        roles: dict[str, str] | None = None,
    ) -> None:
        connection.execute(
            "DELETE FROM track_artist_credits WHERE track_id=? AND confirmed=?",
            (track_id, confirmed),
        )
        connection.executemany(
            "INSERT INTO track_artist_credits(track_id,artist_id,position,role,confirmed) "
            "VALUES(?,?,?,?,?)",
            [
                (track_id, artist_id, position, (roles or {}).get(artist_id, "artist"), confirmed)
                for position, artist_id in enumerate(artist_ids)
            ],
        )

    def set_category(self, track_id: str, category: str) -> None:
        if category not in CATEGORIES:
            raise ValueError(category)
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE track_artist_review SET category=?, decision_version=decision_version+1, "
                "updated_at_utc=? WHERE track_id=? AND category<>?",
                (category, _now(), track_id, category),
            )

    # ------------------------------------------------------------- confirmations

    def stage_confirmation(
        self,
        items: Sequence[tuple[str, int]],
        *,
        write_tags: bool,
        label: str,
    ) -> StageResult:
        """Freeze the decisions of a lot and queue their application.

        Every item carries the decision version that was shown to the user. An item
        whose version changed, or whose credit or title is incomplete, is returned and
        not staged; nothing is applied silently on a subset: the caller decides.
        """
        operation_id = str(uuid.uuid4())
        staged: list[str] = []
        incomplete: list[str] = []
        stale: list[str] = []
        with self._database.transaction() as connection:
            now = _now()
            plan: list[tuple[str, int, dict[str, Any]]] = []
            for track_id, version in items:
                row = connection.execute(
                    "SELECT * FROM track_artist_review WHERE track_id=?", (track_id,)
                ).fetchone()
                if (
                    row is None
                    or int(row["decision_version"]) != version
                    or (row["review_state"] == "confirmed" and row["apply_state"] == "succeeded")
                ):
                    stale.append(track_id)
                    continue
                draft = connection.execute(
                    "SELECT artist_id, role FROM track_artist_credits "
                    "WHERE track_id=? AND confirmed=0 ORDER BY position",
                    (track_id,),
                ).fetchall()
                if not draft or not is_usable_title(str(row["proposed_title"])):
                    incomplete.append(track_id)
                    continue
                before = {
                    "reviewState": str(row["review_state"]),
                    "applyState": str(row["apply_state"]),
                    "confirmedTitle": row["confirmed_title"],
                    "confirmedCredits": [
                        [str(item["artist_id"]), str(item["role"])]
                        for item in connection.execute(
                            "SELECT artist_id, role FROM track_artist_credits "
                            "WHERE track_id=? AND confirmed=1 ORDER BY position",
                            (track_id,),
                        )
                    ],
                }
                plan.append((track_id, version, {"draft": draft, "before": before}))
            if incomplete or stale or not plan:
                return StageResult("", [], incomplete, stale)
            connection.execute(
                "INSERT INTO artist_operations(operation_id,kind,label,write_tags,status,"
                "created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?)",
                (operation_id, "confirm", label, int(write_tags), "prepared", now, now),
            )
            for track_id, version, details in plan:
                draft = details["draft"]
                self._write_credits(
                    connection,
                    track_id,
                    1,
                    [str(item["artist_id"]) for item in draft],
                    {str(item["artist_id"]): str(item["role"]) for item in draft},
                )
                connection.execute(
                    "UPDATE track_artist_review SET review_state='confirmed', "
                    "apply_state='queued', apply_error='', apply_note='', apply_write_tags=?, "
                    "confirmed_title=proposed_title, updated_at_utc=? WHERE track_id=?",
                    (int(write_tags), now, track_id),
                )
                connection.execute(
                    "INSERT INTO artist_operation_items(operation_id,track_id,mode,status,"
                    "decision_version,before_json,updated_at_utc) VALUES(?,?,?,?,?,?,?)",
                    (
                        operation_id,
                        track_id,
                        "full",
                        "queued",
                        version,
                        json.dumps(details["before"]),
                        now,
                    ),
                )
                staged.append(track_id)
            self._refresh_states(connection)
        return StageResult(operation_id, staged, [], [])

    # ---------------------------------------------------- artist-level operations

    @staticmethod
    def _tracks_using(
        connection: sqlite3.Connection, artist_id: str, *, confirmed: int | None = None
    ) -> list[str]:
        condition = "" if confirmed is None else f"AND confirmed={int(confirmed)}"
        return [
            str(row[0])
            for row in connection.execute(
                f"SELECT DISTINCT track_id FROM track_artist_credits WHERE artist_id=? {condition}",
                (artist_id,),
            )
        ]

    def tracks_of_artist_confirmed(self, artist_id: str) -> list[str]:
        with self._database.transaction() as connection:
            return self._tracks_using(connection, artist_id, confirmed=1)

    def rename_artist(self, artist_id: str, new_name: str) -> list[str]:
        """Rename a profile and lock its spelling; returns the confirmed tracks affected."""
        name = clean_name(new_name)
        key = normalize_key(name)
        if not key:
            raise ValueError("The artist name cannot be empty.")
        with self._database.transaction() as connection:
            clash = connection.execute(
                "SELECT artist_id FROM artists WHERE name_key=? AND state<>'retired' "
                "AND artist_id<>?",
                (key, artist_id),
            ).fetchone()
            if clash is not None:
                raise ValueError("Another artist already has this name. Use Merge instead.")
            old = connection.execute(
                "SELECT display_name, name_key FROM artists WHERE artist_id=? AND state<>'retired'",
                (artist_id,),
            ).fetchone()
            if old is None:
                raise ValueError("The artist no longer exists.")
            connection.execute(
                "UPDATE artists SET display_name=?, name_key=?, name_origin='manual', "
                "updated_at_utc=? WHERE artist_id=?",
                (name, key, _now(), artist_id),
            )
            if old["name_key"] != key:
                # The former spelling keeps pointing at this identity in the next imports.
                connection.execute(
                    "INSERT OR REPLACE INTO artist_aliases(alias_key,artist_id,spelling) "
                    "VALUES(?,?,?)",
                    (str(old["name_key"]), artist_id, str(old["display_name"])),
                )
            return self._tracks_using(connection, artist_id, confirmed=1)

    def merge_artists(self, source_id: str, destination_id: str) -> list[str]:
        """Merge ``source_id`` into ``destination_id``; returns the confirmed tracks affected."""
        if source_id == destination_id:
            raise ValueError("Choose another artist to merge into.")
        with self._database.transaction() as connection:
            source = connection.execute(
                "SELECT * FROM artists WHERE artist_id=? AND state<>'retired'", (source_id,)
            ).fetchone()
            destination = connection.execute(
                "SELECT * FROM artists WHERE artist_id=? AND state<>'retired'", (destination_id,)
            ).fetchone()
            if source is None or destination is None:
                raise ValueError("The artist no longer exists.")
            affected = self._tracks_using(connection, source_id, confirmed=1)
            for track_id in self._tracks_using(connection, source_id):
                for confirmed in (0, 1):
                    self._substitute(connection, track_id, confirmed, source_id, destination_id)
            connection.execute(
                "UPDATE artist_name_observations SET artist_id=? WHERE artist_id=?",
                (destination_id, source_id),
            )
            connection.execute(
                "UPDATE artist_aliases SET artist_id=? WHERE artist_id=?",
                (destination_id, source_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO artist_aliases(alias_key,artist_id,spelling) VALUES(?,?,?)",
                (str(source["name_key"]), destination_id, str(source["display_name"])),
            )
            connection.execute(
                "UPDATE artists SET state='retired', merged_into=?, updated_at_utc=? "
                "WHERE artist_id=?",
                (destination_id, _now(), source_id),
            )
            self._refresh_spelling(connection, destination_id)
            self._refresh_states(connection)
            return affected

    def delete_artist(self, artist_id: str) -> list[str]:
        """Detach a profile from its credits; returns the confirmed tracks affected.

        A pending track left without any artist goes to ``needs_input``; a confirmed
        one goes back to review with its previous credit removed. No audio file is
        deleted.
        """
        with self._database.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM artists WHERE artist_id=? AND state<>'retired'", (artist_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("The artist no longer exists.")
            affected = self._tracks_using(connection, artist_id, confirmed=1)
            for track_id in self._tracks_using(connection, artist_id):
                for confirmed in (0, 1):
                    self._substitute(connection, track_id, confirmed, artist_id, None)
                draft_left = connection.execute(
                    "SELECT COUNT(*) FROM track_artist_credits WHERE track_id=? AND confirmed=0",
                    (track_id,),
                ).fetchone()[0]
                confirmed_left = connection.execute(
                    "SELECT COUNT(*) FROM track_artist_credits WHERE track_id=? AND confirmed=1",
                    (track_id,),
                ).fetchone()[0]
                if track_id in affected and confirmed_left == 0:
                    connection.execute(
                        "UPDATE track_artist_review SET review_state='pending', "
                        "apply_state='none', category='needs_input', "
                        "decision_version=decision_version+1, updated_at_utc=? WHERE track_id=?",
                        (_now(), track_id),
                    )
                elif draft_left == 0:
                    connection.execute(
                        "UPDATE track_artist_review SET category='needs_input', "
                        "decision_version=decision_version+1, updated_at_utc=? WHERE track_id=?",
                        (_now(), track_id),
                    )
            connection.execute(
                "DELETE FROM artist_name_observations WHERE artist_id=?", (artist_id,)
            )
            connection.execute(
                "UPDATE artists SET state='retired', updated_at_utc=? WHERE artist_id=?",
                (_now(), artist_id),
            )
            self._refresh_states(connection)
            return affected

    def _substitute(
        self,
        connection: sqlite3.Connection,
        track_id: str,
        confirmed: int,
        old_id: str,
        new_id: str | None,
    ) -> None:
        rows = connection.execute(
            "SELECT artist_id, role FROM track_artist_credits "
            "WHERE track_id=? AND confirmed=? ORDER BY position",
            (track_id, confirmed),
        ).fetchall()
        if not any(str(row["artist_id"]) == old_id for row in rows):
            return
        ordered: list[str] = []
        roles: dict[str, str] = {}
        for row in rows:
            artist_id = str(row["artist_id"])
            if artist_id == old_id:
                if new_id is None:
                    continue
                artist_id = new_id
            if artist_id not in ordered:
                ordered.append(artist_id)
                roles[artist_id] = str(row["role"])
        self._write_credits(connection, track_id, confirmed, ordered, roles)

    def queue_operation(
        self,
        kind: str,
        label: str,
        track_ids: Sequence[str],
        *,
        write_tags: bool,
        tags_only: Iterable[str] = (),
    ) -> str:
        """Journal the application of an artist-level change on its confirmed tracks."""
        if not track_ids:
            return ""
        tags_only_ids = set(tags_only)
        operation_id = str(uuid.uuid4())
        now = _now()
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO artist_operations(operation_id,kind,label,write_tags,status,"
                "created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?)",
                (operation_id, kind, label, int(write_tags), "prepared", now, now),
            )
            for track_id in track_ids:
                row = connection.execute(
                    "SELECT decision_version FROM track_artist_review WHERE track_id=?",
                    (track_id,),
                ).fetchone()
                if row is None:
                    continue
                mode = "tags_only" if track_id in tags_only_ids else "full"
                connection.execute(
                    "INSERT INTO artist_operation_items(operation_id,track_id,mode,status,"
                    "decision_version,updated_at_utc) VALUES(?,?,?,?,?,?)",
                    (operation_id, track_id, mode, "queued", int(row[0]), now),
                )
                if mode == "full":
                    connection.execute(
                        "UPDATE track_artist_review SET apply_state='queued', apply_error='', "
                        "apply_note='', apply_write_tags=?, updated_at_utc=? WHERE track_id=?",
                        (int(write_tags), now, track_id),
                    )
        return operation_id

    # ------------------------------------------------------------------- journal

    def operation(self, operation_id: str) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute("SELECT * FROM artist_operations WHERE operation_id=?", (operation_id,))
            .fetchone()
        )
        return dict(row) if row is not None else None

    def operation_items(
        self, operation_id: str, statuses: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM artist_operation_items WHERE operation_id=?"
        parameters: list[Any] = [operation_id]
        if statuses:
            query += f" AND status IN ({','.join('?' * len(statuses))})"
            parameters.extend(statuses)
        rows = self._database.connection().execute(query + " ORDER BY rowid", parameters)
        return [dict(row) for row in rows.fetchall()]

    def set_operation_status(self, operation_id: str, status: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE artist_operations SET status=?, updated_at_utc=? WHERE operation_id=?",
                (status, _now(), operation_id),
            )

    def update_item(self, operation_id: str, track_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "path_before",
            "path_target",
            "path_final",
            "revision_before_json",
            "revision_after_json",
            "tags_phase",
            "tag_operation_id",
            "rename_phase",
            "error",
            "warning",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown journal field: {', '.join(sorted(unknown))}")
        if not fields:
            return
        assignments = ",".join(f"{name}=?" for name in fields)
        with self._database.transaction() as connection:
            connection.execute(
                f"UPDATE artist_operation_items SET {assignments}, updated_at_utc=? "
                "WHERE operation_id=? AND track_id=?",
                [*fields.values(), _now(), operation_id, track_id],
            )

    def set_apply_state(
        self, track_id: str, state: str, *, error: str = "", note: str | None = None
    ) -> None:
        with self._database.transaction() as connection:
            if note is None:
                connection.execute(
                    "UPDATE track_artist_review SET apply_state=?, apply_error=?, "
                    "updated_at_utc=? WHERE track_id=?",
                    (state, error, _now(), track_id),
                )
            else:
                connection.execute(
                    "UPDATE track_artist_review SET apply_state=?, apply_error=?, apply_note=?, "
                    "updated_at_utc=? WHERE track_id=?",
                    (state, error, note, _now(), track_id),
                )

    @staticmethod
    def finish_item(
        connection: sqlite3.Connection,
        operation_id: str,
        track_id: str,
        *,
        path_final: str,
        revision_after: SourceRevision,
        note: str,
    ) -> None:
        """Record the end of an item in the transaction that moved its location."""
        now = _now()
        connection.execute(
            "UPDATE artist_operation_items SET status='succeeded', path_final=?, "
            "revision_after_json=?, error='', warning=?, updated_at_utc=? "
            "WHERE operation_id=? AND track_id=?",
            (
                path_final,
                json.dumps(_revision_json(revision_after)),
                note,
                now,
                operation_id,
                track_id,
            ),
        )
        connection.execute(
            "UPDATE track_artist_review SET apply_state='succeeded', apply_error='', "
            "apply_note=?, updated_at_utc=? WHERE track_id=?",
            (note, now, track_id),
        )

    def pending_applications(self) -> list[dict[str, Any]]:
        """Return the confirmed tracks whose application is not finished, for a resume."""
        rows = (
            self._database.connection()
            .execute(
                "SELECT i.operation_id, i.track_id FROM artist_operation_items i "
                "JOIN artist_operations o ON o.operation_id=i.operation_id "
                "JOIN track_artist_review r ON r.track_id=i.track_id "
                "WHERE i.status IN ('queued','running','failed','cancelled') "
                "AND r.apply_state IN ('queued','running','failed','cancelled') "
                "AND i.rowid = (SELECT MAX(j.rowid) FROM artist_operation_items j "
                "WHERE j.track_id=i.track_id) "
                "ORDER BY i.rowid"
            )
            .fetchall()
        )
        return [dict(row) for row in rows]

    def confirmed_state(self, track_id: str) -> dict[str, Any] | None:
        """Return the confirmed title and credits of a track, or ``None`` before confirmation."""
        connection = self._database.connection()
        row = connection.execute(
            "SELECT review_state, confirmed_title, apply_write_tags FROM track_artist_review "
            "WHERE track_id=?",
            (track_id,),
        ).fetchone()
        if row is None:
            return None
        credits = self._credit_map(connection, [track_id], confirmed=1).get(track_id, [])
        return {
            "reviewState": str(row["review_state"]),
            "title": str(row["confirmed_title"] or ""),
            "credits": credits,
            "writeTags": bool(row["apply_write_tags"]),
        }

    def restore_decision(self, track_id: str, before: dict[str, Any]) -> None:
        """Put the decision of a track back to its state before a confirmation."""
        with self._database.transaction() as connection:
            credits = [str(item[0]) for item in before.get("confirmedCredits", [])]
            roles = {str(item[0]): str(item[1]) for item in before.get("confirmedCredits", [])}
            valid = [
                artist_id
                for artist_id in credits
                if connection.execute(
                    "SELECT 1 FROM artists WHERE artist_id=? AND state<>'retired'", (artist_id,)
                ).fetchone()
            ]
            self._write_credits(connection, track_id, 1, valid, roles)
            connection.execute(
                "UPDATE track_artist_review SET review_state=?, apply_state=?, "
                "apply_error='', apply_note='', confirmed_title=?, "
                "decision_version=decision_version+1, updated_at_utc=? WHERE track_id=?",
                (
                    str(before.get("reviewState", "pending")),
                    str(before.get("applyState", "none")),
                    before.get("confirmedTitle"),
                    _now(),
                    track_id,
                ),
            )
            self._refresh_states(connection)

    def last_confirmation(self) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute(
                "SELECT * FROM artist_operations WHERE kind='confirm' AND status IN "
                "('completed','partial') ORDER BY created_at_utc DESC, rowid DESC LIMIT 1"
            )
            .fetchone()
        )
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------- catalog

    def catalog(self) -> list[dict[str, Any]]:
        """Return the established artists, their tracks, roles, tags and hidden state."""
        rows = (
            self._database.connection()
            .execute(
                "SELECT a.artist_id, a.display_name, COUNT(DISTINCT c.track_id) AS tracks, "
                "r.decision, r.roles_json, r.bass_related, r.tags_json "
                "FROM artists a JOIN track_artist_credits c ON c.artist_id=a.artist_id "
                "AND c.confirmed=1 JOIN track_locations l ON l.track_id=c.track_id "
                "LEFT JOIN artist_enrichment_reviews r ON r.artist_id=a.artist_id "
                "WHERE a.state='established' GROUP BY a.artist_id "
                "ORDER BY a.display_name COLLATE NOCASE, a.display_name"
            )
            .fetchall()
        )
        return [
            {
                "id": str(row["artist_id"]),
                "name": str(row["display_name"]),
                "tracks": int(row["tracks"]),
                **_profile_from_row(row).as_dict(),
            }
            for row in rows
        ]

    def artist_profile(self, artist_id: str) -> ArtistProfile:
        """Return the roles, tags and hidden state of an artist (empty when never set)."""
        row = (
            self._database.connection()
            .execute(
                "SELECT decision, roles_json, bass_related, tags_json "
                "FROM artist_enrichment_reviews WHERE artist_id=?",
                (artist_id,),
            )
            .fetchone()
        )
        return _profile_from_row(row)

    def save_artist_profile(
        self,
        artist_id: str,
        *,
        roles: Iterable[object],
        bass_related: bool | None,
        tags: Iterable[object],
        hidden: bool,
    ) -> ArtistProfile:
        """Store the roles, tags and hidden state of an artist.

        ``idgaf`` and the ``exclude`` decision always change together; any other
        decision (``uncertain``, ``pending``) is kept while the artist stays visible. The
        links, notes and sourced observations of the row are never touched.
        """
        clean_roles = normalize_roles(roles)
        clean_tags = normalize_tags(tags)
        stored_tags = [HIDDEN_TAG, *clean_tags] if hidden else clean_tags
        now = _now()
        with self._database.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM artists WHERE artist_id=?", (artist_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("The artist no longer exists.")
            row = connection.execute(
                "SELECT decision, record_json FROM artist_enrichment_reviews WHERE artist_id=?",
                (artist_id,),
            ).fetchone()
            previous = str(row["decision"]) if row is not None else "keep"
            decision = "exclude" if hidden else ("keep" if previous == "exclude" else previous)
            record = _record(row["record_json"] if row is not None else "")
            record.update(
                {
                    "decision": decision,
                    "roles": clean_roles,
                    "bass_related": bass_related,
                    "tags": stored_tags,
                    "saved_at": now,
                }
            )
            _upsert_review(
                connection, artist_id, decision, clean_roles, bass_related, stored_tags, record, now
            )
        return ArtistProfile(clean_roles, bass_related, clean_tags, hidden)

    def set_folder_genres(self, artist_id: str, genres: Mapping[str, int]) -> ArtistProfile:
        """Give an artist the genres read from the folders, with their track counts.

        The counts are kept in ``record_json`` (``genre_sources``) and the tags this call
        added in ``genre_added``: the next run removes exactly those, and never a tag the
        user typed, even one that spells the same as a genre.
        """
        ordered = sorted(genres.items(), key=lambda item: (-item[1], item[0].casefold()))
        now = _now()
        with self._database.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM artists WHERE artist_id=?", (artist_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("The artist no longer exists.")
            row = connection.execute(
                "SELECT decision, roles_json, bass_related, tags_json, record_json "
                "FROM artist_enrichment_reviews WHERE artist_id=?",
                (artist_id,),
            ).fetchone()
            profile = _profile_from_row(row)
            record = _record(row["record_json"] if row is not None else "")
            earlier = record.get("genre_added")
            earlier_keys = (
                {str(name).casefold() for name in earlier} if isinstance(earlier, list) else set()
            )
            manual = [tag for tag in profile.tags if tag.casefold() not in earlier_keys]
            manual_keys = {tag.casefold() for tag in manual}
            tags = normalize_tags([*manual, *(name for name, _ in ordered)])
            counts = {name: count for name, count in ordered if name in tags}
            added = [name for name in counts if name.casefold() not in manual_keys]
            stored_tags = [HIDDEN_TAG, *tags] if profile.hidden else tags
            decision = str(row["decision"]) if row is not None else "keep"
            record.update(
                {
                    "decision": decision,
                    "roles": profile.roles,
                    "bass_related": profile.bass_related,
                    "tags": stored_tags,
                    "genre_sources": counts,
                    "genre_added": added,
                    "saved_at": now,
                }
            )
            _upsert_review(
                connection,
                artist_id,
                decision,
                profile.roles,
                profile.bass_related,
                stored_tags,
                record,
                now,
            )
        return ArtistProfile(profile.roles, profile.bass_related, tags, profile.hidden)

    def catalog_track_ids(self, artist_id: str) -> list[str]:
        """Return the tracks credited to ``artist_id``, by file name."""
        rows = (
            self._database.connection()
            .execute(
                "SELECT DISTINCT c.track_id FROM track_artist_credits c "
                "JOIN track_locations l ON l.track_id=c.track_id "
                "WHERE c.artist_id=? AND c.confirmed=1 "
                "ORDER BY l.path COLLATE NOCASE, l.path",
                (artist_id,),
            )
            .fetchall()
        )
        return [str(row[0]) for row in rows]

    def confirmed_credit_names(self, track_ids: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
        return self._credit_map(self._database.connection(), list(track_ids), confirmed=1)

    def readable_track_ids(self) -> list[str]:
        """Return every readable, present track of the registered roots, once each."""
        rows = (
            self._database.connection()
            .execute(
                "SELECT DISTINCT rt.track_id FROM root_tracks rt "
                "JOIN track_locations l ON l.track_id=rt.track_id "
                "WHERE rt.present=1 AND l.status='readable' ORDER BY l.path_key"
            )
            .fetchall()
        )
        return [str(row[0]) for row in rows]


def _upsert_review(
    connection: sqlite3.Connection,
    artist_id: str,
    decision: str,
    roles: list[str],
    bass_related: bool | None,
    stored_tags: list[str],
    record: dict[str, Any],
    now: str,
) -> None:
    """Write the editable fields of an enrichment row; links, notes and observations stay."""
    connection.execute(
        "INSERT INTO artist_enrichment_reviews(artist_id, decision, roles_json, "
        "bass_related, spotify_url, soundcloud_url, tags_json, notes, "
        "identity_decision, validated_at_utc, record_json, observation_json) "
        "VALUES(?,?,?,?, '', '', ?, '', 'accepted', ?, ?, '{}') "
        "ON CONFLICT(artist_id) DO UPDATE SET decision=excluded.decision, "
        "roles_json=excluded.roles_json, bass_related=excluded.bass_related, "
        "tags_json=excluded.tags_json, record_json=excluded.record_json",
        (
            artist_id,
            decision,
            json.dumps(roles),
            None if bass_related is None else int(bass_related),
            json.dumps(stored_tags),
            now,
            json.dumps(record, ensure_ascii=False),
        ),
    )


def _record(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _profile_from_row(row: sqlite3.Row | None) -> ArtistProfile:
    if row is None:
        return ArtistProfile()
    try:
        raw_tags = json.loads(row["tags_json"])
        raw_roles = json.loads(row["roles_json"])
    except (TypeError, ValueError):
        raw_tags, raw_roles = [], []
    raw_tags = raw_tags if isinstance(raw_tags, list) else []
    raw_roles = raw_roles if isinstance(raw_roles, list) else []
    bass = row["bass_related"]
    return ArtistProfile(
        roles=normalize_roles(raw_roles),
        bass_related=None if bass is None else bool(bass),
        tags=normalize_tags(raw_tags),
        hidden=is_hidden(str(row["decision"]), raw_tags),
    )


def _revision_json(revision: SourceRevision) -> dict[str, Any]:
    return {
        "size_bytes": revision.size_bytes,
        "mtime_ns": revision.mtime_ns,
        "file_id": revision.file_id,
        "generation": revision.generation,
    }


def revision_from_json(text: str) -> SourceRevision | None:
    if not text:
        return None
    data = json.loads(text)
    return SourceRevision(
        int(data["size_bytes"]), int(data["mtime_ns"]), data.get("file_id"), int(data["generation"])
    )

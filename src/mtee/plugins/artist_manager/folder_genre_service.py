"""Give the artists of a library the genres of the folders their tracks sit in.

``plan`` only reads. ``apply`` writes the genres as tags of the artists, through the
artist repository, and removes the ones an earlier run added when they no longer hold.
The tags typed by the user are never touched.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from mtee.persistence.database import Database
from mtee.plugins.artist_manager.folder_genres import (
    IGNORED_FOLDERS,
    Credit,
    folder_genres,
    marker_names,
    track_targets,
)
from mtee.plugins.artist_manager.repository import ArtistRepository

__all__ = ["FolderGenreService", "GenrePlan"]


@dataclass(slots=True)
class GenrePlan:
    """What a run would do, with the tracks it could not decide."""

    root: str
    tracks: int = 0
    artist_names: dict[str, str] = field(default_factory=dict)
    artist_genres: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    genre_tracks: Counter[str] = field(default_factory=Counter)
    statuses: Counter[str] = field(default_factory=Counter)
    ignored_folders: Counter[str] = field(default_factory=Counter)
    uncredited: int = 0
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    lost_markers: list[dict[str, Any]] = field(default_factory=list)

    @property
    def genre_artists(self) -> Counter[str]:
        counts: Counter[str] = Counter()
        for genres in self.artist_genres.values():
            counts.update(genres.keys())
        return counts


class FolderGenreService:
    def __init__(self, database: Database, repository: ArtistRepository) -> None:
        self._database = database
        self._repository = repository

    def plan(
        self, root_name: str, ignored: Iterable[str] = IGNORED_FOLDERS, depth: int = 2
    ) -> GenrePlan:
        connection = self._database.connection()
        plan = GenrePlan(root_name)
        credits: dict[str, list[Credit]] = defaultdict(list)
        for row in connection.execute(
            "SELECT c.track_id, a.artist_id, a.display_name, c.role "
            "FROM track_artist_credits c JOIN artists a ON a.artist_id=c.artist_id "
            "WHERE c.confirmed=1 AND a.state='established' ORDER BY c.track_id, c.position"
        ):
            credits[str(row[0])].append(Credit(str(row[1]), str(row[2]), str(row[3])))
            plan.artist_names[str(row[1])] = str(row[2])
        ignored_keys = {name.casefold() for name in ignored}
        rows = connection.execute(
            "SELECT t.track_id, t.relative_path, l.metadata_json, "
            "r.confirmed_title, r.original_title "
            "FROM root_tracks t JOIN library_roots lr ON lr.root_id=t.root_id "
            "JOIN track_locations l ON l.track_id=t.track_id "
            "LEFT JOIN track_artist_review r ON r.track_id=t.track_id "
            "WHERE lr.name=? AND t.present=1 ORDER BY t.relative_path",
            (root_name,),
        ).fetchall()
        seen: set[str] = set()
        for row in rows:
            track_id, relative = str(row[0]), str(row[1])
            if track_id in seen:
                continue
            seen.add(track_id)
            plan.tracks += 1
            genres = folder_genres(relative, ignored_keys, depth)
            if not genres:
                folders = relative.replace("\\", "/").split("/")
                plan.ignored_folders[folders[0] if len(folders) > 1 else "(root)"] += 1
                continue
            track_credits = credits.get(track_id, [])
            if not track_credits:
                plan.uncredited += 1
                continue
            final = _final_title(row[2], row[3])
            stem = PurePath(relative).stem
            others = [title for title in (row[4], stem) if title]
            titles = [title for title in (final, *others) if title]
            targets = track_targets(track_credits, titles)
            plan.statuses[targets.status] += 1
            known = set(marker_names(final)) if final else set()
            lost = [
                name for title in others for name in marker_names(str(title)) if name not in known
            ]
            if lost:
                plan.lost_markers.append(
                    {
                        "path": relative,
                        "names": list(dict.fromkeys(lost)),
                        "status": targets.status,
                    }
                )
            if targets.status == "unresolved":
                plan.unresolved.append(
                    {
                        "path": relative,
                        "genres": genres,
                        "names": targets.names,
                        "credits": [credit.name for credit in track_credits],
                    }
                )
                continue
            if not targets.artist_ids:
                continue
            for genre in genres:
                plan.genre_tracks[genre] += 1
            for artist_id in targets.artist_ids:
                for genre in genres:
                    plan.artist_genres[artist_id][genre] += 1
        return plan

    def apply(self, plan: GenrePlan) -> dict[str, int]:
        """Write the genres of ``plan``; return how many artists were tagged and cleared."""
        tagged = 0
        for artist_id, genres in plan.artist_genres.items():
            self._repository.set_folder_genres(artist_id, dict(genres))
            tagged += 1
        cleared = 0
        for artist_id in self._with_earlier_genres():
            if artist_id not in plan.artist_genres:
                self._repository.set_folder_genres(artist_id, {})
                cleared += 1
        return {"tagged": tagged, "cleared": cleared}

    def _with_earlier_genres(self) -> list[str]:
        rows = (
            self._database.connection()
            .execute(
                "SELECT artist_id, record_json FROM artist_enrichment_reviews "
                "WHERE record_json LIKE '%genre_added%'"
            )
            .fetchall()
        )
        found: list[str] = []
        for row in rows:
            try:
                added = json.loads(row[1]).get("genre_added")
            except (TypeError, ValueError, AttributeError):
                continue
            if isinstance(added, list) and added:
                found.append(str(row[0]))
        return found


def _final_title(metadata_json: object, confirmed: object) -> str:
    if confirmed:
        return str(confirmed)
    try:
        titles = json.loads(str(metadata_json)).get("title") or []
    except (TypeError, ValueError, AttributeError):
        return ""
    return str(titles[0]) if titles else ""

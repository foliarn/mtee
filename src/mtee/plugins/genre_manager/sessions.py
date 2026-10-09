"""Persistent source sessions and batched rows for Genre Manager."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.plugins.genre_manager.repository import _now


class GenreSessionRepository:
    """Snapshot one source's track IDs without tying the session to file paths."""

    def __init__(
        self,
        database: Database,
        library: LibraryRepository,
        playlists: PlaylistsRepository,
    ) -> None:
        self._database = database
        self._library = library
        self._playlists = playlists

    def source_options(self) -> list[dict[str, Any]]:
        """Folder and playlist completion, computed in bulk on a worker thread."""
        connection = self._database.connection()
        folder_counts: dict[tuple[str, str], list[int]] = {}
        for row in connection.execute(
            "SELECT rt.root_id,rt.relative_path,"
            "CASE WHEN s.reviewed_revision=s.genre_revision AND s.reviewed_revision IS NOT NULL "
            "THEN 1 ELSE 0 END AS reviewed "
            "FROM root_tracks rt LEFT JOIN gm_track_state s ON s.track_id=rt.track_id "
            "WHERE rt.present=1"
        ):
            parent = str(PurePosixPath(str(row["relative_path"])).parent)
            if parent == ".":
                parent = ""
            counts = folder_counts.setdefault((str(row["root_id"]), parent), [0, 0])
            counts[0] += 1
            counts[1] += int(row["reviewed"])
        options = []
        for root in self._library.roots():
            root_id = str(root["id"])
            for folder in self._library.folders(root_id):
                total, reviewed = folder_counts.get((root_id, folder), [0, 0])
                options.append(
                    {
                        "kind": "folder",
                        "rootId": root_id,
                        "key": folder,
                        "name": folder.rsplit("/", 1)[-1] if folder else str(root["name"]),
                        "path": folder,
                        "count": total,
                        "reviewed": reviewed,
                        "completion": round(100 * reviewed / total) if total else 0,
                    }
                )
        playlist_counts = {
            str(row["playlist_id"]): (int(row["total"]), int(row["reviewed"]))
            for row in connection.execute(
                "SELECT e.playlist_id,COUNT(*) AS total,"
                "SUM(CASE WHEN s.reviewed_revision=s.genre_revision "
                "AND s.reviewed_revision IS NOT NULL THEN 1 ELSE 0 END) AS reviewed "
                "FROM playlist_entries e LEFT JOIN gm_track_state s ON s.track_id=e.track_id "
                "GROUP BY e.playlist_id"
            )
        }
        for playlist in self._playlists.playlists():
            playlist_id = str(playlist["playlist_id"])
            total, reviewed = playlist_counts.get(playlist_id, (0, 0))
            options.append(
                {
                    "kind": "playlist",
                    "rootId": "",
                    "key": playlist_id,
                    "name": str(playlist["name"]),
                    "path": "",
                    "count": total,
                    "reviewed": reviewed,
                    "completion": round(100 * reviewed / total) if total else 0,
                }
            )
        return options

    def open_source(
        self,
        kind: str,
        key: str,
        *,
        root_id: str = "",
        include_subfolders: bool = False,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if kind not in {"folder", "playlist"}:
            raise ValueError("Choose a folder or playlist")
        candidates = [
            option
            for option in self.source_options()
            if option["kind"] == kind and option["key"] == key and option["rootId"] == root_id
        ]
        if not candidates:
            raise LookupError("Source is no longer available")
        source = candidates[0]
        identity = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"mtee/gm/{kind}/{root_id}/{key}/{include_subfolders}")
        )
        connection = self._database.connection()
        previous = connection.execute(
            "SELECT * FROM gm_sessions WHERE session_id=?", (identity,)
        ).fetchone()
        if previous is not None and not refresh:
            return dict(previous)
        if kind == "folder":
            if include_subfolders:
                track_ids = self._library.track_ids_in_tree(root_id, key)
            else:
                track_ids = [row["id"] for row in self._library.tracks_in_folder(root_id, key)]
        else:
            track_ids = [
                str(entry["track_id"])
                for entry in self._playlists.entries(key)
                if entry["track_id"] is not None
            ]
        present = {row["id"] for row in self._library.tracks_by_ids(track_ids)}
        track_ids = [track_id for track_id in dict.fromkeys(track_ids) if track_id in present]
        with self._database.transaction() as transaction:
            if previous is None:
                transaction.execute(
                    "INSERT INTO gm_sessions(session_id,source_kind,root_id,source_key,"
                    "source_label,include_subfolders,created_at_utc,updated_at_utc) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (
                        identity,
                        kind,
                        root_id or None,
                        key,
                        source["name"],
                        int(include_subfolders),
                        _now(),
                        _now(),
                    ),
                )
            else:
                transaction.execute(
                    "UPDATE gm_sessions SET source_label=?,updated_at_utc=? WHERE session_id=?",
                    (source["name"], _now(), identity),
                )
                transaction.execute("DELETE FROM gm_session_tracks WHERE session_id=?", (identity,))
            transaction.executemany(
                "INSERT INTO gm_session_tracks(session_id,track_id,position) VALUES(?,?,?)",
                [(identity, track_id, index) for index, track_id in enumerate(track_ids)],
            )
        return dict(
            connection.execute(
                "SELECT * FROM gm_sessions WHERE session_id=?", (identity,)
            ).fetchone()
        )

    def latest_session(self) -> dict[str, Any] | None:
        row = (
            self._database.connection()
            .execute("SELECT * FROM gm_sessions ORDER BY updated_at_utc DESC LIMIT 1")
            .fetchone()
        )
        return dict(row) if row is not None else None

    def save_view(
        self,
        session_id: str,
        *,
        view_mode: str,
        interaction_mode: str,
        search_text: str,
        selected_ids: Sequence[str],
        brush_kind: str,
        brush_id: str,
    ) -> None:
        if view_mode not in {"all", "to_review"}:
            raise ValueError("Unknown review filter")
        if interaction_mode not in {"selection", "brush"} or brush_kind not in {"genre", "tag"}:
            raise ValueError("Unknown interaction mode")
        with self._database.transaction() as connection:
            changed = connection.execute(
                "UPDATE gm_sessions SET view_mode=?,interaction_mode=?,search_text=?,"
                "selected_json=?,brush_kind=?,brush_id=?,updated_at_utc=? WHERE session_id=?",
                (
                    view_mode,
                    interaction_mode,
                    search_text,
                    json.dumps(list(dict.fromkeys(selected_ids))),
                    brush_kind,
                    brush_id,
                    _now(),
                    session_id,
                ),
            ).rowcount
            if changed != 1:
                raise KeyError(session_id)

    def rows(self, session_id: str) -> list[dict[str, Any]]:
        ids = [
            str(row[0])
            for row in self._database.connection().execute(
                "SELECT track_id FROM gm_session_tracks WHERE session_id=? ORDER BY position",
                (session_id,),
            )
        ]
        rows = self._library.tracks_by_ids(ids)
        if not rows:
            return []
        decisions: dict[str, dict[str, Any]] = {
            identity: {
                "genres": [],
                "tags": [],
                "genreRevision": 0,
                "tagRevision": 0,
                "reviewed": False,
            }
            for identity in ids
        }
        connection = self._database.connection()
        for chunk_start in range(0, len(ids), 400):
            chunk = ids[chunk_start : chunk_start + 400]
            marks = ",".join("?" * len(chunk))
            for state in connection.execute(
                "SELECT track_id,genre_revision,tag_revision,reviewed_revision "
                f"FROM gm_track_state WHERE track_id IN ({marks})",
                chunk,
            ):
                item = decisions[str(state["track_id"])]
                item["genreRevision"] = int(state["genre_revision"])
                item["tagRevision"] = int(state["tag_revision"])
                item["reviewed"] = state["reviewed_revision"] == state["genre_revision"]
            for assignment in connection.execute(
                "SELECT track_id,genre_id FROM gm_track_genres "
                f"WHERE track_id IN ({marks}) ORDER BY track_id,position",
                chunk,
            ):
                decisions[str(assignment["track_id"])]["genres"].append(str(assignment["genre_id"]))
            for assignment in connection.execute(
                "SELECT track_id,tag_id FROM gm_track_tags "
                f"WHERE track_id IN ({marks}) ORDER BY track_id,tag_id",
                chunk,
            ):
                decisions[str(assignment["track_id"])]["tags"].append(str(assignment["tag_id"]))
        return [row | decisions[row["id"]] for row in rows]

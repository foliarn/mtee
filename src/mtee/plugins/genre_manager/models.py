"""Qt boundary for the bundled Genre Manager page."""

# Qt properties and slots use the camelCase names consumed by QML.
# ruff: noqa: N802

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from mtee.models.track_list_model import TrackListModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.plugins.genre_manager.artist_attribution import ArtistAttribution
from mtee.plugins.genre_manager.organizer import GenreOrganizer
from mtee.plugins.genre_manager.repository import GenreManagerRepository
from mtee.plugins.genre_manager.service import GenreManagerService
from mtee.plugins.genre_manager.sessions import GenreSessionRepository
from mtee.services.file_access import FileAccessCoordinator


class _ResultBridge(QObject):
    ready = Signal(int, object)


class GenreManagerModel(QObject):
    """Expose typed intentions; SQL and large source reads stay on a worker."""

    changed = Signal()

    def __init__(
        self,
        database: Database,
        library: LibraryRepository,
        playlists: PlaylistsRepository,
        file_access: FileAccessCoordinator | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._database = database
        repository = GenreManagerRepository(database)
        self._repository = repository
        self._service = GenreManagerService(repository)
        self._sessions = GenreSessionRepository(database, library, playlists)
        self._organizer = GenreOrganizer(
            database, library, self._sessions, file_access or FileAccessCoordinator()
        )
        self._attribution = ArtistAttribution(database)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mtee-genre-manager")
        self._bridge = _ResultBridge(self)
        self._bridge.ready.connect(self._on_result)
        self._generation = 0
        self._busy = False
        self._error = ""
        self._message = ""
        self._genres: list[dict[str, Any]] = []
        self._tags: list[dict[str, Any]] = []
        self._sources: list[dict[str, Any]] = []
        self._session: dict[str, Any] = {}
        self._all_rows: list[dict[str, Any]] = []
        self._rows_model = TrackListModel(self)
        self._selected: list[str] = []
        self._anchor = ""
        self._view_mode = "all"
        self._interaction_mode = "selection"
        self._search = ""
        self._brush_kind = "genre"
        self._brush_id = ""
        self._last_operations: list[str] = []
        self._organize_preview: dict[str, Any] = {}
        self._organize_result: dict[str, Any] = {}
        self._last_organization_id = ""
        self._organization_cancel = Event()
        self._organize_moving = False
        self._uncertainties: list[dict[str, Any]] = []
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._save_view)
        self.refresh()

    @Property(QObject, notify=changed)
    def rowsModel(self) -> QObject:
        return self._rows_model

    @Property(dict, notify=changed)
    def state(self) -> dict[str, Any]:
        session = self._session
        reviewed = sum(bool(row["reviewed"]) for row in self._all_rows)
        return {
            "busy": self._busy,
            "error": self._error,
            "message": self._message,
            "genres": self._genres,
            "tags": self._tags,
            "sources": self._sources,
            "sessionId": str(session.get("session_id", "")),
            "sourceKind": str(session.get("source_kind", "")),
            "sourceLabel": str(session.get("source_label", "Choose source")),
            "sourceKey": str(session.get("source_key", "")),
            "rootId": str(session.get("root_id") or ""),
            "total": len(self._all_rows),
            "reviewed": reviewed,
            "selectedIds": list(self._selected),
            "viewMode": self._view_mode,
            "interactionMode": self._interaction_mode,
            "search": self._search,
            "brushKind": self._brush_kind,
            "brushId": self._brush_id,
            "canUndo": bool(self._last_operations),
            "organizePreview": self._organize_preview,
            "organizeResult": self._organize_result,
            "canUndoOrganization": bool(self._last_organization_id),
            "organizeMoving": self._organize_moving,
            "uncertainties": self._uncertainties,
        }

    def _submit(self, work: Any) -> None:
        self._generation += 1
        generation = self._generation
        self._busy = True
        self._error = ""
        self.changed.emit()
        self._executor.submit(self._run, generation, work)

    def _run(self, generation: int, work: Any) -> None:
        try:
            payload = work()
        except Exception as error:
            try:
                payload = self._snapshot() | {"error": f"{type(error).__name__}: {error}"}
            except Exception:
                payload = {"error": f"{type(error).__name__}: {error}"}
        self._bridge.ready.emit(generation, payload)

    def _snapshot(self, session: dict[str, Any] | None = None, message: str = "") -> dict[str, Any]:
        self._service.ensure_catalogue()
        selected_session = session if session is not None else self._sessions.latest_session()
        rows = (
            self._sessions.rows(str(selected_session["session_id"]))
            if selected_session is not None
            else []
        )
        return {
            "session": selected_session or {},
            "rows": rows,
            "genres": self._repository.genres(),
            "tags": self._repository.tags(),
            "sources": self._sessions.source_options(),
            "message": message,
        }

    @Slot(int, object)
    def _on_result(self, generation: int, payload: object) -> None:
        if generation != self._generation or not isinstance(payload, dict):
            return
        self._busy = False
        self._organize_moving = False
        error = payload.get("error")
        self._error = str(error) if error else ""
        if "rows" not in payload:
            self.changed.emit()
            return
        self._message = str(payload.get("message", ""))
        if "operations" in payload:
            self._last_operations = list(payload["operations"])
        if "organizePreview" in payload:
            self._organize_preview = dict(payload["organizePreview"])
        if "organizeResult" in payload:
            self._organize_result = dict(payload["organizeResult"])
        if "lastOrganizationId" in payload:
            self._last_organization_id = str(payload["lastOrganizationId"])
        if "uncertainties" in payload:
            self._uncertainties = list(payload["uncertainties"])
        self._genres = list(payload["genres"])
        self._tags = list(payload["tags"])
        self._sources = list(payload["sources"])
        old_session = str(self._session.get("session_id", ""))
        self._session = dict(payload["session"])
        self._all_rows = list(payload["rows"])
        if str(self._session.get("session_id", "")) != old_session:
            self._view_mode = str(self._session.get("view_mode", "all"))
            self._interaction_mode = str(self._session.get("interaction_mode", "selection"))
            self._search = str(self._session.get("search_text", ""))
            self._brush_kind = str(self._session.get("brush_kind", "genre"))
            self._brush_id = str(self._session.get("brush_id", ""))
            try:
                self._selected = list(json.loads(self._session.get("selected_json", "[]")))
            except (TypeError, ValueError):
                self._selected = []
        known = {str(row["id"]) for row in self._all_rows}
        self._selected = [track_id for track_id in self._selected if track_id in known]
        self._publish_rows()
        self.changed.emit()

    def _publish_rows(self) -> None:
        search = self._search.casefold().strip()
        visible = [
            row
            for row in self._all_rows
            if (self._view_mode == "all" or not row["reviewed"])
            and (
                not search
                or search in str(row.get("title", "")).casefold()
                or search in str(row.get("artist", "")).casefold()
                or search in str(row.get("filename", "")).casefold()
            )
        ]
        self._rows_model.replace(visible)
        visible_ids = {str(row["id"]) for row in visible}
        self._selected = [track_id for track_id in self._selected if track_id in visible_ids]

    @Slot()
    def refresh(self) -> None:
        self._submit(self._snapshot)

    @Slot(str, str, str, bool)
    def openSource(self, kind: str, key: str, root_id: str, include_subfolders: bool) -> None:
        self._submit(
            lambda: self._snapshot(
                self._sessions.open_source(
                    kind, key, root_id=root_id, include_subfolders=include_subfolders
                )
            )
        )

    @Slot(str)
    def setViewMode(self, mode: str) -> None:
        if mode not in {"all", "to_review"}:
            return
        self._view_mode = mode
        self._publish_rows()
        self.changed.emit()
        self._save_timer.start()

    @Slot(str)
    def setInteractionMode(self, mode: str) -> None:
        if mode not in {"selection", "brush"}:
            return
        self._interaction_mode = mode
        self.changed.emit()
        self._save_timer.start()

    @Slot(str)
    def setSearch(self, value: str) -> None:
        self._search = value
        self._publish_rows()
        self.changed.emit()
        self._save_timer.start()

    @Slot(str, str)
    def setBrush(self, kind: str, identity: str) -> None:
        if kind not in {"genre", "tag"}:
            return
        self._brush_kind = kind
        self._brush_id = identity
        self.changed.emit()
        self._save_timer.start()

    @Slot(str, bool, bool)
    def selectTrack(self, track_id: str, ctrl: bool, shift: bool) -> None:
        visible = self._rows_model.track_ids_snapshot()
        if track_id not in visible:
            return
        if shift and self._anchor in visible:
            first = visible.index(self._anchor)
            last = visible.index(track_id)
            span = visible[min(first, last) : max(first, last) + 1]
            self._selected = list(dict.fromkeys([*self._selected, *span] if ctrl else span))
        elif ctrl:
            self._selected = (
                [item for item in self._selected if item != track_id]
                if track_id in self._selected
                else [*self._selected, track_id]
            )
            self._anchor = track_id
        else:
            self._selected = [track_id]
            self._anchor = track_id
        self.changed.emit()
        self._save_timer.start()

    @Slot()
    def selectVisible(self) -> None:
        self._selected = self._rows_model.track_ids_snapshot()
        self.changed.emit()
        self._save_timer.start()

    @Slot()
    def clearSelection(self) -> None:
        self._selected = []
        self.changed.emit()
        self._save_timer.start()

    def _save_view(self) -> None:
        session_id = str(self._session.get("session_id", ""))
        if not session_id:
            return
        values = (
            self._view_mode,
            self._interaction_mode,
            self._search,
            list(self._selected),
            self._brush_kind,
            self._brush_id,
        )
        self._executor.submit(
            lambda: self._sessions.save_view(
                session_id,
                view_mode=values[0],
                interaction_mode=values[1],
                search_text=values[2],
                selected_ids=values[3],
                brush_kind=values[4],
                brush_id=values[5],
            )
        )

    def _write(self, action: Any, message: str, operations: list[str] | None = None) -> None:
        if self._busy:
            return
        session = dict(self._session)

        def work() -> dict[str, Any]:
            error = ""
            try:
                action()
            except Exception as failure:
                error = f"{type(failure).__name__}: {failure}"
            applied = [
                operation_id
                for operation_id in operations or []
                if self._repository.operation_exists(operation_id)
            ]
            if operations is not None and applied:
                marks = ",".join("?" for _ in applied)
                affected = [
                    str(row[0])
                    for row in self._database.connection().execute(
                        f"SELECT DISTINCT track_id FROM gm_decision_operations "
                        f"WHERE kind IN ('genres','review') AND operation_id IN ({marks})",
                        applied,
                    )
                ]
                self._attribution.refresh(affected)
            return self._snapshot(session, message if not error else "") | {
                "operations": applied,
                "error": error,
            }

        self._submit(work)

    @Slot(str)
    def addGenreToSelection(self, genre_id: str) -> None:
        ids = list(self._selected)
        if not ids:
            return
        revisions = {str(row["id"]): int(row["genreRevision"]) for row in self._all_rows}
        operations = [str(uuid.uuid4()) for _ in ids]

        def action() -> None:
            for track_id, operation_id in zip(ids, operations, strict=True):
                self._service.assign_genre(
                    track_id,
                    genre_id,
                    expected_revision=revisions[track_id],
                    operation_id=operation_id,
                )

        self._write(action, f"Genre added to {len(ids)} tracks", operations)

    @Slot(str)
    def removeGenreFromSelection(self, genre_id: str) -> None:
        ids = list(self._selected)
        revisions = {str(row["id"]): int(row["genreRevision"]) for row in self._all_rows}
        operations = [str(uuid.uuid4()) for _ in ids]

        def action() -> None:
            for track_id, operation_id in zip(ids, operations, strict=True):
                self._service.remove_genre(
                    track_id,
                    genre_id,
                    expected_revision=revisions[track_id],
                    operation_id=operation_id,
                )

        self._write(action, f"Genre removed from {len(ids)} tracks", operations)

    @Slot(str, str)
    def removeGenreFromTrack(self, track_id: str, genre_id: str) -> None:
        row = next((item for item in self._all_rows if item["id"] == track_id), None)
        if row is None:
            return
        operation_id = str(uuid.uuid4())
        self._write(
            lambda: self._service.remove_genre(
                track_id,
                genre_id,
                expected_revision=int(row["genreRevision"]),
                operation_id=operation_id,
            ),
            "Genre removed",
            [operation_id],
        )

    @Slot(str, str, int)
    def moveGenre(self, track_id: str, genre_id: str, direction: int) -> None:
        row = next((item for item in self._all_rows if item["id"] == track_id), None)
        if row is None:
            return
        ordered = list(row["genres"])
        if genre_id not in ordered:
            return
        old = ordered.index(genre_id)
        new = max(0, min(len(ordered) - 1, old + direction))
        if new == old:
            return
        ordered.insert(new, ordered.pop(old))
        operation_id = str(uuid.uuid4())
        self._write(
            lambda: self._repository.set_genres(
                track_id,
                ordered,
                expected_revision=int(row["genreRevision"]),
                operation_id=operation_id,
            ),
            "Genre order updated",
            [operation_id],
        )

    @Slot(str, str, bool)
    def paint(self, track_id: str, identity: str, present: bool) -> None:
        row = next((item for item in self._all_rows if item["id"] == track_id), None)
        if row is None or not identity:
            return
        operation_id = str(uuid.uuid4())
        if self._brush_kind == "tag":
            self._write(
                lambda: self._repository.set_tag(
                    track_id,
                    identity,
                    present=present,
                    expected_revision=int(row["tagRevision"]),
                    operation_id=operation_id,
                ),
                "Tag updated",
                [operation_id],
            )
        else:

            def action() -> None:
                if present:
                    self._service.assign_genre(
                        track_id,
                        identity,
                        expected_revision=int(row["genreRevision"]),
                        operation_id=operation_id,
                    )
                else:
                    self._service.remove_genre(
                        track_id,
                        identity,
                        expected_revision=int(row["genreRevision"]),
                        operation_id=operation_id,
                    )

            self._write(action, "Genre updated", [operation_id])

    @Slot(str)
    def addTagToSelection(self, tag_id: str) -> None:
        ids = list(self._selected)
        revisions = {str(row["id"]): int(row["tagRevision"]) for row in self._all_rows}
        operations = [str(uuid.uuid4()) for _ in ids]

        def action() -> None:
            for track_id, operation_id in zip(ids, operations, strict=True):
                self._repository.set_tag(
                    track_id,
                    tag_id,
                    present=True,
                    expected_revision=revisions[track_id],
                    operation_id=operation_id,
                )

        self._write(action, f"Tag added to {len(ids)} tracks", operations)

    @Slot(str)
    def removeTagFromSelection(self, tag_id: str) -> None:
        ids = list(self._selected)
        revisions = {str(row["id"]): int(row["tagRevision"]) for row in self._all_rows}
        operations = [str(uuid.uuid4()) for _ in ids]

        def action() -> None:
            for track_id, operation_id in zip(ids, operations, strict=True):
                self._repository.set_tag(
                    track_id,
                    tag_id,
                    present=False,
                    expected_revision=revisions[track_id],
                    operation_id=operation_id,
                )

        self._write(action, f"Tag removed from {len(ids)} tracks", operations)

    @Slot()
    def markSelectedReviewed(self) -> None:
        ids = list(self._selected)
        revisions = {str(row["id"]): int(row["genreRevision"]) for row in self._all_rows}
        operations = [str(uuid.uuid4()) for _ in ids]

        def action() -> None:
            for track_id, operation_id in zip(ids, operations, strict=True):
                self._repository.mark_reviewed(
                    track_id,
                    expected_revision=revisions[track_id],
                    operation_id=operation_id,
                )

        self._write(action, f"Marked {len(ids)} tracks as reviewed", operations)

    @Slot()
    def undo(self) -> None:
        operations = list(self._last_operations)
        if not operations:
            return

        def action() -> None:
            for operation_id in reversed(operations):
                self._repository.undo(operation_id)
            self._attribution.refresh()

        self._write(action, "Last decision undone", [])

    @Slot(str)
    def assignGenreToSource(self, genre_id: str) -> None:
        if self._session.get("source_kind") != "folder":
            return
        rows = list(self._all_rows)
        operations = [str(uuid.uuid4()) for _ in rows]

        def action() -> None:
            for row, operation_id in zip(rows, operations, strict=True):
                self._service.assign_genre(
                    str(row["id"]),
                    genre_id,
                    expected_revision=int(row["genreRevision"]),
                    operation_id=operation_id,
                )

        self._write(action, f"Genre applied to {len(rows)} folder tracks", operations)

    @Slot(str, str)
    def makePrimary(self, track_id: str, genre_id: str) -> None:
        row = next((item for item in self._all_rows if item["id"] == track_id), None)
        if row is None:
            return
        operation_id = str(uuid.uuid4())
        self._write(
            lambda: self._service.make_primary(
                track_id,
                genre_id,
                expected_revision=int(row["genreRevision"]),
                operation_id=operation_id,
            ),
            "Main genre changed",
            [operation_id],
        )

    @Slot(str, str)
    def createGenre(self, name: str, parent_id: str) -> None:
        self._write(
            lambda: self._repository.create_genre(name, parent_id or None),
            f"{name.strip()} created",
        )

    @Slot(str, str)
    def renameGenre(self, genre_id: str, name: str) -> None:
        self._write(lambda: self._repository.rename_genre(genre_id, name), "Genre renamed")

    @Slot(str, bool)
    def setGenreArchived(self, genre_id: str, archived: bool) -> None:
        self._write(
            lambda: self._repository.set_genre_archived(genre_id, archived),
            "Genre archived" if archived else "Genre restored",
        )

    @Slot(str)
    def createTag(self, name: str) -> None:
        self._write(lambda: self._repository.create_tag(name), f"{name.strip()} created")

    @Slot()
    def openOrganize(self) -> None:
        session = dict(self._session)
        if not session.get("session_id"):
            return

        def work() -> dict[str, Any]:
            self._organizer.recover()
            preview = self._organizer.preview(str(session["session_id"]))
            return self._snapshot(session) | {
                "organizePreview": preview,
                "organizeResult": {},
                "lastOrganizationId": self._organizer.latest_undoable(str(session["session_id"])),
            }

        self._submit(work)

    @Slot(str, str, str)
    def setDestination(self, root_id: str, genre_id: str, relative_folder: str) -> None:
        session = dict(self._session)

        def work() -> dict[str, Any]:
            self._organizer.set_destination(root_id, genre_id, relative_folder)
            preview = self._organizer.preview(str(session["session_id"]))
            return self._snapshot(session, "Destination saved") | {
                "organizePreview": preview,
                "organizeResult": {},
            }

        self._submit(work)

    @Slot()
    def moveReviewedFiles(self) -> None:
        if self._busy:
            return
        preview = dict(self._organize_preview)
        operation_id = str(preview.get("operationId", ""))
        if not operation_id or not preview.get("ready"):
            return
        session = dict(self._session)
        self._organization_cancel.clear()
        self._organize_moving = True

        def work() -> dict[str, Any]:
            result = self._organizer.apply(
                operation_id, should_cancel=self._organization_cancel.is_set
            )
            return self._snapshot(session, "Organization finished") | {
                "organizePreview": preview,
                "organizeResult": result,
                "lastOrganizationId": operation_id if result["moved"] else "",
            }

        self._submit(work)

    @Slot()
    def cancelOrganization(self) -> None:
        if self._organize_moving:
            self._organization_cancel.set()

    @Slot()
    def undoOrganization(self) -> None:
        if not self._last_organization_id:
            return
        session = dict(self._session)
        operation_id = self._last_organization_id

        def work() -> dict[str, Any]:
            preview = self._organizer.prepare_undo(operation_id)
            return self._snapshot(session, "Check the inverse moves before confirming") | {
                "organizePreview": preview,
                "organizeResult": {},
                "lastOrganizationId": "",
            }

        self._submit(work)

    @Slot()
    def openUncertain(self) -> None:
        session = dict(self._session)

        def work() -> dict[str, Any]:
            self._attribution.refresh()
            return self._snapshot(session) | {
                "uncertainties": self._attribution.uncertainties(),
            }

        self._submit(work)

    @Slot(str, list)
    def chooseArtistContributors(self, track_id: str, artist_ids: list[str]) -> None:
        session = dict(self._session)

        def work() -> dict[str, Any]:
            self._attribution.choose(track_id, artist_ids)
            return self._snapshot(session, "Artist contribution saved") | {
                "uncertainties": self._attribution.uncertainties(),
            }

        self._submit(work)

    @Slot(str, result=list)
    def artistGenres(self, artist_id: str) -> list[dict[str, Any]]:
        return self._attribution.artist_genres(artist_id)

    @Slot()
    def close(self) -> None:
        self._save_timer.stop()
        self._save_view()
        self._executor.shutdown(wait=True)

"""Qt models of the artist manager: its state, its lists and its long operations.

QML never reaches the database or the files. The lists and the state are read in a
worker thread and delivered to the graphical thread; confirmations are applied by jobs
of the job service, which report progress, errors per track and cancellation.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from mtee.domain.artists import normalize_key
from mtee.domain.jobs import JobState
from mtee.models.analysis_model import AnalysisModel
from mtee.services.artist_manager_service import ArtistManagerError, ArtistManagerService
from mtee.services.jobs import JobContext, JobService

__all__ = ["ArtistListModel", "ArtistManagerModel", "NullArtistManager"]

_REFRESH_INTERVAL_MS = 400
_APPLY_PREFIX = "Apply artists"


class ArtistApplyError(RuntimeError):
    """Some tracks of a confirmation could not be applied; they stay queued."""

    code = "artist_apply_incomplete"


class _Bridge(QObject):
    """Carry worker-thread results to the graphical thread."""

    stateReady = Signal(int, object)
    rowsReady = Signal(object, int, object)
    previewReady = Signal(object)
    itemDone = Signal(str)
    finished = Signal(str)


_TRACK_ROLES = (
    "trackId",
    "filename",
    "title",
    "artists",
    "credits",
    "category",
    "reviewState",
    "applyState",
    "applyError",
    "applyNote",
    "note",
    "incomplete",
    "version",
    "path",
)
_ARTIST_ROLES = ("artistId", "name", "tracks", "trackIds", "unavailable")


class ArtistListModel(QAbstractListModel):
    """One list of the manager: tracks or artists of a category, or the catalog."""

    countChanged = Signal()
    loadingChanged = Signal()
    searchChanged = Signal()

    def __init__(self, manager: ArtistManagerModel, key: str) -> None:
        super().__init__(manager)
        self._manager = manager
        self._key = key
        self._kind = "catalog" if key == "catalog" else key.partition(".")[2]
        self._category = "" if key == "catalog" else key.partition(".")[0]
        self._all: list[dict[str, Any]] = []
        self._rows: list[dict[str, Any]] = []
        self._search = ""
        self._sort_key = "filename" if self._kind == "tracks" else "artist"
        self._ascending = True
        self._loading = False
        self._generation = 0
        names = _TRACK_ROLES if self._kind == "tracks" else _ARTIST_ROLES
        self._role_names = {
            Qt.ItemDataRole.UserRole + 1 + index: name for index, name in enumerate(names)
        }

    # ----------------------------------------------------------------- QAbstractListModel

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name.encode()) for role, name in self._role_names.items()}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_names.get(role)
        if name is None:
            return None
        return self._rows[index.row()].get(name if name != "artistId" else "id")

    # -------------------------------------------------------------------- properties

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._rows)

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, constant=True)
    def key(self) -> str:
        return self._key

    @Property(str, constant=True)
    def category(self) -> str:
        return self._category

    @Property(str, constant=True)
    def kind(self) -> str:
        return self._kind

    @Property(str, notify=countChanged)
    def sortKey(self) -> str:
        return self._sort_key

    @Property(bool, notify=countChanged)
    def sortAscending(self) -> bool:
        return self._ascending

    @Property(int, notify=countChanged)
    def totalCount(self) -> int:
        return len(self._all)

    @Property(int, notify=countChanged)
    def trackTotal(self) -> int:
        """Distinct tracks behind the visible rows (an artist list shows artists)."""
        if self._kind == "tracks":
            return len(self._rows)
        return len({track_id for row in self._rows for track_id in row.get("trackIds", [])})

    # ----------------------------------------------------------------------- actions

    @Slot(str)
    def setSearch(self, text: str) -> None:
        text = str(text)
        if text == self._search:
            return
        self._search = text
        self.searchChanged.emit()
        self._apply()

    @Slot(str)
    def toggleSort(self, key: str) -> None:
        if key == self._sort_key:
            self._ascending = not self._ascending
        else:
            self._sort_key = key
            self._ascending = True
        self._apply()

    @Slot()
    def reload(self) -> None:
        self._generation += 1
        self._set_loading(True)
        self._manager.request_rows(self, self._generation)

    @Property(str, notify=searchChanged)
    def searchText(self) -> str:
        return self._search

    def spec(self) -> tuple[str, str, str]:
        return self._category, self._kind, self._key

    def search_text(self) -> str:
        return self._search

    # ---------------------------------------------------------------------- internals

    def accept(self, generation: int, rows: list[dict[str, Any]]) -> None:
        if generation != self._generation:
            return
        self._all = rows
        self._set_loading(False)
        self._apply()

    def _set_loading(self, value: bool) -> None:
        if self._loading != value:
            self._loading = value
            self.loadingChanged.emit()

    def _visible(self) -> list[dict[str, Any]]:
        needle = normalize_key(self._search)
        rows = self._all
        if needle:
            if self._kind == "tracks":
                rows = [
                    row
                    for row in rows
                    if needle in normalize_key(f"{row['filename']} {row['title']} {row['artists']}")
                ]
            else:
                rows = [row for row in rows if needle in normalize_key(row["name"])]
        if self._kind == "tracks":
            if self._sort_key == "artist":
                rows = sorted(
                    rows,
                    key=lambda row: (
                        normalize_key(row["artists"]) or "￿",
                        row["filename"].casefold(),
                    ),
                )
            else:
                rows = sorted(rows, key=lambda row: row["filename"].casefold())
        elif self._sort_key == "tracks":
            rows = sorted(rows, key=lambda row: (row["tracks"], row["name"].casefold()))
        else:
            rows = sorted(rows, key=lambda row: row["name"].casefold())
        if not self._ascending:
            rows = list(reversed(rows))
        return rows

    @staticmethod
    def _identity(row: dict[str, Any]) -> str:
        return str(row.get("trackId") or row.get("id") or "")

    def _apply(self) -> None:
        new_rows = self._visible()
        old_ids = [self._identity(row) for row in self._rows]
        new_ids = [self._identity(row) for row in new_rows]
        wanted = set(new_ids)
        common_old = [identity for identity in old_ids if identity in wanted]
        known = set(old_ids)
        common_new = [identity for identity in new_ids if identity in known]
        if common_old != common_new:
            self.beginResetModel()
            self._rows = new_rows
            self.endResetModel()
            self.countChanged.emit()
            return
        for position in range(len(self._rows) - 1, -1, -1):
            if old_ids[position] not in wanted:
                self.beginRemoveRows(QModelIndex(), position, position)
                del self._rows[position]
                self.endRemoveRows()
        for position, row in enumerate(new_rows):
            if (
                position < len(self._rows)
                and self._identity(self._rows[position]) == new_ids[position]
            ):
                if self._rows[position] != row:
                    self._rows[position] = row
                    cell = self.index(position)
                    self.dataChanged.emit(cell, cell)
            else:
                self.beginInsertRows(QModelIndex(), position, position)
                self._rows.insert(position, row)
                self.endInsertRows()
        self.countChanged.emit()


class ArtistManagerModel(QObject):
    """State, lists and operations of the artist manager, exposed to QML."""

    stateChanged = Signal()
    busyChanged = Signal()
    noticeRaised = Signal(str)
    confirmationReady = Signal("QVariantMap")
    tracksChanged = Signal(list)

    def __init__(
        self,
        service: ArtistManagerService,
        jobs: JobService,
        analysis: AnalysisModel | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._jobs = jobs
        self._analysis = analysis
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mtee-artists")
        self._bridge = _Bridge(self)
        queued = Qt.ConnectionType.QueuedConnection
        self._bridge.stateReady.connect(self._on_state, queued)
        self._bridge.rowsReady.connect(self._on_rows, queued)
        self._bridge.previewReady.connect(self._on_preview, queued)
        self._bridge.itemDone.connect(self._on_item_done, queued)
        self._bridge.finished.connect(self._on_finished, queued)
        self._state: dict[str, Any] = {}
        self._state_generation = 0
        self._models: dict[str, ArtistListModel] = {}
        self._analyzing = False
        self._applying = False
        self._changed_tracks: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._item_timer = QTimer(self)
        self._item_timer.setSingleShot(True)
        self._item_timer.setInterval(_REFRESH_INTERVAL_MS)
        self._item_timer.timeout.connect(self._flush_changed_tracks)
        jobs.jobSubmitted.connect(self._on_job_event)
        jobs.jobUpdated.connect(self._on_job_event)
        if analysis is not None:
            analysis.resultsChanged.connect(self._schedule_refresh)
        self.refresh()

    @property
    def service(self) -> ArtistManagerService:
        return self._service

    def artist_name(self, artist_id: str) -> str:
        """Return the name of a profile, ``""`` when it no longer exists."""
        artist = self._service.repository.artist(artist_id)
        return str(artist["name"]) if artist else ""

    # ---------------------------------------------------------------------- properties

    @Property(bool, constant=True)
    def available(self) -> bool:
        return True

    @Property("QVariantMap", notify=stateChanged)
    def state(self) -> dict[str, Any]:
        return self._state

    @Property(bool, notify=busyChanged)
    def analyzing(self) -> bool:
        return self._analyzing

    @Property(bool, notify=busyChanged)
    def applying(self) -> bool:
        return self._applying

    # ----------------------------------------------------------------------- refreshing

    @Slot()
    def refresh(self) -> None:
        """Reload the state and every list that a view currently holds."""
        self._state_generation += 1
        generation = self._state_generation
        self._executor.submit(self._read_state, generation)
        for model in self._models.values():
            model.reload()

    @Slot()
    def _schedule_refresh(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def _read_state(self, generation: int) -> None:
        try:
            state = self._service.state()
        except Exception as error:
            state = {"error": f"{type(error).__name__}: {error}"}
        self._bridge.stateReady.emit(generation, state)

    @Slot(int, object)
    def _on_state(self, generation: int, state: object) -> None:
        if generation != self._state_generation or not isinstance(state, dict):
            return
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    def request_rows(self, model: ArtistListModel, generation: int) -> None:
        category, kind, key = model.spec()
        self._executor.submit(self._read_rows, model, key, category, kind, generation)

    def _read_rows(
        self, model: ArtistListModel, key: str, category: str, kind: str, generation: int
    ) -> None:
        try:
            if kind == "tracks":
                rows = self._service.track_rows(category)
            elif kind == "artists":
                rows = self._service.artist_rows(category)
            else:
                rows = [{**row, "unavailable": False} for row in self._service.catalog()]
        except Exception:
            rows = []
        self._bridge.rowsReady.emit(model, generation, rows)

    @Slot(object, int, object)
    def _on_rows(self, model: object, generation: int, rows: object) -> None:
        if isinstance(model, ArtistListModel) and isinstance(rows, list):
            model.accept(generation, rows)

    @Slot(str, result=QObject)
    def listModel(self, key: str) -> QObject:
        """Return the list of a view (``from_tags.tracks``, ``suggested.artists``, ``catalog``)."""
        model = self._models.get(key)
        if model is None:
            model = ArtistListModel(self, key)
            self._models[key] = model
            model.reload()
        return model

    # ------------------------------------------------------------------------ analysis

    @Slot()
    def analyzeCollection(self) -> None:
        if self._analysis is None:
            self.noticeRaised.emit("Analysis is not available.")
            return
        self._analysis.analyzeCollection()

    # -------------------------------------------------------------------------- edit

    @Slot(str, result="QVariantMap")
    def editInfo(self, track_id: str) -> dict[str, Any]:
        return self._service.edit_info(track_id)

    @Slot(str, result="QVariantList")
    def suggest(self, query: str) -> list[dict[str, Any]]:
        return self._service.suggestions(query)

    @Slot(str, list, str, result="QVariantMap")
    def previewName(self, track_id: str, names: list, title: str) -> dict[str, Any]:
        return self._service.preview_name(track_id, [str(name) for name in names], str(title))

    @Slot(str, str, list, bool, result="QVariantMap")
    def saveEdit(
        self, track_id: str, title: str, entries: list, to_needs_input: bool
    ) -> dict[str, Any]:
        """Save the draft of a track; ``entries`` holds ``{id, name}`` per artist line."""
        pairs = [
            (str(entry.get("id", "")), str(entry.get("name", "")))
            for entry in entries
            if isinstance(entry, dict)
        ]
        try:
            self._service.save_edit(track_id, title, pairs, to_needs_input=bool(to_needs_input))
        except ArtistManagerError as error:
            return {"ok": False, "error": str(error)}
        except Exception as error:
            return {"ok": False, "error": f"The change could not be saved: {error}"}
        self.refresh()
        return {"ok": True, "error": ""}

    # ------------------------------------------------------------------ confirmation

    @Slot(str, str, str)
    def requestConfirmation(self, category: str, scope: str, search: str) -> None:
        """Freeze the scope of the current filter; ``confirmationReady`` delivers it."""

        def work() -> None:
            try:
                preview = self._service.preview_confirmation(category, scope, search).as_dict()
            except Exception as error:
                preview = {
                    "category": category,
                    "scope": scope,
                    "blocked": f"The lot could not be prepared: {error}",
                    "items": [],
                }
            self._bridge.previewReady.emit(preview)

        self._executor.submit(work)

    @Slot(object)
    def _on_preview(self, preview: object) -> None:
        if isinstance(preview, dict):
            self.confirmationReady.emit(preview)

    @Slot(list, bool, str, result="QVariantMap")
    def confirm(self, items: list, write_tags: bool, label: str) -> dict[str, Any]:
        """Stage the frozen lot, then apply it in a job."""
        frozen = [(str(entry[0]), int(entry[1])) for entry in items if len(entry) == 2]
        try:
            result = self._service.stage(frozen, write_tags=bool(write_tags), label=str(label))
        except ArtistManagerError as error:
            return {"ok": False, "error": str(error)}
        self._submit_apply(result.operation_id, f"{_APPLY_PREFIX}: {len(result.staged)} tracks")
        self.refresh()
        return {"ok": True, "error": ""}

    # ------------------------------------------------------------------ artist actions

    @Slot(str, result="QVariantMap")
    def artistImpact(self, artist_id: str) -> dict[str, Any]:
        try:
            return self._service.impact(artist_id)
        except ArtistManagerError as error:
            return {"name": "", "confirmedTracks": 0, "error": str(error)}

    @Slot(str, str, bool, result="QVariantMap")
    def renameArtist(self, artist_id: str, name: str, write_tags: bool) -> dict[str, Any]:
        return self._run_artist_operation(
            lambda: self._service.rename_artist(artist_id, name, write_tags=bool(write_tags)),
            "Rename artist",
        )

    @Slot(str, str, bool, result="QVariantMap")
    def mergeArtist(self, artist_id: str, destination_id: str, write_tags: bool) -> dict[str, Any]:
        return self._run_artist_operation(
            lambda: self._service.merge_artist(
                artist_id, destination_id, write_tags=bool(write_tags)
            ),
            "Merge artists",
        )

    @Slot(str, bool, result="QVariantMap")
    def deleteArtist(self, artist_id: str, remove_from_tags: bool) -> dict[str, Any]:
        return self._run_artist_operation(
            lambda: self._service.delete_artist(artist_id, remove_from_tags=bool(remove_from_tags)),
            "Delete artist",
        )

    def _run_artist_operation(self, action: Any, label: str) -> dict[str, Any]:
        try:
            outcome = action()
        except ArtistManagerError as error:
            return {"ok": False, "error": str(error)}
        operation_id = str(outcome.get("operationId", ""))
        if operation_id:
            self._submit_apply(operation_id, f"{_APPLY_PREFIX}: {label}")
        self.refresh()
        return {"ok": True, "error": ""}

    # ---------------------------------------------------------------------- jobs

    def _submit_apply(self, operation_id: str, label: str) -> None:
        files = self._service.files

        def task(context: JobContext) -> None:
            summary = files.apply_operation(
                operation_id,
                is_cancelled=lambda: context.is_cancelled,
                report_items=context.report_items,
                report_failure=context.report_failure,
                on_item_done=self._bridge.itemDone.emit,
            )
            self._bridge.finished.emit(operation_id)
            if summary.failed:
                raise ArtistApplyError(
                    f"{summary.failed} tracks could not be applied. They stay in the list."
                )

        self._jobs.submit(task, label=label)

    @Slot()
    def retryUnfinished(self) -> None:
        """Apply again every confirmed track whose application did not finish."""
        operations = self._service.files.resume_ids()
        if not operations:
            self.noticeRaised.emit("Nothing to retry.")
            return
        for operation_id in operations:
            self._submit_apply(operation_id, f"{_APPLY_PREFIX}: retry")

    @Slot()
    def undoLast(self) -> None:
        """Undo the last confirmation that was applied."""
        operation = self._service.repository.last_confirmation()
        if operation is None:
            self.noticeRaised.emit("There is no confirmation to undo.")
            return
        files = self._service.files
        operation_id = str(operation["operation_id"])

        def task(context: JobContext) -> None:
            outcome = files.undo_operation(operation_id)
            for message in outcome["conflicts"]:
                context.report_failure("Undo", message)
            self._bridge.finished.emit(operation_id)
            if outcome["conflicts"]:
                raise ArtistApplyError(
                    f"{len(outcome['conflicts'])} tracks were changed since and were not restored."
                )

        self._jobs.submit(task, label=f"{_APPLY_PREFIX}: undo")

    @Slot(object)
    def _on_job_event(self, status: object) -> None:
        label = str(getattr(status, "label", ""))
        if not label:
            return
        analyzing = any(
            item.label.startswith("Analyze") and not item.is_terminal
            for item in self._jobs.statuses()
        )
        applying = any(
            item.label.startswith(_APPLY_PREFIX) and not item.is_terminal
            for item in self._jobs.statuses()
        )
        if (analyzing, applying) != (self._analyzing, self._applying):
            finished = (self._analyzing and not analyzing) or (self._applying and not applying)
            self._analyzing, self._applying = analyzing, applying
            self.busyChanged.emit()
            if finished or getattr(status, "state", None) in (JobState.SUCCEEDED, JobState.FAILED):
                self._schedule_refresh()

    @Slot(str)
    def _on_item_done(self, track_id: str) -> None:
        self._changed_tracks.add(track_id)
        if not self._item_timer.isActive():
            self._item_timer.start()

    @Slot()
    def _flush_changed_tracks(self) -> None:
        ids = sorted(self._changed_tracks)
        self._changed_tracks.clear()
        if ids:
            self.tracksChanged.emit(ids)
            self._schedule_refresh()

    @Slot(str)
    def _on_finished(self, _operation_id: str) -> None:
        self._flush_changed_tracks()
        self.refresh()


class NullArtistManager(QObject):
    """Stand-in of the demo mode: the manager works on the real library only."""

    stateChanged = Signal()
    busyChanged = Signal()
    noticeRaised = Signal(str)
    confirmationReady = Signal("QVariantMap")
    tracksChanged = Signal(list)

    @Property(bool, constant=True)
    def available(self) -> bool:
        return False

    @Property("QVariantMap", notify=stateChanged)
    def state(self) -> dict[str, Any]:
        return {
            "mode": "guided",
            "completed": False,
            "cohortRegistered": False,
            "cohortReady": False,
            "cohortTotal": 0,
            "cohortMissing": 0,
            "unfinishedApplications": 0,
            "categories": {
                name: {"remaining": 0, "complete": False, "accessible": name == "from_tags"}
                for name in ("from_tags", "suggested", "needs_input")
            },
        }

    @Property(bool, notify=busyChanged)
    def analyzing(self) -> bool:
        return False

    @Property(bool, notify=busyChanged)
    def applying(self) -> bool:
        return False

    @Slot(str, result=QObject)
    def listModel(self, _key: str) -> QObject:
        return self

    @Slot()
    def refresh(self) -> None:
        return None

    @Slot()
    def analyzeCollection(self) -> None:
        return None

"""Worker-backed Qt gateway for local playlist operations and sidebar state."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QElapsedTimer,
    QObject,
    QThread,
    QUrl,
    Signal,
    Slot,
)

from mtee.domain.durations import format_playlist_meta
from mtee.domain.jobs import JobCancelledError, JobId, JobStatus
from mtee.domain.playlists import LIKED_PLAYLIST_ID, PLAYLIST_COLUMNS
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.jobs import JobContext, JobService
from mtee.services.playlist_exchange import PlaylistExchange
from mtee.services.playlist_images import copy_cover
from mtee.services.playlist_service import AmbiguousPlaylistAddError, PlaylistService
from mtee.services.profile_service import (
    DEFAULT_CREATOR,
    DISPLAY_NAME_KEY,
    normalize_display_name,
)


class PlaylistsModel(QObject):
    changed = Signal()
    noticeRaised = Signal(str)
    playlistCreated = Signal(str)
    playlistDeleted = Signal(str)
    uiRequested = Signal(str, str, list)
    importReady = Signal()
    importResolved = Signal()
    libraryImported = Signal()
    coverChanged = Signal(str)
    resultReady = Signal(object, object, object)

    def __init__(
        self,
        service: PlaylistService,
        settings: SettingsRepository,
        jobs: JobService,
        data_dir: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.repository = service.repository
        self.settings = settings
        self.jobs = jobs
        self.data_dir = data_dir
        self._playlists: list[dict[str, Any]] = []
        self._folders: list[dict[str, Any]] = []
        self._memberships: dict[str, list[str]] = {}
        self._liked: list[str] = []
        self._liked_aliases: set[str] = set()
        self._expanded: set[str] = set()
        self._creator = "MTEE"
        self._liked_detail: dict[str, Any] = {}
        self._columns: dict[str, Any] = self.default_columns()
        self._ambiguity: dict[str, Any] = {}
        self.exchange: PlaylistExchange | None = None
        self._import_preview: dict[str, Any] = {}
        self._import_manifest: dict[str, Any] = {}
        self._pending_imports: list[dict[str, Any]] = []
        self._import_committing = False
        self._pending: deque[tuple[Callable[[JobContext], None], str, bool]] = deque()
        self._current_job = ""
        self.jobs.jobUpdated.connect(self._on_job_updated)
        self.resultReady.connect(self._receive)
        self.refresh()

    @staticmethod
    def default_columns() -> dict[str, Any]:
        return {
            "order": list(PLAYLIST_COLUMNS),
            "hidden": [],
            "showArtwork": True,
            "widths": {
                "title": 0,
                "artist": 150,
                "album": 150,
                "bpm": 52,
                "key": 52,
                "duration": 70,
            },
        }

    @Property(list, notify=changed)
    def playlists(self) -> list[dict[str, Any]]:
        return self._playlists

    @Property(list, notify=changed)
    def tree(self) -> list[dict[str, Any]]:
        rows = [
            {
                "id": LIKED_PLAYLIST_ID,
                "name": "Liked tracks",
                "kind": "playlist",
                "depth": 0,
                "cover": -1,
                "coverUrl": "",
                "covers": [],
                "summary": f"{len(self._liked)} tracks",
                "pinned": False,
                "path": "",
            }
        ]
        rows.extend(p | {"depth": 0} for p in self._playlists if p["pinned"])

        def children(parent: str, depth: int) -> None:
            for folder in self._folders:
                if (folder["parent_id"] or "") != parent:
                    continue
                identity = folder["folder_id"]
                rows.append(
                    {
                        "id": identity,
                        "name": folder["name"],
                        "kind": "folder",
                        "depth": depth,
                        "expanded": identity in self._expanded,
                        "parent": parent,
                        "cover": -1,
                    }
                )
                if identity in self._expanded:
                    children(identity, depth + 1)
            rows.extend(
                p | {"depth": depth}
                for p in self._playlists
                if not p["pinned"] and p["folder"] == parent
            )

        children("", 0)
        return rows

    @Property(list, notify=changed)
    def folders(self) -> list[dict[str, Any]]:
        return [{"id": f["folder_id"], "name": f["name"]} for f in self._folders]

    @Property(str, notify=changed)
    def creator(self) -> str:
        return self._creator

    @Property(dict, notify=changed)
    def columns(self) -> dict[str, Any]:
        return self._columns

    @Property(dict, notify=changed)
    def ambiguity(self) -> dict[str, Any]:
        return self._ambiguity

    @Slot(str, result=dict)
    def details(self, identity: str) -> dict[str, Any]:
        if identity == LIKED_PLAYLIST_ID:
            return self._liked_detail or {
                "id": identity,
                "name": "Liked tracks",
                "description": "Your saved tracks",
                "summary": "0 tracks",
                "trackCount": 0,
                "metaText": "0 tracks",
                "covers": [],
                "coverUrl": "",
            }
        return next((p for p in self._playlists if p["id"] == identity), {})

    @Slot(str, result=list)
    def containing(self, track_id: str) -> list[str]:
        return self._memberships.get(track_id, [])

    @Slot(str, result=bool)
    def isLiked(self, track_id: str) -> bool:
        return track_id in self._liked_aliases

    def _snapshot(self) -> dict[str, Any]:
        folders = self.repository.folders()
        by_id = {f["folder_id"]: f for f in folders}
        playlists = []
        for playlist in self.repository.playlists():
            identity = playlist["playlist_id"]
            rows = self.service.rows(identity)
            seconds = sum(int(r.get("seconds", 0)) for r in rows)
            unavailable = sum(not r["available"] for r in rows)
            path = []
            parent = playlist["folder_id"] or ""
            while parent in by_id:
                path.insert(0, by_id[parent]["name"])
                parent = by_id[parent]["parent_id"] or ""
            cover = self.data_dir / "playlist-covers" / playlist["cover_ref"]
            playlists.append(
                playlist
                | {
                    "id": identity,
                    "kind": "playlist",
                    "folder": playlist["folder_id"] or "",
                    "cover": -1,
                    "coverUrl": QUrl.fromLocalFile(str(cover)).toString()
                    if playlist["cover_ref"]
                    else "",
                    "covers": [r["coverUrl"] for r in rows if r["coverUrl"]][:4],
                    "path": " / ".join(path),
                    "seconds": seconds,
                    "unavailable": unavailable,
                    "summary": f"{len(rows)} tracks · {seconds // 60}:{seconds % 60:02d}"
                    + (f" · {unavailable} unavailable" if unavailable else ""),
                    "trackCount": len(rows),
                    "metaText": format_playlist_meta(len(rows), seconds),
                }
            )
        liked_rows = self.service.rows(LIKED_PLAYLIST_ID)
        liked_seconds = sum(int(r.get("seconds", 0)) for r in liked_rows)
        liked_detail = {
            "id": LIKED_PLAYLIST_ID,
            "name": "Liked tracks",
            "description": "Your saved tracks",
            "summary": f"{len(liked_rows)} tracks · {liked_seconds // 60}:{liked_seconds % 60:02d}",
            "trackCount": len(liked_rows),
            "metaText": format_playlist_meta(len(liked_rows), liked_seconds),
            "coverUrl": "",
            "covers": [r["coverUrl"] for r in liked_rows if r["coverUrl"]][:4],
        }
        return {
            "likedDetail": liked_detail,
            "expanded": self.settings.get_json("playlists/expanded", []),
            "playlists": playlists,
            "folders": folders,
            "liked": self.repository.liked_ids(),
            "likedAliases": self.service.liked_aliases(),
            "memberships": self.service.memberships(),
            "creator": self.settings.get(DISPLAY_NAME_KEY, "") or DEFAULT_CREATOR,
            "columns": self.settings.get_json("playlists/columns", self.default_columns()),
            "pendingImports": self.exchange.pending_imports() if self.exchange else [],
        }

    def run(
        self,
        action: Callable[[JobContext], Any],
        *,
        label: str = "Update playlists",
        event: str = "",
        visible: bool = False,
        ambiguity_context: dict[str, Any] | None = None,
    ) -> None:
        def task(context: JobContext) -> None:
            try:
                with self.service.lock:
                    context.raise_if_cancelled()
                    result = action(context)
                    state = self._snapshot()
                    self.resultReady.emit(state, {"event": event, "value": result}, None)
            except AmbiguousPlaylistAddError as error:
                self.resultReady.emit(
                    None,
                    {"ambiguity": ambiguity_context or {}, "trackIds": error.track_ids},
                    str(error),
                )
            except JobCancelledError:
                self.resultReady.emit(
                    None,
                    {"event": event},
                    "Playlist operation cancelled. "
                    "Incomplete ZIP imports can be resumed from the + menu.",
                )
                raise
            except Exception as error:
                self.resultReady.emit(None, {"event": event}, str(error))
                raise

        self._pending.append((task, label, visible))
        self._start_next()

    def _start_next(self) -> None:
        if self._current_job or not self._pending or not self.jobs.accepting:
            return
        task, label, visible = self._pending.popleft()
        self._current_job = str(self.jobs.submit(task, label=label, visible=visible))

    @Slot(object)
    def _on_job_updated(self, status: object) -> None:
        if (
            isinstance(status, JobStatus)
            and str(status.job_id) == self._current_job
            and status.is_terminal
        ):
            self._current_job = ""
            self._start_next()

    @Slot()
    def refresh(self) -> None:
        self.run(lambda _context: None)

    @Slot(object, object, object)
    def _receive(self, state: object, result: object, error: object) -> None:
        if error is not None:
            self._import_committing = False
            if isinstance(result, dict) and "ambiguity" in result:
                self._ambiguity = dict(result["ambiguity"]) | {"trackIds": result["trackIds"]}
                self.changed.emit()
            self.noticeRaised.emit(str(error))
            if isinstance(result, dict) and result.get("event") == "import":
                self.refresh()
                self.libraryImported.emit()
            return
        if not isinstance(state, dict):
            return
        self._playlists = state["playlists"]
        self._folders = state["folders"]
        self._memberships = state["memberships"]
        self._liked = state["liked"]
        self._liked_aliases = set(state["likedAliases"])
        self._liked_detail = state["likedDetail"]
        self._expanded = set(state["expanded"])
        self._creator = state["creator"]
        self._columns = state["columns"]
        self._pending_imports = state.get("pendingImports", [])
        self.changed.emit()
        if isinstance(result, dict):
            if result["event"] == "import":
                self._import_manifest = result["value"]["manifest"]
                self._import_preview = result["value"]
                self.importReady.emit()
                self.changed.emit()
                self.libraryImported.emit()
            elif result["event"] == "export":
                missing = result["value"]["missing"]
                self.noticeRaised.emit(
                    "Playlist exported."
                    + (f" {missing} unavailable tracks have no audio copy." if missing else "")
                )
            elif result["event"] == "created":
                self._import_committing = False
                self.playlistCreated.emit(str(result["value"]))
            elif result["event"] == "cover":
                self.coverChanged.emit(str(result["value"]))
            elif result["event"] == "located":
                self.libraryImported.emit()
            elif result["event"] == "deleted":
                self.playlistDeleted.emit(str(result["value"]))

    @Slot(str)
    def toggleFolder(self, identity: str) -> None:
        if identity in self._expanded:
            self._expanded.remove(identity)
        else:
            self._expanded.add(identity)
        self.changed.emit()
        expanded = sorted(self._expanded)
        self.run(lambda _c: self.settings.set_json("playlists/expanded", expanded))

    @Slot(str, str, list)
    def create(
        self, name: str, folder: str, track_ids: list, *, confirm_unknown: bool = False
    ) -> None:
        self._create_playlist(name, folder, track_ids, confirm_unknown=confirm_unknown)

    @Slot(str, list)
    def createUntitled(self, folder: str, track_ids: list) -> None:
        self._create_playlist(None, folder, track_ids)

    def _create_playlist(
        self, name: str | None, folder: str, track_ids: list, *, confirm_unknown: bool = False
    ) -> None:
        ids = [str(identity) for identity in track_ids]
        ambiguity = {"action": "create", "name": name, "folder": folder}

        def create(_context: JobContext) -> str:
            identity = self.repository.create(name, folder)
            try:
                self.service.add(
                    identity, ids, confirm_unknown=confirm_unknown
                )
            except Exception:
                self.repository.delete(identity)
                raise
            return identity

        self.run(create, event="created", ambiguity_context=ambiguity)

    @Slot(str, list)
    def toggle(self, identity: str, track_ids: list) -> None:
        ids = [str(i) for i in track_ids]
        self.run(
            lambda _c: self.service.toggle(identity, ids),
            ambiguity_context={"playlistId": identity},
        )

    @Slot(bool)
    def confirmAmbiguity(self, confirmed: bool) -> None:
        pending = dict(self._ambiguity)
        self._ambiguity = {}
        self.changed.emit()
        if confirmed and pending.get("trackIds"):
            if pending.get("action") == "create":
                self._create_playlist(
                    pending["name"], pending["folder"], pending["trackIds"], confirm_unknown=True
                )
            elif pending.get("playlistId"):
                method = self.service.add if pending.get("action") == "add" else self.service.toggle
                self.run(
                    lambda _c: method(
                        pending["playlistId"], pending["trackIds"], confirm_unknown=True
                    )
                )

    @Slot(str)
    def toggleLike(self, track_id: str) -> None:
        self.run(lambda _c: self.service.toggle_like(track_id))

    @Slot(str, str, str, int)
    def edit(self, identity: str, name: str, description: str, version: int) -> None:
        self.run(
            lambda _c: self.repository.update(
                identity,
                name=name,
                description=description,
                cover=self.repository.playlist(identity)["cover_ref"],
                version=version,
            )
        )

    @Slot(str, str)
    def setCover(self, identity: str, url: str) -> None:
        def copy(_context: JobContext) -> None:
            reference = ""
            if url:
                reference = copy_cover(
                    Path(QUrl(url).toLocalFile()), self.data_dir / "playlist-covers"
                )
            playlist = self.repository.playlist(identity)
            self.repository.update(
                identity,
                name=playlist["name"],
                description=playlist["description"],
                cover=reference,
                version=playlist["version"],
            )

        self.run(lambda c: (copy(c), identity)[1], event="cover")

    @Slot(str)
    def setCreator(self, value: str) -> None:
        """Set the profile display name, which is the creator written on playlists."""
        try:
            name = normalize_display_name(value)
        except ValueError:
            self.noticeRaised.emit("Use a creator name between 1 and 240 characters.")
            return
        self.run(lambda _c: self.settings.set(DISPLAY_NAME_KEY, name))

    @Slot(dict)
    def setColumns(self, value: dict) -> None:
        self.run(lambda _c: self.settings.set_json("playlists/columns", dict(value)))

    @Slot(str, int)
    def resizeColumn(self, key: str, width: int) -> None:
        if key in PLAYLIST_COLUMNS:
            value = dict(self._columns)
            value["widths"] = dict(value["widths"]) | {key: min(max(width, 44), 640)}
            self.setColumns(value)

    @Slot(str, int)
    def moveColumn(self, key: str, offset: int) -> None:
        order = list(self._columns["order"])
        if key in order and offset in {-1, 1}:
            index = order.index(key)
            order.insert(min(max(index + offset, 0), len(order) - 1), order.pop(index))
            self.setColumns(dict(self._columns) | {"order": order})

    @Slot(str, str, bool)
    def moveColumnRelative(self, key: str, target: str, after: bool) -> None:
        order = list(self._columns["order"])
        if key in order and target in order and key != target:
            order.remove(key)
            order.insert(order.index(target) + int(after), key)
            self.setColumns(dict(self._columns) | {"order": order})

    @Slot(str)
    def duplicate(self, identity: str) -> None:
        self.run(lambda _c: self.repository.duplicate(identity), event="created")

    @Slot(str)
    def delete(self, identity: str) -> None:
        def delete(_context: JobContext) -> str:
            self.repository.delete(identity)
            return identity

        self.run(delete, event="deleted")

    @Slot(str, bool)
    def pin(self, identity: str, pinned: bool) -> None:
        self.run(lambda _c: self.repository.pin(identity, pinned))

    @Slot(str, str)
    def createFolder(self, name: str, parent: str) -> None:
        self.run(lambda _c: self.repository.create_folder(name, parent))

    @Slot(str, str)
    def renameFolder(self, identity: str, name: str) -> None:
        self.run(lambda _c: self.repository.rename_folder(identity, name))

    @Slot(str)
    def deleteFolder(self, identity: str) -> None:
        self.run(lambda _c: self.repository.delete_folder(identity))

    @Slot(str, str, bool, str)
    def move(self, identity: str, folder: str, is_folder: bool, before: str) -> None:
        self.run(
            lambda _c: self.repository.move(identity, folder, is_folder=is_folder, before=before)
        )

    @Slot(str, list, int)
    def reorder(self, identity: str, entries: list, version: int) -> None:
        self.run(lambda _c: self.repository.reorder(identity, [str(i) for i in entries], version))

    @Slot(str, list)
    def remove(self, identity: str, entries: list) -> None:
        if identity == LIKED_PLAYLIST_ID:

            def unlike(_context: JobContext) -> None:
                for entry in entries:
                    if str(entry).startswith("like:"):
                        self.repository.like(str(entry).partition(":")[2], False)

            self.run(unlike)
        else:
            self.run(lambda _c: self.repository.remove(identity, [str(i) for i in entries]))

    @Slot(str, str, str)
    def resolve(self, identity: str, entry: str, track_id: str) -> None:
        self.run(lambda _c: self.service.resolve(identity, entry, track_id))

    @Slot(str, str, list)
    def requestUI(self, action: str, identity: str, tracks: list) -> None:
        self.uiRequested.emit(action, identity, tracks)

    @Slot()
    def resetColumns(self) -> None:
        self.setColumns(self.default_columns())

    @Property(dict, notify=changed)
    def importPreview(self) -> dict[str, Any]:
        return self._import_preview

    @Slot(str, str, bool)
    def export(self, identity: str, url: str, complete: bool) -> None:
        if self.exchange is None:
            return
        exchange = self.exchange
        destination = Path(QUrl(url).toLocalFile())
        suffix = ".zip" if complete else ".mteeplaylist"
        if destination.suffix.lower() != suffix:
            destination = destination.with_name(destination.name + suffix)
        self.run(
            lambda c: exchange.export(identity, destination, complete, c),
            event="export",
            label="Export playlist",
            visible=True,
        )

    @Slot(str, str)
    def prepareImport(self, url: str, destination_url: str) -> None:
        if self.exchange is None:
            return
        exchange = self.exchange
        path = Path(QUrl(url).toLocalFile())

        def prepare(context: JobContext) -> dict[str, Any]:
            if path.suffix.lower() == ".zip":
                manifest, matches, folder = exchange.extract_and_scan(
                    path, Path(QUrl(destination_url).toLocalFile()), context
                )
            else:
                manifest = exchange.read(path)
                matches = exchange.preview(manifest, context)
                folder = ""
            return {
                "name": manifest["name"],
                "manifest": manifest,
                "matches": matches,
                "extractionFolder": folder,
            }

        self.run(prepare, event="import", label="Import playlist", visible=True)

    @Slot(int, str)
    def chooseImportMatch(self, index: int, track_id: str) -> None:
        matches = self._import_preview.get("matches", [])
        if not 0 <= index < len(matches):
            return
        if track_id and track_id not in {c["id"] for c in matches[index]["candidates"]}:
            return
        matches[index]["track_id"] = track_id or None
        matches[index]["status"] = "matched" if track_id else "missing"
        self.changed.emit()

    @Slot()
    def finishImport(self) -> None:
        if self.exchange is None or not self._import_preview or self._import_committing:
            return
        exchange = self.exchange
        manifest = dict(self._import_manifest)
        matches = [dict(m) for m in self._import_preview["matches"]]
        if any(m["status"] == "ambiguous" for m in matches):
            self.noticeRaised.emit("Choose a local file or Keep missing for each ambiguous entry.")
            return

        self._import_committing = True

        def finish(_context: JobContext) -> str:
            return exchange.commit_import(manifest, matches, manifest.get("_operation_id", ""))

        self.run(finish, event="created", label="Save imported playlist", visible=True)

    @Slot(str, str, str)
    def locateFile(self, identity: str, entry: str, url: str) -> None:
        path = Path(QUrl(url).toLocalFile())

        def locate(_context: JobContext) -> None:
            from mtee.domain.tracks import SourceRevision
            from mtee.services.metadata_reader import MetadataReader

            snapshot = MetadataReader().read(path)
            if snapshot.status != "readable":
                raise ValueError("Choose a readable local audio file.")
            root = self.service.library.add_root(path.parent)
            generation = root["scanGeneration"]
            track = self.service.library.upsert_location(
                root["id"],
                path.name,
                path,
                SourceRevision.observe(path),
                snapshot,
                generation,
            )
            self.service.resolve(identity, entry, track)

        self.run(locate, event="located")

    @Slot(str, list)
    def add(self, identity: str, track_ids: list) -> None:
        ids = [str(i) for i in track_ids]
        self.run(
            lambda _c: self.service.add(identity, ids),
            ambiguity_context={"playlistId": identity, "action": "add"},
        )

    @Property(list, notify=changed)
    def pendingImports(self) -> list[dict[str, Any]]:
        return self._pending_imports

    @Slot(str)
    def resumeImport(self, operation: str) -> None:
        if self.exchange is None:
            return
        exchange = self.exchange

        def resume(context: JobContext) -> dict[str, Any]:
            manifest, matches, folder = exchange.resume(operation, context)
            return {
                "name": manifest["name"],
                "manifest": manifest,
                "matches": matches,
                "extractionFolder": folder,
            }

        self.run(resume, event="import", label="Resume playlist import", visible=True)

    def flush_pending(self, timeout_ms: int = 5000) -> bool:
        """Drain ordered writes; cancel file jobs with resumable journals."""
        timer = QElapsedTimer()
        timer.start()
        cancelled: set[str] = set()
        while (self._pending or self._current_job) and timer.elapsed() < timeout_ms:
            if self._current_job and self._current_job not in cancelled:
                identity = JobId.parse(self._current_job)
                if self.jobs.is_visible(identity):
                    self.jobs.cancel(identity)
                    cancelled.add(self._current_job)
            QCoreApplication.processEvents()
            QThread.msleep(5)
        if self._pending or self._current_job:
            self.noticeRaised.emit("Some playlist changes did not finish before shutdown.")
            return False
        return True

"""Preview, journal and recover Genre Manager file organization on local roots."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from mtee.domain.tracks import SourceRevision, TrackId, sha256_of_file
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository, normalize_path
from mtee.plugins.genre_manager.repository import _now, serialized_decision
from mtee.plugins.genre_manager.sessions import GenreSessionRepository
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService


class OrganizationError(RuntimeError):
    """A preview or movement is unsafe or no longer current."""


_INVALID_WINDOWS = re.compile(r'[<>:"|?*\x00-\x1f]')
_DEVICE = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)


def clean_relative_folder(value: str) -> str:
    """Reject traversal, absolute paths and Windows-invalid folder components."""
    raw = value.replace("\\", "/")
    if not raw.strip():
        return ""
    if raw != raw.strip():
        raise OrganizationError("The destination folder name is not valid on Windows")
    if raw.startswith("/") or PureWindowsPath(raw).drive:
        raise OrganizationError("Choose a folder inside the selected library root")
    parts = raw.split("/")
    if any(
        not part
        or part in {".", ".."}
        or part.endswith((" ", "."))
        or _INVALID_WINDOWS.search(part)
        or _DEVICE.match(part)
        for part in parts
    ):
        raise OrganizationError("The destination folder name is not valid on Windows")
    return PurePosixPath(*parts).as_posix()


def _revision_dict(revision: SourceRevision) -> dict[str, Any]:
    return {
        "size_bytes": revision.size_bytes,
        "mtime_ns": revision.mtime_ns,
        "file_id": revision.file_id,
        "generation": revision.generation,
    }


def _revision(value: dict[str, Any]) -> SourceRevision:
    return SourceRevision(
        int(value["size_bytes"]),
        int(value["mtime_ns"]),
        value.get("file_id"),
        int(value["generation"]),
    )


class GenreOrganizer:
    """Move reviewed tracks only after an explicit, immutable preview."""

    def __init__(
        self,
        database: Database,
        library: LibraryRepository,
        sessions: GenreSessionRepository,
        file_access: FileAccessCoordinator,
    ) -> None:
        self._database = database
        self._library = library
        self._sessions = sessions
        self._access = file_access
        self._move = FileMoveService(database, library, file_access)

    def destinations(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self._database.connection().execute(
                "SELECT root_id,genre_id,relative_folder FROM gm_destinations "
                "ORDER BY root_id,genre_id"
            )
        ]

    def latest_undoable(self, session_id: str) -> str:
        """Restore the last forward batch whose successful moves have not been undone."""
        rows = self._database.connection().execute(
            "SELECT o.operation_id,o.preview_json FROM gm_organization_operations o "
            "WHERE o.session_id=? AND EXISTS (SELECT 1 FROM gm_organization_items i "
            "WHERE i.operation_id=o.operation_id AND i.phase='completed') "
            "ORDER BY o.created_at_utc DESC",
            (session_id,),
        )
        for row in rows:
            if not json.loads(str(row["preview_json"])).get("undoOf"):
                return str(row["operation_id"])
        return ""

    @serialized_decision
    def set_destination(self, root_id: str, genre_id: str, relative_folder: str) -> None:
        """Persist a mapping entered by the user; a folder name never creates one."""
        relative = clean_relative_folder(relative_folder)
        self._safe_folder(root_id, relative)
        with self._database.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM gm_genres WHERE genre_id=? AND archived=0", (genre_id,)
                ).fetchone()
                is None
            ):
                raise OrganizationError("Choose an active main genre")
            connection.execute(
                "INSERT INTO gm_destinations(root_id,genre_id,relative_folder,updated_at_utc) "
                "VALUES(?,?,?,?) ON CONFLICT(root_id,genre_id) DO UPDATE SET "
                "relative_folder=excluded.relative_folder,updated_at_utc=excluded.updated_at_utc",
                (root_id, genre_id, relative, _now()),
            )

    def _safe_folder(self, root_id: str, relative: str) -> tuple[Path, Path, bool]:
        root = next((row for row in self._library.roots() if row["id"] == root_id), None)
        if root is None:
            raise OrganizationError("The library root is no longer registered")
        try:
            root_path = Path(str(root["path"])).resolve(strict=True)
        except OSError as error:
            raise OrganizationError("The library root is unavailable") from error
        folder = root_path.joinpath(*PurePosixPath(relative).parts) if relative else root_path
        ancestor = folder
        while not ancestor.exists():
            if ancestor == root_path:
                break
            ancestor = ancestor.parent
        try:
            resolved_ancestor = ancestor.resolve(strict=True)
            resolved_ancestor.relative_to(root_path)
        except (OSError, ValueError) as error:
            raise OrganizationError("The destination escapes the library root") from error
        if not resolved_ancestor.is_dir():
            raise OrganizationError("The destination parent is not a directory")
        if folder.exists():
            try:
                folder.resolve(strict=True).relative_to(root_path)
            except (OSError, ValueError) as error:
                raise OrganizationError("The destination escapes the library root") from error
            if not folder.is_dir():
                raise OrganizationError("The destination is not a directory")
        return root_path, folder, not folder.exists()

    @serialized_decision
    def preview(self, session_id: str) -> dict[str, Any]:
        session = (
            self._database.connection()
            .execute(
                "SELECT session_id,source_label FROM gm_sessions WHERE session_id=?", (session_id,)
            )
            .fetchone()
        )
        if session is None:
            raise KeyError(session_id)
        rows = self._sessions.rows(session_id)
        mappings = {
            (str(row["root_id"]), str(row["genre_id"])): str(row["relative_folder"])
            for row in self.destinations()
        }
        roots = {str(root["id"]): root for root in self._library.roots()}
        results: list[dict[str, Any]] = []
        targets: set[str] = set()
        unreviewed = 0
        for row in rows:
            if not row["reviewed"]:
                unreviewed += 1
                continue
            track_id = str(row["id"])
            genres = row["genres"]
            root_id = str(row["rootId"])
            item: dict[str, Any] = {
                "trackId": track_id,
                "title": row["title"],
                "rootId": root_id,
                "rootName": str(roots[root_id]["name"]) if root_id in roots else root_id,
                "rootPath": str(roots[root_id]["path"]) if root_id in roots else "",
                "genreId": genres[0] if genres else "",
                "genreRevision": row["genreRevision"],
                "source": row["path"],
                "destination": "",
                "relativeFolder": mappings.get((root_id, genres[0]), "") if genres else "",
                "status": "conflict",
                "message": "",
                "needsFolder": False,
            }
            record = self._library.source_record(track_id)
            if not genres:
                item["message"] = "A main genre is required"
            elif record is None or record.status != "readable" or not root_id:
                item["message"] = "The source file is unavailable"
            elif (root_id, genres[0]) not in mappings:
                item["status"] = "needs_destination"
                item["message"] = "Choose a destination for this main genre"
            else:
                try:
                    relative = clean_relative_folder(mappings[(root_id, genres[0])])
                    _root, folder, needs_folder = self._safe_folder(root_id, relative)
                    target = folder / record.path.name
                    item["destination"] = str(target)
                    item["needsFolder"] = needs_folder
                    if not record.revision.matches(SourceRevision.observe(record.path)):
                        raise OrganizationError("The source changed after its last scan")
                    destination_device = folder if folder.exists() else _root
                    if os.stat(record.path).st_dev != os.stat(destination_device).st_dev:
                        raise OrganizationError("Moving between drives is not supported")
                    if normalize_path(record.path) == normalize_path(target):
                        item["status"] = "already_in_place"
                    elif target.exists() or self._library.path_owner(target) is not None:
                        raise OrganizationError("A file with this name already exists")
                    elif normalize_path(target) in targets:
                        raise OrganizationError("Two tracks have the same destination")
                    elif self._access.is_busy(TrackId.parse(track_id)):
                        item["status"] = "busy"
                        item["message"] = "The file is in use; retry when available"
                    else:
                        item["status"] = "ready"
                        item["revision"] = _revision_dict(record.revision)
                        targets.add(normalize_path(target))
                except (OSError, ValueError, OrganizationError) as error:
                    item["message"] = str(error)
            results.append(item)
        operation_id = str(uuid.uuid4())
        preview = {
            "operationId": operation_id,
            "sessionId": session_id,
            "sourceLabel": str(session["source_label"]),
            "reviewed": len(results),
            "unreviewed": unreviewed,
            "ready": sum(item["status"] == "ready" for item in results),
            "rows": results,
        }
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO gm_organization_operations("
                "operation_id,session_id,status,preview_json,"
                "created_at_utc,updated_at_utc) VALUES(?,?,'prepared',?,?,?)",
                (operation_id, session_id, json.dumps(preview), _now(), _now()),
            )
            connection.executemany(
                "INSERT INTO gm_organization_items("
                "operation_id,track_id,ordinal,source_path,destination_path,"
                "source_revision_json,genre_revision,genre_id,phase,updated_at_utc) "
                "VALUES(?,?,?,?,?,?,?,?,'prepared',?)",
                [
                    (
                        operation_id,
                        item["trackId"],
                        index,
                        item["source"],
                        item["destination"],
                        json.dumps(item["revision"]),
                        item["genreRevision"],
                        item["genreId"],
                        _now(),
                    )
                    for index, item in enumerate(results)
                    if item["status"] == "ready"
                ],
            )
        return preview

    def _item_status(self, operation_id: str, track_id: str, phase: str, error: str = "") -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE gm_organization_items SET phase=?,error=?,updated_at_utc=? "
                "WHERE operation_id=? AND track_id=?",
                (phase, error, _now(), operation_id, track_id),
            )

    def _operation_status(self, operation_id: str, status: str) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE gm_organization_operations SET status=?,updated_at_utc=? "
                "WHERE operation_id=?",
                (status, _now(), operation_id),
            )

    @serialized_decision
    def apply(
        self, operation_id: str, *, should_cancel: Callable[[], bool] | None = None
    ) -> dict[str, Any]:
        """Apply one inspected preview, journaling each disk/database boundary."""
        connection = self._database.connection()
        operation = connection.execute(
            "SELECT * FROM gm_organization_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if operation is None:
            raise KeyError(operation_id)
        if operation["status"] != "prepared":
            raise OrganizationError("This preview was already applied or interrupted")
        preview = json.loads(str(operation["preview_json"]))
        items = connection.execute(
            "SELECT * FROM gm_organization_items WHERE operation_id=? ORDER BY ordinal",
            (operation_id,),
        ).fetchall()
        preview_rows = {str(row["trackId"]): row for row in preview["rows"]}
        undo_of = str(preview.get("undoOf", ""))
        self._operation_status(operation_id, "running")
        moved = 0
        failed = 0
        busy = 0
        cancelled = False
        for item in items:
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            track_id = str(item["track_id"])
            relative = ""
            try:
                record = self._library.source_record(track_id)
                source = Path(str(item["source_path"]))
                target = Path(str(item["destination_path"]))
                expected = _revision(json.loads(str(item["source_revision_json"])))
                if record is None or record.path != source or record.revision != expected:
                    raise OrganizationError("The preview is stale; review this track again")
                if not undo_of:
                    state = connection.execute(
                        "SELECT genre_revision,reviewed_revision FROM gm_track_state "
                        "WHERE track_id=?",
                        (track_id,),
                    ).fetchone()
                    main = connection.execute(
                        "SELECT genre_id FROM gm_track_genres WHERE track_id=? AND position=0",
                        (track_id,),
                    ).fetchone()
                    if (
                        state is None
                        or int(state["genre_revision"]) != item["genre_revision"]
                        or state["reviewed_revision"] != state["genre_revision"]
                        or main is None
                        or str(main[0]) != item["genre_id"]
                    ):
                        raise OrganizationError("The classification changed after the preview")
                    root_id = str(preview_rows[track_id]["rootId"])
                    mapping = connection.execute(
                        "SELECT relative_folder FROM gm_destinations WHERE root_id=? "
                        "AND genre_id=?",
                        (root_id, str(item["genre_id"])),
                    ).fetchone()
                    if mapping is None:
                        raise OrganizationError("The destination mapping was removed")
                    relative = clean_relative_folder(str(mapping[0]))
                    _root, folder, _needs_folder = self._safe_folder(root_id, relative)
                    if normalize_path(folder / source.name) != normalize_path(target):
                        raise OrganizationError("The destination changed after the preview")
                else:
                    root_id = str(preview_rows[track_id]["rootId"])
                    _root, folder, _needs_folder = self._safe_folder(
                        root_id, str(preview_rows[track_id]["relativeFolder"])
                    )
                    if normalize_path(folder / source.name) != normalize_path(target):
                        raise OrganizationError("The undo destination changed")
                if not expected.matches(SourceRevision.observe(source)):
                    raise OrganizationError("The source changed after the preview")
                if target.exists() or self._library.path_owner(target) is not None:
                    raise OrganizationError("A file appeared at the destination")
                if "sha256" in json.loads(str(item["source_revision_json"])):
                    expected_hash = json.loads(str(item["source_revision_json"]))["sha256"]
                    if sha256_of_file(source) != expected_hash:
                        raise OrganizationError("The source bytes changed after the preview")
                if not folder.exists():
                    folder.mkdir(parents=True, exist_ok=True)
                    if undo_of:
                        self._safe_folder(root_id, str(preview_rows[track_id]["relativeFolder"]))
                    else:
                        self._safe_folder(root_id, relative)
                proof = json.loads(str(item["source_revision_json"]))
                proof["sha256"] = sha256_of_file(source)
                with self._database.transaction() as transaction:
                    transaction.execute(
                        "UPDATE gm_organization_items SET source_revision_json=?,phase='moving',"
                        "updated_at_utc=? WHERE operation_id=? AND track_id=?",
                        (json.dumps(proof), _now(), operation_id, track_id),
                    )
                result = self._move.move(
                    track_id,
                    folder,
                    on_disk_moved=lambda identity=track_id: self._item_status(
                        operation_id, identity, "moved"
                    ),
                )
                if result.status == "busy":
                    self._item_status(operation_id, track_id, "failed", result.message)
                    busy += 1
                    continue
                if result.status != "moved":
                    raise OrganizationError(result.message or result.status)
                self._item_status(operation_id, track_id, "catalogued")
                self._item_status(operation_id, track_id, "completed")
                if undo_of:
                    self._item_status(undo_of, track_id, "undone")
                moved += 1
            except (OSError, ValueError, OrganizationError) as error:
                self._item_status(operation_id, track_id, "conflict", str(error))
                failed += 1
        if cancelled:
            status = "cancelled"
        elif failed or busy:
            status = "partial"
        else:
            status = "completed"
        self._operation_status(operation_id, status)
        return {
            "operationId": operation_id,
            "status": status,
            "moved": moved,
            "conflicts": failed,
            "busy": busy,
            "unreviewed": preview["unreviewed"],
            "alreadyInPlace": sum(row["status"] == "already_in_place" for row in preview["rows"]),
        }

    @serialized_decision
    def prepare_undo(self, operation_id: str) -> dict[str, Any]:
        """Preview inverse moves for completed items, retaining their own safety checks."""
        connection = self._database.connection()
        original = connection.execute(
            "SELECT session_id,status FROM gm_organization_operations WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if original is None:
            raise KeyError(operation_id)
        if original["status"] not in {"completed", "partial", "cancelled"}:
            raise OrganizationError("The organization has no completed moves to undo")
        items = connection.execute(
            "SELECT * FROM gm_organization_items WHERE operation_id=? AND phase='completed' "
            "ORDER BY ordinal",
            (operation_id,),
        ).fetchall()
        if not items:
            raise OrganizationError("The organization has no completed moves to undo")
        rows: list[dict[str, Any]] = []
        for item in items:
            track_id = str(item["track_id"])
            source = Path(str(item["destination_path"]))
            target = Path(str(item["source_path"]))
            record = self._library.source_record(track_id)
            status = "ready"
            message = ""
            expected_hash = ""
            root = self._library.track_folder(track_id)
            try:
                if record is None or record.path != source or not source.is_file():
                    raise OrganizationError("The organized file is no longer at its destination")
                if root is None:
                    raise OrganizationError("The library root is unavailable")
                root_id = str(root[0])
                relative = target.parent.relative_to(
                    next(Path(str(r["path"])) for r in self._library.roots() if r["id"] == root_id)
                ).as_posix()
                _root, _folder, needs_folder = self._safe_folder(root_id, relative)
                if target.exists() or self._library.path_owner(target) is not None:
                    raise OrganizationError("The original path is occupied")
                if not record.revision.matches(SourceRevision.observe(source)):
                    raise OrganizationError("The organized file changed")
                expected_hash = json.loads(str(item["source_revision_json"]))["sha256"]
                if sha256_of_file(source) != expected_hash:
                    raise OrganizationError("The organized file bytes changed")
            except (OSError, ValueError, StopIteration, OrganizationError) as error:
                status, message = "conflict", str(error)
                root_id, relative, needs_folder = "", "", False
            rows.append(
                {
                    "trackId": track_id,
                    "title": source.stem,
                    "rootId": root_id,
                    "relativeFolder": relative,
                    "genreId": str(item["genre_id"]),
                    "genreRevision": int(item["genre_revision"]),
                    "source": str(source),
                    "destination": str(target),
                    "status": status,
                    "message": message,
                    "needsFolder": needs_folder,
                    "revision": _revision_dict(record.revision) | {"sha256": expected_hash}
                    if status == "ready" and record is not None
                    else {},
                }
            )
        undo_id = str(uuid.uuid4())
        preview = {
            "operationId": undo_id,
            "sessionId": str(original["session_id"]),
            "undoOf": operation_id,
            "sourceLabel": "Undo organization",
            "reviewed": len(rows),
            "unreviewed": 0,
            "ready": sum(row["status"] == "ready" for row in rows),
            "rows": rows,
        }
        with self._database.transaction() as transaction:
            transaction.execute(
                "INSERT INTO gm_organization_operations(operation_id,session_id,status,"
                "preview_json,created_at_utc,updated_at_utc) VALUES(?,?,'prepared',?,?,?)",
                (undo_id, str(original["session_id"]), json.dumps(preview), _now(), _now()),
            )
            transaction.executemany(
                "INSERT INTO gm_organization_items(operation_id,track_id,ordinal,"
                "source_path,destination_path,source_revision_json,genre_revision,genre_id,"
                "phase,updated_at_utc) VALUES(?,?,?,?,?,?,?,?,'prepared',?)",
                [
                    (
                        undo_id,
                        row["trackId"],
                        index,
                        row["source"],
                        row["destination"],
                        json.dumps(row["revision"]),
                        row["genreRevision"],
                        row["genreId"],
                        _now(),
                    )
                    for index, row in enumerate(rows)
                    if row["status"] == "ready"
                ],
            )
        return preview

    def recover(self) -> list[dict[str, Any]]:
        """Reconcile interrupted items only when path and SHA proof are sufficient."""
        connection = self._database.connection()
        pending = connection.execute(
            "SELECT * FROM gm_organization_items WHERE phase IN "
            "('moving','moved','catalogued','conflict') "
            "ORDER BY updated_at_utc"
        ).fetchall()
        outcomes = []
        for item in pending:
            operation_id = str(item["operation_id"])
            track_id = str(item["track_id"])
            source = Path(str(item["source_path"]))
            target = Path(str(item["destination_path"]))
            proof = json.loads(str(item["source_revision_json"]))
            record = self._library.source_record(track_id)
            try:
                if record is None or "sha256" not in proof:
                    raise OrganizationError("The file identity cannot be proved")
                if target.is_file() and not source.exists():
                    if sha256_of_file(target) != proof["sha256"]:
                        raise OrganizationError("Destination bytes differ from the journal")
                    if normalize_path(record.path) == normalize_path(source):
                        with self._database.transaction() as transaction:
                            LibraryRepository.move_location_in_transaction(
                                transaction,
                                track_id=track_id,
                                expected_revision=_revision(proof),
                                destination=target,
                                new_revision=SourceRevision.observe(
                                    target, generation=int(proof["generation"]) + 1
                                ),
                                metadata=record.snapshot,
                            )
                    elif normalize_path(record.path) != normalize_path(target):
                        raise OrganizationError("Library path disagrees with the journal")
                    self._item_status(operation_id, track_id, "completed")
                    outcome = "completed"
                elif source.is_file() and not target.exists():
                    if sha256_of_file(source) != proof["sha256"]:
                        raise OrganizationError("Source bytes differ from the journal")
                    if normalize_path(record.path) != normalize_path(source):
                        raise OrganizationError("Library path disagrees with the journal")
                    self._item_status(operation_id, track_id, "conflict", "Move did not complete")
                    outcome = "conflict"
                else:
                    raise OrganizationError("Both paths exist or neither path exists")
            except (OSError, ValueError, OrganizationError) as error:
                self._item_status(operation_id, track_id, "conflict", str(error))
                outcome = "conflict"
            outcomes.append({"operationId": operation_id, "trackId": track_id, "status": outcome})
            if outcome == "completed":
                operation = connection.execute(
                    "SELECT preview_json FROM gm_organization_operations WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if operation is not None:
                    undo_of = json.loads(str(operation["preview_json"])).get("undoOf")
                    if undo_of:
                        self._item_status(str(undo_of), track_id, "undone")
        interrupted = connection.execute(
            "SELECT i.operation_id,i.track_id FROM gm_organization_items i "
            "JOIN gm_organization_operations o ON o.operation_id=i.operation_id "
            "WHERE o.status='running' AND i.phase='prepared'"
        ).fetchall()
        for item in interrupted:
            self._item_status(
                str(item["operation_id"]),
                str(item["track_id"]),
                "conflict",
                "Move was not started before interruption; prepare a new preview",
            )
            outcomes.append(
                {
                    "operationId": str(item["operation_id"]),
                    "trackId": str(item["track_id"]),
                    "status": "conflict",
                }
            )
        for operation_id in {item["operationId"] for item in outcomes}:
            remaining = connection.execute(
                "SELECT COUNT(*) FROM gm_organization_items WHERE operation_id=? "
                "AND phase NOT IN ('completed','undone')",
                (operation_id,),
            ).fetchone()[0]
            self._operation_status(str(operation_id), "partial" if remaining else "completed")
        return outcomes

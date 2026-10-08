"""Qt facade: worker database commands, GUI-only snapshots, per-view preferences."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from PySide6.QtCore import Property as QtProperty
from PySide6.QtCore import QObject, Signal
from PySide6.QtCore import Slot as QtSlot

from mtee.domain.genre_filters import folder_context_mapping, folder_protected_ids
from mtee.persistence.genre_manager_repository import GenreManagerRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.jobs import JobService

Property = cast(Any, QtProperty)
Slot = cast(Any, QtSlot)


class GenreModel(QObject):
    changed = Signal()
    applied = Signal()
    contextChanged = Signal(list)
    finished = Signal(object, str)

    def __init__(self, repository: GenreManagerRepository, jobs: JobService, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.jobs = jobs
        self._catalog: dict[str, Any] = {"genres": [], "metas": [], "tags": []}
        self._preferences: dict[str, Any] = {
            "views": {},
            "named": {},
            "favourites": [],
            "recent": [],
        }
        self._busy = False
        self._message = ""
        self._undo: list[str] = []
        self._assignments: dict[str, dict[str, Any]] = {}
        self._loading = False
        self._undo_pending = False
        self._retry_callback = None
        self._retry_mutation = True
        self.finished.connect(self._finished)
        self.reload()

    @Property("QVariantMap", notify=changed)
    def catalog(self):
        return self._catalog

    @Property("QVariantMap", notify=changed)
    def preferences(self):
        return self._preferences

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(bool, notify=changed)
    def canUndo(self):
        return bool(self._undo) and not self._busy

    def _submit(self, callback, *, mutation=True):
        if self._busy or self._loading:
            return
        self._retry_callback = callback
        self._retry_mutation = mutation
        self._busy = True
        self._message = "Saving" if mutation else "Loading"
        self.changed.emit()

        def work(context):
            try:
                context.raise_if_cancelled()
                result = callback(context)
                snapshot = self.repository.catalog()
                tree = self.repository.taxonomy_from(self.repository.database.connection())
                snapshot["contexts"] = {
                    folder: sorted(folder_protected_ids(folder, tree))
                    for folder in folder_context_mapping()
                }
                ids = [
                    str(r[0])
                    for r in self.repository.database.connection().execute(
                        "SELECT track_id FROM tracks"
                    )
                ]
                assignments = self.repository.track_assignments(ids)
                self.finished.emit(
                    {
                        "result": result,
                        "catalog": snapshot,
                        "assignments": assignments,
                        "mutation": mutation,
                    },
                    "",
                )
            except Exception as error:
                self.finished.emit({}, str(error))
                raise

        self.jobs.submit(
            work, label="Save local genres" if mutation else "Load local genres", visible=mutation
        )

    @Slot(object, str)
    def _finished(self, payload, error):
        self._busy = False
        if error:
            self._message = "Could not save: " + error
        else:
            self._catalog = payload["catalog"]
            self._assignments = payload["assignments"]
            result = payload.get("result") or {}
            changed_views = []
            if result.get("preferences") is not None:
                next_preferences = result["preferences"]
                changed_views = [
                    key
                    for key in set(self._preferences["views"]) | set(next_preferences["views"])
                    if self._preferences["views"].get(key) != next_preferences["views"].get(key)
                ]
                self._preferences = next_preferences
            if result.get("undo"):
                if self._undo:
                    self._undo.pop()
            elif result.get("operation"):
                self._undo.append(result["operation"])
            if result.get("created"):
                key = result["view"]
                state = self._preferences["views"].setdefault(key, {})
                state["brush"] = result["created"]
            self._message = "Saved" if payload["mutation"] else ""
            if payload["mutation"]:
                self.applied.emit()
            elif result.get("preferences") is not None:
                self.contextChanged.emit(changed_views)
        self.changed.emit()
        if self._undo_pending:
            self._undo_pending = False
            self.undo()

    @Slot()
    def retry(self):
        if self._retry_callback is not None and not self._busy:
            self._submit(self._retry_callback, mutation=self._retry_mutation)

    @Slot()
    def reload(self):
        self._submit(
            lambda context: {
                "preferences": SettingsRepository(self.repository.database).get_json(
                    "genres/ui/v1", deepcopy(self._preferences)
                )
            },
            mutation=False,
        )

    @Slot(str, str, str, "QVariantMap", int)
    def edit(self, kind, action, identity, values, revision):
        self._submit(
            lambda context: self.repository.edit(
                kind, action, identity, dict(values), revision, context.raise_if_cancelled
            )
        )

    @Slot(str, str, str)
    def quickCreate(self, view, name, parent):
        def create(context):
            result: dict[str, Any] = dict(
                self.repository.edit("genre", "create", "", {"name": name, "parent_id": parent})
            )
            prefs = deepcopy(self._preferences)
            prefs["views"].setdefault(view, {})["brush"] = result["identity"]
            SettingsRepository(self.repository.database).set_json("genres/ui/v1", prefs)
            result["preferences"] = prefs
            return result

        self._submit(create)

    @Slot(str, str)
    def setBrush(self, view, identity):
        prefs = deepcopy(self._preferences)
        prefs["views"].setdefault(view, {})["brush"] = identity
        prefs["recent"] = [identity, *[i for i in prefs["recent"] if i != identity][:8]]
        self._save_preferences(prefs)

    @Slot(str)
    def toggleFavourite(self, identity):
        prefs = deepcopy(self._preferences)
        values = prefs["favourites"]
        if identity in values:
            values.remove(identity)
        else:
            values.append(identity)
        self._save_preferences(prefs)

    @Slot(str, "QVariantMap")
    def setFilter(self, view, spec):
        prefs = deepcopy(self._preferences)
        prefs["views"].setdefault(view, {})["filter"] = dict(spec)
        self._save_preferences(prefs)

    @Slot(str, str)
    def saveFilter(self, view, name):
        if not name.strip():
            return
        prefs = deepcopy(self._preferences)
        prefs["named"][name.strip()] = deepcopy(
            prefs["views"]
            .get(view, {})
            .get("filter", {"version": 1, "mode": "all", "criteria": []})
        )
        self._save_preferences(prefs)

    @Slot(str, str)
    def loadFilter(self, view, name):
        spec = self._preferences["named"].get(name)
        if spec is not None:
            self.setFilter(view, spec)

    def _save_preferences(self, prefs):
        def save(context):
            SettingsRepository(self.repository.database).set_json("genres/ui/v1", prefs)
            return {"preferences": prefs}

        self._submit(save, mutation=False)

    @Slot(list, str, bool, "QVariantMap")
    def assign(self, ids, genre, enabled, revisions):
        self._submit(
            lambda context: {
                "operation": self.repository.change_membership(
                    ids,
                    [genre],
                    enabled=enabled,
                    expected_revisions=dict(revisions),
                    cancel=context.raise_if_cancelled,
                )
            }
        )

    @Slot(list, str, bool, "QVariantMap")
    def assignTag(self, ids, tag, enabled, revisions):
        self._submit(
            lambda context: {
                "operation": self.repository.change_tags(
                    ids, tag, enabled, dict(revisions), context.raise_if_cancelled
                )
            }
        )

    @Slot()
    def undo(self):
        if self._busy:
            self._undo_pending = True
            return
        if not self._undo:
            return
        operation = self._undo[-1]
        self._submit(lambda context: {"inverse": self.repository.undo_any(operation), "undo": True})

    def assignment_snapshot(self, identity: str) -> dict[str, Any]:
        return deepcopy(self._assignments.get(identity, {}))

    def catalog_snapshot(self) -> dict[str, Any]:
        return deepcopy(self._catalog)

    def view_state(self, key: str) -> dict[str, Any]:
        return deepcopy(self._preferences["views"].get(key, {}))

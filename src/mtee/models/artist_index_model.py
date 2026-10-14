"""Qt models of the core Artists view: the artist list and the tracks of one artist.

Both read the ``ArtistIndexService``. The list is rebuilt on the graphical thread from the
finished index only; the tracks of an artist are read by a background job.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from mtee.models.track_list_model import TrackListModel
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artist_index_service import ArtistIndexService
from mtee.services.jobs import JobContext, JobService

__all__ = ["ArtistListModel", "ArtistPageModel"]

_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_ROOT_INDEX = QModelIndex()


class ArtistListModel(QAbstractListModel):
    """The artists of the library, filtered by a search text, one row per artist.

    A row is ``{"key", "name", "trackCount"}``. ``key`` is the stable identity used to open
    the artist page.
    """

    countChanged = Signal()
    filterChanged = Signal()

    def __init__(self, service: ArtistIndexService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._filter = ""
        self._rows: list[dict[str, Any]] = []
        service.indexChanged.connect(self._reload)
        self._reload()

    def roleNames(self) -> dict[int, QByteArray]:
        return {_DATA_ROLE: QByteArray(b"modelData")}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        return (
            self._rows[index.row()]
            if role in (_DATA_ROLE, int(Qt.ItemDataRole.DisplayRole))
            else None
        )

    @Property(int, notify=countChanged)
    def count(self) -> int:
        """Artists shown with the current filter."""
        return len(self._rows)

    @Property(int, notify=countChanged)
    def totalCount(self) -> int:
        """Every artist of the library, whatever the filter."""
        return len(self._service.index.artists)

    @Property(str, notify=filterChanged)
    def filterText(self) -> str:
        return self._filter

    @Slot(str)
    def setFilterText(self, text: str) -> None:
        self._filter = " ".join(str(text).split())
        self.filterChanged.emit()
        self._reload()

    @Slot(str, result=int)
    def rowForKey(self, key: str) -> int:
        for row, item in enumerate(self._rows):
            if item["key"] == key:
                return row
        return -1

    def _reload(self) -> None:
        needle = self._filter.casefold()
        rows = [
            {"key": artist.key, "name": artist.name, "trackCount": artist.track_count}
            for artist in self._service.artists()
            if not needle or needle in artist.name.casefold()
        ]
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        self.countChanged.emit()


class ArtistPageModel(QObject):
    """The page of one artist: its tracks, and the two override actions.

    ``oneArtistCredits`` and ``splitCredits`` name the credit texts that each action changes,
    so the page can show what the action applies to before the user chooses it.
    """

    changed = Signal()
    _loaded = Signal(object, int)

    def __init__(
        self,
        service: ArtistIndexService,
        library: LibraryRepository,
        jobs: JobService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._library = library
        self._jobs = jobs
        self._tracks = TrackListModel(self)
        self._key = ""
        self._generation = 0
        self._loaded.connect(self._on_loaded)
        service.indexChanged.connect(self._on_index_changed)

    @Property(QObject, constant=True)
    def tracks(self) -> QObject:
        return self._tracks

    @Property(str, notify=changed)
    def artistKey(self) -> str:
        return self._key

    @Property(str, notify=changed)
    def name(self) -> str:
        entry = self._service.index.entry(self._key) if self._key else None
        return entry.name if entry is not None else ""

    @Property(int, notify=changed)
    def trackCount(self) -> int:
        entry = self._service.index.entry(self._key) if self._key else None
        return entry.track_count if entry is not None else 0

    @Property(list, notify=changed)
    def oneArtistCredits(self) -> list[str]:
        return self._service.one_artist_credits(self._key) if self._key else []

    @Property(list, notify=changed)
    def splitCredits(self) -> list[str]:
        return self._service.split_credits(self._key) if self._key else []

    @Property(bool, notify=changed)
    def canMakeOneArtist(self) -> bool:
        return bool(self.oneArtistCredits)

    @Property(bool, notify=changed)
    def canSplit(self) -> bool:
        return bool(self.splitCredits)

    @Slot(str)
    def open(self, key: str) -> None:
        """Show the page of the artist ``key``; an unknown key clears the page."""
        self._key = key if self._service.index.entry(key) is not None else ""
        self._reload()
        self.changed.emit()

    @Slot()
    def close(self) -> None:
        self._key = ""
        self._generation += 1
        self._tracks.replace([])
        self.changed.emit()

    @Slot()
    def makeOneArtist(self) -> None:
        """ "This is one artist": keep the credits of this artist whole."""
        if self._key:
            self._service.make_one_artist(self._key)

    @Slot()
    def splitArtist(self) -> None:
        """ "Split into separate artists": cut the credits of this artist at every junction."""
        if self._key:
            self._service.split_artist(self._key)

    def _reload(self) -> None:
        self._generation += 1
        generation = self._generation
        identifiers = self._service.tracks_of(self._key) if self._key else []
        if not identifiers:
            self._tracks.replace([])
            return

        def load(_context: JobContext) -> None:
            rows = self._library.tracks_by_ids(identifiers)
            rows.sort(key=lambda row: (str(row.get("title", "")).casefold(), row.get("path", "")))
            self._loaded.emit(rows, generation)

        with suppress(RuntimeError):
            self._jobs.submit(load, label="Load artist tracks", visible=False)

    def _on_loaded(self, rows: object, generation: int) -> None:
        if generation == self._generation and isinstance(rows, list):
            self._tracks.replace(rows)

    def _on_index_changed(self) -> None:
        if self._key and self._service.index.entry(self._key) is None:
            self._key = ""
        self._reload()
        self.changed.emit()

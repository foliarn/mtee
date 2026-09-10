"""Fictitious rows used by the shell of the foundation step.

No file of the user is read here. The explorer step replaces this model with a
catalogue fed by the file system.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

__all__ = ["DEMO_TRACKS", "DemoTrack", "DemoTrackRole", "DemoTracksModel"]


@dataclass(frozen=True, slots=True)
class DemoTrack:
    """One invented row of the Table view."""

    title: str
    artist: str
    genre: str
    bpm: str
    key: str
    duration: str
    file_format: str


DEMO_TRACKS: tuple[DemoTrack, ...] = (
    DemoTrack("Night Terminal", "Aurore Mesnil", "Deep House", "122", "8A", "6:41", "FLAC"),
    DemoTrack("Carrier Wave", "Loop Foundry", "Techno", "134", "5A", "7:12", "WAV"),
    DemoTrack("Slow Return", "Marek Tual", "Ambient", "—", "—", "9:05", "AIFF"),
    DemoTrack("Halogen", "Sœur Kepler", "Electro", "128", "11B", "5:28", "MP3"),
    DemoTrack("Paper Streets", "Nils Abadie", "House", "124", "3A", "6:02", "M4A"),
    DemoTrack("Undertow", "Cassini Div", "Breaks", "140", "9B", "4:47", "OPUS"),
    DemoTrack("Vent d'ouest", "Hélène Roux", "Downtempo", "96", "2A", "5:53", "FLAC"),
    DemoTrack("Static Garden", "Rue Numérique", "Dub Techno", "126", "7A", "8:19", "WAV"),
)


class DemoTrackRole(IntEnum):
    """Roles exposed to QML for the Table view."""

    TITLE = int(Qt.ItemDataRole.UserRole) + 1
    ARTIST = int(Qt.ItemDataRole.UserRole) + 2
    GENRE = int(Qt.ItemDataRole.UserRole) + 3
    BPM = int(Qt.ItemDataRole.UserRole) + 4
    KEY = int(Qt.ItemDataRole.UserRole) + 5
    DURATION = int(Qt.ItemDataRole.UserRole) + 6
    FORMAT = int(Qt.ItemDataRole.UserRole) + 7


class DemoTracksModel(QAbstractListModel):
    """Read-only model of the invented rows."""

    def __init__(
        self, tracks: tuple[DemoTrack, ...] = DEMO_TRACKS, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._tracks)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            int(DemoTrackRole.TITLE): QByteArray(b"title"),
            int(DemoTrackRole.ARTIST): QByteArray(b"artist"),
            int(DemoTrackRole.GENRE): QByteArray(b"genre"),
            int(DemoTrackRole.BPM): QByteArray(b"bpm"),
            int(DemoTrackRole.KEY): QByteArray(b"musicalKey"),
            int(DemoTrackRole.DURATION): QByteArray(b"duration"),
            int(DemoTrackRole.FORMAT): QByteArray(b"fileFormat"),
        }

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ):
        if not index.isValid() or not 0 <= index.row() < len(self._tracks):
            return None
        track = self._tracks[index.row()]
        match role:
            case DemoTrackRole.TITLE | Qt.ItemDataRole.DisplayRole:
                return track.title
            case DemoTrackRole.ARTIST:
                return track.artist
            case DemoTrackRole.GENRE:
                return track.genre
            case DemoTrackRole.BPM:
                return track.bpm
            case DemoTrackRole.KEY:
                return track.key
            case DemoTrackRole.DURATION:
                return track.duration
            case DemoTrackRole.FORMAT:
                return track.file_format
            case _:
                return None

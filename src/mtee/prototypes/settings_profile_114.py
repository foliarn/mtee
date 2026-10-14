"""Disposable interaction model for the plan 114-115 user review.

It owns sample data only. Nothing here reads or writes the MTEE database, the
settings, the profile folder or any audio file; the file choices are fixed
examples. The real behaviour is in the services of steps 114 and 115.
"""

# Qt properties and slots keep the camelCase names consumed by QML.
# ruff: noqa: N802

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

__all__ = ["SettingsProfilePrototype", "create_avatar"]

CATEGORIES = [
    ("general", "General"),
    ("library", "Library"),
    ("playback", "Playback"),
    ("analysis", "Analysis"),
    ("shortcuts", "Keyboard shortcuts"),
    ("privacy", "Data & privacy"),
    ("about", "About"),
]
PERIODS = [
    ("week", "This week"),
    ("month", "This month"),
    ("year", "This year"),
    ("all", "All time"),
]
DIALOGS = ("", "clear-history", "reset-statistics", "restore-confirm")

SHORTCUTS = [
    ("Play or pause", "Space"),
    ("Play the selected track", "Enter"),
    ("Select all", "Ctrl+A"),
    ("Show or hide the info panel", "Ctrl+I"),
    ("Undo last edit", "Ctrl+Z"),
    ("Save edits", "Ctrl+S"),
    ("Show Explorer", "Ctrl+Shift+E"),
    ("Toggle sidebar", "Ctrl+B"),
    ("Split editor", "Ctrl+\\"),
    ("Close tab", "Ctrl+W"),
    ("Next track", "Ctrl+Right"),
    ("Previous track", "Ctrl+Left"),
    ("Move selected files to the Recycle Bin", "Delete"),
    ("Fullscreen player", "F11"),
    ("Leave fullscreen", "Esc"),
    ("Settings", "Ctrl+,"),
]

RULES = [
    {"id": "r1", "text": "Burial feat. Four Tet", "decision": "This is one artist"},
    {"id": "r2", "text": "Kode9 & Spaceape", "decision": "Split into separate artists"},
    {"id": "r3", "text": "Skream, Benga", "decision": "Split into separate artists"},
    {"id": "r4", "text": "DJ Rashad x DJ Spinn", "decision": "This is one artist"},
]

TRACKS = [
    ("Archangel", "Burial", "Burial", "8A", 140, "4:32", 26, "2026-10-13"),
    ("Midnight Request Line", "Skream", "Skream", "8A", 140, "5:58", 19, "2026-10-12"),
    ("Night", "Skream & Benga", "Skream", "8A", 140, "6:06", 11, "2026-10-09"),
    ("Router", "Pangaea", "Pangaea", "5B", 138, "5:21", 7, "2026-09-28"),
    ("Changes", "Mala", "Mala", "2B", 140, "6:44", 9, "2026-10-05"),
    ("Sine", "Kode9, Spaceape", "Sine", "12A", 70, "4:11", 4, "2026-08-30"),
    ("Crunked Up", "Benga", "Crunked Up", "10A", 68, "3:55", 3, "2026-07-14"),
    ("Long Way Down", "Four Tet", "Rounds", "1B", 124, "5:12", 0, ""),
    ("Stepping Out", "Pinch", "Dub Plates", "4A", 136, "7:03", 2, "2026-09-02"),
    ("Dub Pressure", "Digital Mystikz", "Digital Mystikz", "9A", 140, "5:40", 0, ""),
]


def create_avatar(data_dir: Path) -> Path:
    """Paint a square sample avatar in the review folder (never a user picture)."""
    target = data_dir / "review" / "avatar-sample.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 256, 256)
    gradient.setColorAt(0.0, QColor("#C6FF1A"))
    gradient.setColorAt(1.0, QColor("#FF2E88"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(QColor("#0A0A0A"))
    font = painter.font()
    font.setPointSize(96)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), 0x84, "AL")
    painter.end()
    image.save(str(target))  # the format follows the .png suffix
    return target


def _series(kind: str, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    if kind == "week":
        labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    elif kind == "month":
        labels = [str(day) for day in range(1, 32)]
    elif kind == "year":
        labels = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
    else:
        labels = [
            f"{month} '{str(year)[2:]}"
            for year in (2024, 2025, 2026)
            for month in (
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            )
        ][:34]
    return [
        {"label": label, "minutes": rng.randint(0, 150) if rng.random() > 0.2 else 0}
        for label in labels
    ]


def _empty_stats(kind: str) -> dict[str, Any]:
    """The page after a statistics reset: every figure is zero, the chart keeps its axis."""
    series = [{**bar, "minutes": 0} for bar in _series(kind, seed=0)]
    return {
        "listening": "0 h 00 min",
        "plays": "0",
        "sessions": "0",
        "tracks": [],
        "artists": [],
        "albums": [],
        "series": series,
    }


def _stats(kind: str) -> dict[str, Any]:
    scale = {"week": 1, "month": 4, "year": 30, "all": 120}[kind]
    tracks = [
        {
            "title": title,
            "artist": artist,
            "album": album,
            "plays": max(1, plays * scale // 6),
        }
        for title, artist, album, _key, _bpm, _len, plays, _last in TRACKS[:6]
    ]
    tracks.sort(key=lambda row: -row["plays"])
    artists = [
        {"name": "Burial", "plays": 26 * scale // 6},
        {"name": "Skream", "plays": 30 * scale // 6},
        {"name": "Mala", "plays": 9 * scale // 6},
        {"name": "Pangaea", "plays": 7 * scale // 6},
    ]
    albums = [
        {"name": "Burial", "plays": 26 * scale // 6},
        {"name": "Dub Plates", "plays": 2 * scale // 6 + 1},
        {"name": "Digital Mystikz", "plays": 4 * scale // 6 + 1},
    ]
    minutes = {"week": 402, "month": 1_576, "year": 9_930, "all": 31_208}[kind]
    plays = {"week": 38, "month": 164, "year": 1_122, "all": 3_480}[kind]
    sessions = plays + {"week": 5, "month": 21, "year": 140, "all": 402}[kind]
    return {
        "listening": f"{minutes // 60} h {minutes % 60:02d} min",
        "plays": f"{plays:,}",
        "sessions": f"{sessions:,}",
        "tracks": tracks,
        "artists": sorted(artists, key=lambda row: -row["plays"]),
        "albums": sorted(albums, key=lambda row: -row["plays"]),
        "series": _series(kind, seed=len(kind) * 7),
    }


class SettingsProfilePrototype(QObject):
    """Sample state of the Settings, Profile, Explorer columns and dialogs."""

    changed = Signal()

    def __init__(self, data_dir: Path, *, avatar_path: Path | None = None) -> None:
        super().__init__()
        self._avatar = avatar_path or create_avatar(data_dir)
        self._view = "settings"
        self._category = "general"
        self._dialog = ""
        self._message = ""
        self._profile_name = "Ana Lima"
        self._has_avatar = True
        self._period = "month"
        self._stats = {kind: _stats(kind) for kind, _ in PERIODS}
        self._statistics_reset = False
        self._history_count = 100
        self._restore_pending = False
        self._last_backup = ""
        self._columns = {"plays": False, "lastPlayed": False}
        self._sort = "title"
        self._settings: dict[str, Any] = {
            "island": True,
            "normalize": True,
            "level": "normal",
            "previewTabs": True,
            "notation": "camelot",
            "bpmMin": 70,
            "bpmMax": 180,
            "decimals": 1,
            "parallel": 2,
            "writeTags": False,
        }
        self._rules = [dict(rule) for rule in RULES]

    @Property(str, notify=changed)
    def view(self) -> str:
        return self._view

    @Property(str, notify=changed)
    def category(self) -> str:
        return self._category

    @Property(list, constant=True)
    def categories(self) -> list[dict[str, str]]:
        return [{"key": key, "label": label} for key, label in CATEGORIES]

    @Property(list, constant=True)
    def periods(self) -> list[dict[str, str]]:
        return [{"key": key, "label": label} for key, label in PERIODS]

    @Property(list, constant=True)
    def shortcuts(self) -> list[dict[str, str]]:
        return [{"action": action, "keys": keys} for action, keys in SHORTCUTS]

    @Property(list, notify=changed)
    def rules(self) -> list[dict[str, str]]:
        return self._rules

    @Property(dict, notify=changed)
    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    @Property(str, notify=changed)
    def dialog(self) -> str:
        return self._dialog

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._message

    @Property(str, notify=changed)
    def profileName(self) -> str:
        return self._profile_name

    @Property(str, notify=changed)
    def avatarSource(self) -> str:
        return self._avatar.as_uri() if self._has_avatar else ""

    @Property(int, notify=changed)
    def historyCount(self) -> int:
        return self._history_count

    @Property(bool, notify=changed)
    def restorePending(self) -> bool:
        return self._restore_pending

    @Property(str, notify=changed)
    def lastBackup(self) -> str:
        return self._last_backup

    @Property(str, notify=changed)
    def period(self) -> str:
        return self._period

    @Property(str, notify=changed)
    def periodLabel(self) -> str:
        return dict(PERIODS)[self._period]

    @Property(dict, notify=changed)
    def stats(self) -> dict[str, Any]:
        if self._statistics_reset:
            return _empty_stats(self._period)
        return self._stats[self._period]

    @Property(dict, notify=changed)
    def columns(self) -> dict[str, bool]:
        return dict(self._columns)

    @Property(str, notify=changed)
    def sort(self) -> str:
        return self._sort

    @Property(list, notify=changed)
    def tracks(self) -> list[dict[str, Any]]:
        rows = [
            {
                "title": title,
                "artist": artist,
                "album": album,
                "key": key,
                "bpm": bpm,
                "length": length,
                "plays": plays,
                "lastPlayed": last or "Never",
            }
            for title, artist, album, key, bpm, length, plays, last in TRACKS
        ]
        if self._sort == "plays":
            rows.sort(key=lambda row: -row["plays"])
        return rows

    @Slot(str)
    def setView(self, view: str) -> None:
        self._view = view
        self._message = ""
        self._emit()

    @Slot(str)
    def setCategory(self, key: str) -> None:
        self._category = key
        self._message = ""
        self._emit()

    @Slot(str, bool)
    def setBool(self, key: str, value: bool) -> None:
        if key in self._settings:
            self._settings[key] = bool(value)
            self._emit()

    @Slot(str, str)
    def setText(self, key: str, value: str) -> None:
        if key in self._settings:
            self._settings[key] = value
            self._emit()

    @Slot(str, int)
    def setInt(self, key: str, value: int) -> None:
        if key in self._settings:
            self._settings[key] = int(value)
            self._emit()

    @Slot(str)
    def removeRule(self, rule_id: str) -> None:
        removed = next((rule for rule in self._rules if rule["id"] == rule_id), None)
        if removed is not None:
            self._rules = [rule for rule in self._rules if rule["id"] != rule_id]
            self._message = f"Removed the rule for {removed['text']}."
            self._emit()

    @Slot(str)
    def setPeriod(self, key: str) -> None:
        if key in self._stats:
            self._period = key
            self._emit()

    @Slot(str)
    def setDisplayName(self, value: str) -> None:
        cleaned = value.strip()
        if cleaned:
            self._profile_name = cleaned
            self._message = "Display name saved. Playlists show it as their creator."
        else:
            self._message = "Use a display name between 1 and 240 characters."
        self._emit()

    @Slot()
    def chooseAvatar(self) -> None:
        self._has_avatar = True
        self._message = (
            "Picture copied into the MTEE profile folder. The original file is untouched."
        )
        self._emit()

    @Slot()
    def removeAvatar(self) -> None:
        self._has_avatar = False
        self._message = "Picture removed. MTEE shows the default avatar."
        self._emit()

    @Slot(str)
    def openDialog(self, kind: str) -> None:
        if kind in DIALOGS:
            self._dialog = kind
            self._emit()

    @Slot()
    def closeDialog(self) -> None:
        self._dialog = ""
        self._emit()

    @Slot()
    def confirmClearHistory(self) -> None:
        self._history_count = 0
        self._dialog = ""
        self._message = "History cleared. The statistics are not affected."
        self._emit()

    @Slot()
    def confirmResetStatistics(self) -> None:
        self._statistics_reset = True
        self._dialog = ""
        self._message = "Statistics reset. Listening events removed: 3,480."
        self._emit()

    @Slot()
    def backUp(self) -> None:
        self._last_backup = "mtee-backup-20261014-120000.sqlite3"
        self._message = f"Backup saved as {self._last_backup}, checked with an integrity test."
        self._emit()

    @Slot()
    def chooseBackupFile(self) -> None:
        self._dialog = "restore-confirm"
        self._emit()

    @Slot()
    def scheduleRestore(self) -> None:
        self._restore_pending = True
        self._dialog = ""
        self._message = "Restore scheduled. Restart MTEE to apply it."
        self._emit()

    @Slot()
    def cancelRestore(self) -> None:
        self._restore_pending = False
        self._message = "The scheduled restore was cancelled."
        self._emit()

    @Slot(str, bool)
    def setColumn(self, key: str, value: bool) -> None:
        if key in self._columns:
            self._columns[key] = bool(value)
            self._emit()

    @Slot(str)
    def sortBy(self, key: str) -> None:
        self._sort = key
        self._emit()

    def _emit(self) -> None:
        self.changed.emit()

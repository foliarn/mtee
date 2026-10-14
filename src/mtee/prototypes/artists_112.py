"""Disposable interaction model for the plan 112 user review of the Artists view.

It owns synthetic tracks only. The artist rules are the real ``mtee.domain.artist_index``
functions, so the splitting and the two override actions behave as the core will. Nothing is
written: no database, no tag and no audio file is touched, and Play / Shuffle only report.
"""

# Qt properties and slots keep the camelCase names consumed by QML.
# ruff: noqa: N802

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.artist_index import (
    MODE_ONE_ARTIST,
    MODE_SPLIT,
    ArtistIndex,
    build_artist_index,
)
from mtee.domain.artists import clean_name, normalize_key

# (title, Artist tag, album, seconds). The tags are the ones a collection really holds.
SYNTHETIC_TRACKS: tuple[tuple[str, str, str, int], ...] = (
    ("Blind Faith", "Chase", "Solo Sessions", 214),
    ("Pluto", "Chase & Status", "Brand New Machine", 233),
    ("Count Me Out", "Chase & Status", "Brand New Machine", 247),
    ("Take Me Back", "Chase & Status feat. Takura", "No Introduction", 262),
    ("Dreamin", "Camo & Krooked", "Tomorrow", 241),
    ("Hindsight", "Camo & Krooked", "Tomorrow", 226),
    ("Lime", "T & Sugah", "Sugah Sessions", 205),
    ("Tidal Wave", "Sub Focus & Wilkinson", "Sub Focus", 232),
    ("Endorphin", "Sub Focus", "Sub Focus", 219),
    ("Afterglow", "Wilkinson", "Afterglow EP", 210),
    ("Tiny Fire", "Nikita, the Wicked", "Single", 198),
    ("Ballistic", "Bou, Hedex", "Ballistic", 240),
    ("Dust", "Hedex", "Dust", 222),
    ("Ruin", "MPH", "Ruin", 204),
    ("Turbulence", "MPH x A+", "Turbulence", 231),
    ("Archangel", "Burial", "Untrue", 252),
    ("Ghost Hymn", "Burial feat. Thom Yorke", "Ghost Hymns", 266),
    ("Midnight Request Line", "Skream", "Skream!", 241),
    ("Crunked Up (Skream Remix)", "Benga", "Crunked Up", 218),
)

SCENARIOS = ("default", "selected", "search", "after")


@dataclass
class _Track:
    identity: str
    title: str
    artist: str
    album: str
    seconds: int


def _clock(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


class ArtistsReviewPrototype(QObject):
    """Artists list, one artist page and the two override actions, on synthetic tags."""

    changed = Signal()

    def __init__(self, scenario: str = "default") -> None:
        super().__init__()
        self._tracks = [
            _Track(
                str(uuid5(NAMESPACE_URL, f"mtee-112-review-{number}")),
                title,
                artist,
                album,
                seconds,
            )
            for number, (title, artist, album, seconds) in enumerate(SYNTHETIC_TRACKS)
        ]
        self._overrides: dict[str, tuple[str, str]] = {}
        self._search = ""
        self._key = ""
        self._message = ""
        self._index = ArtistIndex()
        self._rebuild()
        if scenario in ("selected", "after"):
            self._key = "status"
        if scenario == "search":
            self._search = "sub"
        if scenario == "after":
            # "Status" was cut from "Chase & Status": keeping that credit whole ends its page.
            self.makeOneArtist()
            self._key = "chase & status"
        self.changed.emit()

    # ------------------------------------------------------------------ rules

    def _rebuild(self) -> None:
        rows = [(track.identity, (track.artist,)) for track in self._tracks]
        self._index = build_artist_index(rows, self._overrides)

    def _artist_rows(self) -> list[dict[str, Any]]:
        needle = normalize_key(self._search)
        return [
            {"key": artist.key, "name": artist.name, "trackCount": artist.track_count}
            for artist in self._index.artists
            if not needle or needle in artist.name.casefold()
        ]

    def _entry(self) -> Any:
        return self._index.entry(self._key) if self._key else None

    # ------------------------------------------------------------------ properties

    @Property(list, notify=changed)
    def artists(self) -> list[dict[str, Any]]:
        return self._artist_rows()

    @Property(int, notify=changed)
    def totalCount(self) -> int:
        return len(self._index.artists)

    @Property(str, notify=changed)
    def search(self) -> str:
        return self._search

    @Property(str, notify=changed)
    def artistKey(self) -> str:
        return self._key if self._entry() is not None else ""

    @Property(str, notify=changed)
    def artistName(self) -> str:
        entry = self._entry()
        return entry.name if entry is not None else ""

    @Property(int, notify=changed)
    def trackCount(self) -> int:
        entry = self._entry()
        return entry.track_count if entry is not None else 0

    @Property(list, notify=changed)
    def tracks(self) -> list[dict[str, Any]]:
        entry = self._entry()
        if entry is None:
            return []
        identities = set(self._index.tracks_by_artist.get(entry.key, ()))
        found = [track for track in self._tracks if track.identity in identities]
        found.sort(key=lambda track: (track.title.casefold(), track.album.casefold()))
        return [
            {
                "id": track.identity,
                "number": number,
                "title": track.title,
                "album": track.album,
                "time": _clock(track.seconds),
            }
            for number, track in enumerate(found, start=1)
        ]

    @Property(list, notify=changed)
    def artistCredits(self) -> list[str]:
        """The credits this artist was cut from (its own name, when it was never cut)."""
        entry = self._entry()
        return list(entry.origins) if entry is not None else []

    @Property(list, notify=changed)
    def oneArtistCredits(self) -> list[str]:
        return self._index.one_artist_credits(self._key) if self._entry() is not None else []

    @Property(list, notify=changed)
    def splitCredits(self) -> list[str]:
        return self._index.split_credits(self._key) if self._entry() is not None else []

    @Property(bool, notify=changed)
    def canMakeOneArtist(self) -> bool:
        return bool(self.oneArtistCredits)

    @Property(bool, notify=changed)
    def canSplit(self) -> bool:
        return bool(self.splitCredits)

    @Property(str, notify=changed)
    def message(self) -> str:
        return self._message

    @Property(list, notify=changed)
    def choices(self) -> list[dict[str, str]]:
        return [
            {"text": text, "mode": "This is one artist" if mode == MODE_ONE_ARTIST else "Split"}
            for text, mode in self._overrides.values()
        ]

    # ------------------------------------------------------------------ slots

    @Slot(str)
    def setSearch(self, text: str) -> None:
        self._search = " ".join(str(text).split())
        self.changed.emit()

    @Slot(str)
    def selectArtist(self, key: str) -> None:
        self._key = key if self._index.entry(key) is not None else ""
        self._message = "" if self._key else "That artist is no longer in the list."
        self.changed.emit()

    @Slot()
    def makeOneArtist(self) -> None:
        self._apply(self.oneArtistCredits, MODE_ONE_ARTIST, "kept whole")

    @Slot()
    def splitArtist(self) -> None:
        self._apply(self.splitCredits, MODE_SPLIT, "split")

    @Slot()
    def resetChoices(self) -> None:
        self._overrides.clear()
        self._rebuild()
        self._message = "Every choice is cleared in this mock-up."
        self.changed.emit()

    @Slot()
    def play(self) -> None:
        self._message = "Play is not connected in this mock-up: nothing is played."
        self.changed.emit()

    @Slot()
    def shuffle(self) -> None:
        self._message = "Shuffle is not connected in this mock-up: nothing is played."
        self.changed.emit()

    def _apply(self, credits: list[str], mode: str, verb: str) -> None:
        if not credits:
            self._message = "Nothing to change for this artist."
            self.changed.emit()
            return
        for credit in credits:
            self._overrides[normalize_key(credit)] = (clean_name(credit), mode)
        self._rebuild()
        if self._index.entry(self._key) is None:
            self._key = ""
        self._message = f"{', '.join(f'“{credit}”' for credit in credits)} {verb}."
        self.changed.emit()

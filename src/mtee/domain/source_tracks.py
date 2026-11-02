"""Tracks that have no file on this computer, and the way the player reaches their audio.

A plugin may provide tracks of its own (for example the tracks of a server). The core gives
each of them a normal ``track_id`` and stores its display metadata, but there is no file: the
audio comes from a ``PlayableSource`` that the plugin resolves when the track is played.

A track row handed to the interface carries ``sourcePluginId`` (the plugin) and ``sourceKey``
(its own key) exactly when the track has no file. No code that reads, writes, moves or trashes
a file may be given such a row; ``require_file_track`` is the one check they share.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo

__all__ = [
    "MAX_SOURCE_KEY_LENGTH",
    "NonFileTrackError",
    "PlayableSource",
    "SourceTrack",
    "SourceTrackEntry",
    "is_non_file_row",
    "non_file_message",
    "row_is_available",
]

MAX_SOURCE_KEY_LENGTH = 512
_MAX_TEXT_LENGTH = 2000
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class NonFileTrackError(ValueError):
    """A file operation was asked for a track that has no file on this computer."""

    readable = True


def non_file_message(plugin_title: str, what: str = "") -> str:
    """Return the sentence that explains why a file operation does not apply to a track."""
    origin = f" provided by {plugin_title}" if plugin_title else " provided by a plugin"
    action = f" {what}" if what else ""
    return f"This track is{origin} and has no file on this computer, so it cannot be{action}."


def is_non_file_row(row: Mapping[str, Any]) -> bool:
    """Return whether a track row (as the interface receives it) is a track without a file."""
    return bool(row.get("sourcePluginId"))


def row_is_available(row: Mapping[str, Any]) -> bool:
    """Return whether a track row without a file can be played now.

    A plugin track is available while the plugin provides it and is running; the repository
    puts that in ``status`` (``readable`` or ``unreadable``).
    """
    return is_non_file_row(row) and str(row.get("status", "")) == "readable"


def require_file_track(row: Mapping[str, Any], what: str, plugin_title: str = "") -> None:
    """Raise ``NonFileTrackError`` when ``row`` is a track without a file."""
    if is_non_file_row(row):
        raise NonFileTrackError(non_file_message(plugin_title or str(row["sourcePluginId"]), what))


def _text(name: str, value: object, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    text = value.strip()
    if required and not text:
        raise ValueError(f"{name} must not be empty")
    if len(text) > _MAX_TEXT_LENGTH:
        raise ValueError(f"{name} is longer than {_MAX_TEXT_LENGTH} characters")
    return text


def _texts(name: str, value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{name} must be a string or a sequence of strings")
    return tuple(text for item in value if (text := _text(name, item)))


@dataclass(frozen=True, slots=True)
class SourceTrack:
    """The display metadata of one track a plugin provides, under the plugin's own key.

    ``source_key`` identifies the track within the plugin and never changes for it.
    ``artists`` and ``genre`` take a string for one value or a sequence for several.
    ``duration_us`` is the length in microseconds (``0`` when unknown). The cover is not
    part of this record: the plugin's ``TrackSource.cover`` provides it on demand.
    """

    source_key: str
    title: str
    artists: tuple[str, ...] = ()
    album: str = ""
    album_artist: str = ""
    track_number: int | None = None
    duration_us: int = 0
    genre: tuple[str, ...] = ()
    year: int | None = None

    def __post_init__(self) -> None:
        key = _text("source_key", self.source_key, required=True)
        if len(key) > MAX_SOURCE_KEY_LENGTH:
            raise ValueError(f"source_key is longer than {MAX_SOURCE_KEY_LENGTH} characters")
        object.__setattr__(self, "source_key", key)
        object.__setattr__(self, "title", _text("title", self.title))
        object.__setattr__(self, "artists", _texts("artists", self.artists))
        object.__setattr__(self, "album", _text("album", self.album))
        object.__setattr__(self, "album_artist", _text("album_artist", self.album_artist))
        object.__setattr__(self, "genre", _texts("genre", self.genre))
        for name, value in (
            ("track_number", self.track_number),
            ("year", self.year),
        ):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a whole number, zero or more, or None")
        if type(self.duration_us) is not int or self.duration_us < 0:
            raise ValueError("duration_us must be a whole number of microseconds, zero or more")

    def snapshot(self) -> MetadataSnapshot:
        """Return the metadata in the type MTEE uses for the tags of a file."""
        return MetadataSnapshot(
            title=(self.title,) if self.title else (),
            artist=self.artists,
            album=(self.album,) if self.album else (),
            genre=self.genre,
            date=(str(self.year),) if self.year else (),
            track_number=(str(self.track_number),) if self.track_number else (),
            technical=TechnicalInfo(duration_us=self.duration_us or None),
        )

    @classmethod
    def from_snapshot(
        cls, source_key: str, snapshot: MetadataSnapshot, album_artist: str = ""
    ) -> SourceTrack:
        """Rebuild the record from what the core stored."""
        year = snapshot.date[0] if snapshot.date else ""
        number = snapshot.track_number[0] if snapshot.track_number else ""
        return cls(
            source_key=source_key,
            title=snapshot.title[0] if snapshot.title else "",
            artists=snapshot.artist,
            album=snapshot.album[0] if snapshot.album else "",
            album_artist=album_artist,
            track_number=int(number) if number.isdigit() else None,
            duration_us=snapshot.technical.duration_us or 0,
            genre=snapshot.genre,
            year=int(year) if year.isdigit() else None,
        )


@dataclass(frozen=True, slots=True)
class SourceTrackEntry:
    """A track a plugin provides, as the core stores it.

    ``available`` is ``False`` after ``remove``: the row, its ``track_id``, the playlist
    entries and the play log rows stay, and the track cannot be played.
    """

    track_id: str
    track: SourceTrack
    available: bool

    @property
    def source_key(self) -> str:
        return self.track.source_key


@dataclass(frozen=True, slots=True)
class PlayableSource:
    """Where the audio of a track can be read: a local file, or a URL with headers.

    Exactly one of ``path`` and ``url`` is set. ``path`` is a file the plugin made (for
    example a download); the core plays it and holds a read lease on it like on a library
    file. ``url`` is ``http`` or ``https``; ``headers`` are sent with the requests for this
    track only (for example ``Authorization``). A URL source is never locked.
    """

    path: Path | None = None
    url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.path is None) == (self.url is None):
            raise ValueError("A playable source is either a path or a url, not both or neither.")
        if self.path is not None:
            object.__setattr__(self, "path", Path(self.path))
            if self.headers:
                raise ValueError("Headers go with a url, not with a local path.")
        if self.url is not None:
            parts = urlsplit(self.url)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.netloc
                or _CONTROL.search(self.url)
            ):
                raise ValueError("A url source must be an http or https address.")
        checked: dict[str, str] = {}
        for name, value in dict(self.headers).items():
            if not isinstance(name, str) or not _HEADER_NAME.match(name):
                raise ValueError(f"{name!r} is not a valid HTTP header name.")
            if not isinstance(value, str) or _CONTROL.search(value):
                raise ValueError(f"The value of header {name} has a control character.")
            if value.endswith("\\"):
                raise ValueError(f"The value of header {name} must not end with a backslash.")
            checked[name] = value
        object.__setattr__(self, "headers", checked)

    def __repr__(self) -> str:
        # The header values and the query of a url may be secrets (tokens): a log never gets them.
        host = urlsplit(self.url).hostname if self.url else None
        names = ", ".join(self.headers)
        return f"PlayableSource(path={self.path!r}, host={host!r}, headers=[{names}])"

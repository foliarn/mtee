"""Artists of the core Artists view, read from the Artist tag of the files.

The Album Artist tag and the titles (``(X Remix)``) are never read: a remixer is not
credited. A credit is the Artist tag of a track, and it is cut in three steps:

1. A comma, ``feat.`` or ``ft.`` (any case, with or without the dot, as a separate word)
   always separates two artists.
2. A ``&`` or an ``x`` / ``X`` with a space on each side (`` & ``, `` x ``) separates two
   names only when at least one of the two names is a *solo* artist: a name that is the
   whole Artist tag of some track. With three or more names, each junction is decided on
   its own, from the two names it joins as they are cut so far.
3. The user overrides, stored by the core, win over those rules. A ``one_artist`` override
   keeps its credit text whole (no cut inside it). A ``split`` override cuts every junction
   of its credit, whatever the solo artists are.

Names are compared with ``normalize_key``: case and spacing are not significant.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass, field
from typing import Any

from mtee.domain.artists import choose_spelling, clean_name, normalize_key

__all__ = [
    "MODE_ONE_ARTIST",
    "MODE_SPLIT",
    "ArtistEntry",
    "ArtistIndex",
    "CreditPart",
    "CreditRules",
    "album_track_order",
    "build_artist_index",
    "has_separator",
    "solo_artist_keys",
    "split_artist_credit",
    "split_credit_parts",
]

MODE_ONE_ARTIST = "one_artist"
MODE_SPLIT = "split"
OVERRIDE_MODES: tuple[str, ...] = (MODE_ONE_ARTIST, MODE_SPLIT)

# A strong separator takes the spaces around it. ``feat`` and ``ft`` are whole words only:
# ``Left`` or ``Rift`` do not match.
_STRONG_SEPARATOR = re.compile(r"\s*,\s*|\s*\b(?:feat|ft)\b\.?\s*", re.IGNORECASE)
_JUNCTION = re.compile(r"\s+&\s+|\s+x\s+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _Segment:
    """A piece of a credit cut at the strong separators; ``protected`` keeps it whole."""

    text: str
    protected: bool


@dataclass(frozen=True, slots=True)
class CreditPart:
    """One artist of a credit, with the strong segment it was cut from."""

    name: str
    origin: str


@dataclass(frozen=True, slots=True)
class ArtistEntry:
    """One artist of the library: its display name, its tracks and where its names came from.

    ``origins`` are the strong segments of the credits that produced the name (for example
    ``Chase & Status`` for the artist ``Chase``). The Artists view applies its overrides to
    them.
    """

    key: str
    name: str
    track_count: int
    origins: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtistIndex:
    """The artist index of one library state; immutable, built off the graphical thread."""

    artists: tuple[ArtistEntry, ...] = ()
    tracks_by_artist: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    artists_by_track: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    solo_keys: frozenset[str] = frozenset()
    entries: Mapping[str, ArtistEntry] = field(default_factory=dict)

    def entry(self, key: str) -> ArtistEntry | None:
        return self.entries.get(key)

    def one_artist_credits(self, key: str) -> list[str]:
        """Credits that "This is one artist" keeps whole for ``key``: those it was cut from.

        A name that was never cut has none.
        """
        entry = self.entry(key)
        if entry is None:
            return []
        return _one_credit_per_key(
            origin for origin in entry.origins if normalize_key(origin) != key
        )

    def split_credits(self, key: str) -> list[str]:
        """Credits that "Split into separate artists" cuts for ``key``.

        Only a name that holds a separator itself can be split: a plain name has nothing to cut.
        """
        entry = self.entry(key)
        if entry is None or not has_separator(entry.name):
            return []
        return _one_credit_per_key(entry.origins)


@dataclass(frozen=True, slots=True)
class CreditRules:
    """The inputs of the splitting rules, read once from the index and the user's choices.

    A worker that splits many credits (the statistics) holds one of these, so it answers
    as the Artists view and the tag editor do, without reading the index itself.
    """

    solo: frozenset[str] = frozenset()
    one_names: tuple[str, ...] = ()
    split_keys: frozenset[str] = frozenset()

    def split(self, text: str) -> list[str]:
        """The artist names of one credit under these rules."""
        return split_artist_credit(
            text, solo=self.solo, one_names=self.one_names, split_keys=self.split_keys
        )


def _track_number(text: str) -> float:
    """The first number of a track-number tag (``3`` or ``3/12``); a missing one sorts last."""
    head = text.split("/", 1)[0].strip()
    return float(int(head)) if head.isdecimal() else math.inf


def album_track_order(row: Mapping[str, Any]) -> tuple[str, float, str, str]:
    """Sort key of a track on an artist page: album, then track number, then title."""
    return (
        str(row.get("album", "")).casefold(),
        _track_number(str(row.get("trackNumber", ""))),
        str(row.get("title", "")).casefold(),
        str(row.get("id", "")),
    )


def _one_credit_per_key(credits: Iterable[str]) -> list[str]:
    """Keep the first spelling of each credit: two spellings of one credit are one choice."""
    kept: dict[str, str] = {}
    for credit in credits:
        kept.setdefault(normalize_key(credit), credit)
    return list(kept.values())


def has_separator(text: str) -> bool:
    """Return whether ``text`` holds a comma, ``feat.``, ``ft.``, ``&`` or ``x`` junction."""
    cleaned = clean_name(text)
    return _STRONG_SEPARATOR.search(cleaned) is not None or _JUNCTION.search(cleaned) is not None


def _strong_segments(text: str, one_names: Sequence[str]) -> list[_Segment]:
    """Cut ``text`` at the strong separators, keeping each protected name whole.

    The longest protected name wins, and only when it stands between two separators or
    between a separator and the end of the text.
    """
    names = sorted(
        {clean_name(name) for name in one_names if clean_name(name)},
        key=lambda name: (-len(name), name),
    )
    segments: list[_Segment] = []
    position = 0
    while position < len(text):
        remaining = text[position:]
        for name in names:
            if remaining[: len(name)].casefold() != name.casefold():
                continue
            rest = remaining[len(name) :]
            separator = _STRONG_SEPARATOR.match(rest)
            if rest and separator is None:
                continue
            # The tag's own spelling is kept: only the comparison ignores case and spacing.
            segments.append(_Segment(remaining[: len(name)], protected=True))
            position += len(name) + (separator.end() if separator else 0)
            break
        else:
            separator = _STRONG_SEPARATOR.search(remaining)
            if separator is None:
                segments.append(_Segment(remaining, protected=False))
                break
            segments.append(_Segment(remaining[: separator.start()], protected=False))
            position += separator.end()
    return [
        _Segment(clean_name(segment.text), segment.protected)
        for segment in segments
        if clean_name(segment.text)
    ]


def _cut_junctions(segment: _Segment, solo: Set[str], forced: bool) -> list[str]:
    """Cut one unprotected segment at its ``&`` and ``x`` junctions, one junction at a time."""
    if segment.protected:
        return [segment.text]
    tokens: list[str] = []
    junctions: list[str] = []
    last = 0
    for match in _JUNCTION.finditer(segment.text):
        tokens.append(segment.text[last : match.start()])
        junctions.append(match.group())
        last = match.end()
    if not junctions:
        return [segment.text]
    tokens.append(segment.text[last:])
    names: list[str] = []
    current = tokens[0]
    for index, junction in enumerate(junctions):
        left, right = tokens[index], tokens[index + 1]
        cut_here = forced or normalize_key(left) in solo or normalize_key(right) in solo
        if cut_here:
            names.append(current)
            current = right
        else:
            current = f"{current}{junction}{right}"
    names.append(current)
    return names


def split_credit_parts(
    text: str,
    *,
    solo: Set[str] = frozenset(),
    one_names: Sequence[str] = (),
    split_keys: Set[str] = frozenset(),
) -> list[CreditPart]:
    """Return the artists of one credit, in order, each with its origin segment.

    ``solo`` holds the normalized names that are the sole artist of some track.
    ``one_names`` are the credit texts of ``one_artist`` overrides, and ``split_keys`` the
    normalized credit texts of ``split`` overrides.
    """
    whole = normalize_key(text)
    split_whole = whole in split_keys
    parts: list[CreditPart] = []
    for segment in _strong_segments(clean_name(text), one_names):
        forced = not segment.protected and (
            split_whole or normalize_key(segment.text) in split_keys
        )
        for name in _cut_junctions(segment, solo, forced):
            cleaned = clean_name(name)
            if cleaned:
                parts.append(CreditPart(cleaned, segment.text))
    return parts


def split_artist_credit(
    text: str,
    *,
    solo: Set[str] = frozenset(),
    one_names: Sequence[str] = (),
    split_keys: Set[str] = frozenset(),
) -> list[str]:
    """Return the artist names of one credit; see ``split_credit_parts``."""
    return [
        part.name
        for part in split_credit_parts(text, solo=solo, one_names=one_names, split_keys=split_keys)
    ]


def solo_artist_keys(credits: Iterable[Sequence[str]]) -> frozenset[str]:
    """Return the normalized names that are the whole Artist tag of at least one track.

    A track counts when its Artist tag holds exactly one credit, with no junction. Its single
    name is solo; a track crediting two artists gives no solo name.
    """
    solo: set[str] = set()
    for values in credits:
        cleaned = [clean_name(value) for value in values if clean_name(value)]
        if len(cleaned) != 1 or _JUNCTION.search(cleaned[0]):
            continue
        segments = _strong_segments(cleaned[0], ())
        if len(segments) == 1:
            solo.add(normalize_key(segments[0].text))
    return frozenset(solo)


def build_artist_index(
    tracks: Iterable[tuple[str, Sequence[str]]],
    overrides: Mapping[str, tuple[str, str]],
) -> ArtistIndex:
    """Build the artist index from ``(track_id, Artist tag values)`` pairs.

    ``overrides`` maps a normalized credit to ``(credit text, mode)``. Artists are sorted by
    name, case-insensitively; each name is spelled as its most frequent observation (see
    ``choose_spelling``).
    """
    rows = [(str(track_id), tuple(values)) for track_id, values in tracks]
    one_names = tuple(text for text, mode in overrides.values() if mode == MODE_ONE_ARTIST)
    split_keys = frozenset(key for key, (_text, mode) in overrides.items() if mode == MODE_SPLIT)
    solo = solo_artist_keys(values for _track_id, values in rows)
    spellings: dict[str, list[str]] = defaultdict(list)
    origins: dict[str, dict[str, None]] = defaultdict(dict)
    tracks_of: dict[str, list[str]] = defaultdict(list)
    artists_by_track: dict[str, tuple[str, ...]] = {}
    for track_id, values in rows:
        keys: dict[str, None] = {}
        for value in values:
            for part in split_credit_parts(
                value, solo=solo, one_names=one_names, split_keys=split_keys
            ):
                key = normalize_key(part.name)
                spellings[key].append(part.name)
                origins[key].setdefault(part.origin)
                keys.setdefault(key)
        if keys:
            artists_by_track[track_id] = tuple(keys)
            for key in keys:
                tracks_of[key].append(track_id)
    artists = sorted(
        (
            ArtistEntry(
                key=key,
                name=choose_spelling(names),
                track_count=len(tracks_of[key]),
                origins=tuple(origins[key]),
            )
            for key, names in spellings.items()
        ),
        key=lambda entry: (entry.name.casefold(), entry.key),
    )
    return ArtistIndex(
        artists=tuple(artists),
        tracks_by_artist={key: tuple(ids) for key, ids in tracks_of.items()},
        artists_by_track=artists_by_track,
        solo_keys=solo,
        entries={artist.key: artist for artist in artists},
    )

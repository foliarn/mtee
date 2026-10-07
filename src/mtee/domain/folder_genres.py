"""Genres read from the folders of a library, and the artists they apply to.

A track sitting in ``hard techno/`` gives the genre ``Hard Techno`` to its artists. A
remix, bootleg, flip, edit or rework gives it to the remixer only, because the folder
says what the remix is, not what the original was. When the remixer cannot be found
among the credits the track gives nothing: nothing is guessed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from mtee.domain.artists import clean_name

__all__ = [
    "IGNORED_FOLDERS",
    "Credit",
    "TrackTargets",
    "folder_genres",
    "format_genre",
    "marker_names",
    "match_remixers",
    "track_targets",
]

# Folders that are not genres: leftovers, mixes, one folder per artist.
IGNORED_FOLDERS = frozenset({"zzz", "artists", "foliarn", "dj blc"})

_GENRE_NAMES = {"d&b": "Drum & Bass"}
_ACRONYMS = {"ukg": "UKG", "dj": "DJ"}
_INITIAL = re.compile(r"(?<![\w'\u2019])\w")
_ACRONYM = re.compile(rf"\b(?:{'|'.join(_ACRONYMS)})\b", re.IGNORECASE)

_KINDS = r"remix|flip|bootleg|edit|rework|refix|mashup|vip(?:\s+mix)?"
_SEGMENT = re.compile(r"[(\[]([^()\[\]]+)[)\]]")
_MARKER = re.compile(rf"^(?P<who>.*?)\s*\b(?:{_KINDS})(?:\s*\d+)?$", re.IGNORECASE)
_GENERIC = frozenset(
    {
        "original",
        "club",
        "radio",
        "extended",
        "dub",
        "instrumental",
        "vocal",
        "acoustic",
        "remastered",
        "official",
        "short",
        "long",
        "mix",
        "vip",
        "new",
        "the",
        "a",
        "my",
    }
)
_KIND_WORDS = frozenset({"remix", "flip", "bootleg", "edit", "rework", "refix", "mashup"})
_CONNECTORS = frozenset({"x", "&", "vs", "vs.", "and", "+", "-", "\u2013"})
# A marker made of style words only (``Jungle VIP``, ``DJ Edit``, ``Drum and Bass Remix``)
# names a style, not a remixer: the original artist keeps the track.
_STYLE_WORDS = frozenset(
    {
        "dj",
        "jungle",
        "dnb",
        "drum",
        "bass",
        "and",
        "hard",
        "techno",
        "house",
        "garage",
        "ukg",
        "dubstep",
        "grime",
        "breaks",
        "trance",
        "bassline",
        "uk",
        "speed",
        "2step",
    }
)
_TOKEN = re.compile(r"[^\W_]+")
_TRAILING_NOTE = re.compile(r"\s*\([^)]*\)\s*$")


def format_genre(folder: str) -> str:
    """Return the chip of a folder: its name with capitals (``hard techno`` -> ``Hard Techno``)."""
    name = clean_name(folder)
    known = _GENRE_NAMES.get(name.casefold())
    if known:
        return known
    text = _INITIAL.sub(lambda found: found.group().upper(), name)
    return _ACRONYM.sub(lambda found: _ACRONYMS[found.group().casefold()], text)


def folder_genres(
    relative_path: str, ignored: Iterable[str] = IGNORED_FOLDERS, depth: int = 2
) -> list[str]:
    """Return the genres of a file from its folders: the first ``depth`` levels, in order.

    A file directly in the root, or in an ignored top folder, gives no genre.
    """
    folders = [part for part in relative_path.replace("\\", "/").split("/")[:-1] if part.strip()]
    skipped = {clean_name(name).casefold() for name in ignored}
    if not folders or clean_name(folders[0]).casefold() in skipped:
        return []
    genres: list[str] = []
    for folder in folders[:depth]:
        genre = format_genre(folder)
        if genre and genre not in genres:
            genres.append(genre)
    return genres


def marker_names(title: str) -> list[str]:
    """Return who a title credits for a remix: ``(Gray Remix)`` gives ``Gray``.

    A marker without a name (``(VIP)``, ``(Extended Mix)``) or with a style only
    (``(Jungle VIP)``) names nobody.
    """
    names: list[str] = []
    for found in _SEGMENT.finditer(title):
        marker = _MARKER.match(clean_name(found.group(1)))
        if marker is None:
            continue
        words = marker.group("who").split()
        while words and words[-1].casefold().strip(".,:") in (_GENERIC | _KIND_WORDS | _CONNECTORS):
            words.pop()
        who = " ".join(words).strip(" -\u2013:.,")
        if not who or all(token in _STYLE_WORDS for token in _tokens(who)):
            continue
        if who not in names:
            names.append(who)
    return names


@dataclass(frozen=True, slots=True)
class Credit:
    artist_id: str
    name: str
    role: str = "artist"


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def _find(words: list[str], used: list[bool], wanted: list[str]) -> int | None:
    if not wanted:
        return None
    for start in range(len(words) - len(wanted) + 1):
        if words[start : start + len(wanted)] == wanted and not any(
            used[start : start + len(wanted)]
        ):
            return start
    return None


def match_remixers(names: Sequence[str], credits: Sequence[Credit]) -> list[str]:
    """Return the credited artists whose name appears in ``names``, once each.

    The name has to appear as whole words (``Zero's Brace Position`` holds ``Zero``;
    ``Code Pandorum x Caster`` holds ``Code:Pandorum`` and ``Caster``). Longer names
    go first so that ``Pola & Bryson`` is not also read as ``Pola``.
    """
    by_length = sorted(credits, key=lambda credit: -len(_tokens(credit.name)))
    found: list[str] = []
    for who in names:
        words = _tokens(who)
        used = [False] * len(words)
        for credit in by_length:
            # ``Jaybee (UK)`` is credited with its country; the remix says ``Jaybee``.
            for wanted in (_tokens(credit.name), _tokens(_TRAILING_NOTE.sub("", credit.name))):
                start = _find(words, used, wanted)
                if start is not None:
                    used[start : start + len(wanted)] = [True] * len(wanted)
                    if credit.artist_id not in found:
                        found.append(credit.artist_id)
                    break
    return found


@dataclass(frozen=True, slots=True)
class TrackTargets:
    """The artists a track gives its genres to, and why."""

    artist_ids: list[str] = field(default_factory=list)
    # plain: every credited artist; remixer-credit and remix: the remixers only;
    # unresolved: a remixer is named but is not among the credits, nobody is tagged.
    status: str = "plain"
    names: list[str] = field(default_factory=list)


def track_targets(credits: Sequence[Credit], titles: Iterable[str]) -> TrackTargets:
    """Decide who a track's genres go to, from its credits and every title it has."""
    remixers = [credit for credit in credits if credit.role == "remixer"]
    if remixers:
        return TrackTargets(_unique(credit.artist_id for credit in remixers), "remixer-credit")
    names: list[str] = []
    for title in titles:
        for name in marker_names(title):
            if name not in names:
                names.append(name)
    if not names:
        return TrackTargets(_unique(credit.artist_id for credit in credits), "plain")
    matched = match_remixers(names, credits)
    if matched:
        return TrackTargets(matched, "remix", names)
    return TrackTargets([], "unresolved", names)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))

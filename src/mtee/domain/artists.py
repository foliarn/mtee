"""Artist credits: normalized names, proposals read from tags and file names.

A credit is split only on a comma and on ``&``. ``x``, ``feat.`` and ``ft.`` never
become separators, and two names are merged only when they differ by case or by the
spacing, never by resemblance. The proposals are heuristics, not a measure of
confidence: they are reviewed and confirmed by the user before anything is written.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = [
    "CATEGORIES",
    "RULES_VERSION",
    "CreditEntry",
    "Proposal",
    "build_stem",
    "choose_spelling",
    "clean_name",
    "dedupe_names",
    "extract_remixers",
    "is_usable_title",
    "normalize_key",
    "propose",
    "safe_file_name",
    "split_credit",
    "split_file_stem",
]

RULES_VERSION = 1

CATEGORY_FROM_TAGS = "from_tags"
CATEGORY_SUGGESTED = "suggested"
CATEGORY_NEEDS_INPUT = "needs_input"
CATEGORIES: tuple[str, ...] = (CATEGORY_FROM_TAGS, CATEGORY_SUGGESTED, CATEGORY_NEEDS_INPUT)

ROLE_ARTIST = "artist"
ROLE_REMIXER = "remixer"

_SEPARATORS = re.compile(r"\s*(?:,|&)\s*")
_SPACES = re.compile(r"\s+")
_VERSION = re.compile(
    r"[(\[]\s*(?P<who>[^()\[\]]*?)\s+(?P<kind>remix|flip|bootleg)\s*[)\]]", re.IGNORECASE
)
_GENERIC_VERSIONS = frozenset(
    {
        "original",
        "club",
        "radio",
        "extended",
        "vip",
        "dub",
        "instrumental",
        "vocal",
        "acoustic",
        "remastered",
        "edit",
        "official",
        "short",
        "long",
        "mix",
        "the",
        "a",
        "my",
    }
)
_NUMERIC_PREFIX = re.compile(r"\W*\d+\W*")
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_INVALID_WITH_DASH = str.maketrans({"/": "-", "\\": "-", ":": "-"})
_INVALID_WITH_UNDERSCORE = str.maketrans(dict.fromkeys('<>"|?*', "_"))
_MAX_STEM_CHARACTERS = 200


@dataclass(frozen=True, slots=True)
class CreditEntry:
    """One artist of a credit, in order; ``role`` tells a remixer from a main artist."""

    name: str
    role: str = ROLE_ARTIST


@dataclass(frozen=True, slots=True)
class Proposal:
    """What the tags and the file name suggest for one track."""

    category: str
    credits: tuple[CreditEntry, ...]
    title: str
    source: str
    note: str = ""


def clean_name(name: str) -> str:
    """Return ``name`` in Unicode NFC with the spaces trimmed and collapsed."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", name)).strip()


def normalize_key(name: str) -> str:
    """Return the comparison key of a name: case and spacing are not significant.

    Accents, punctuation and signs such as ``+`` are kept.
    """
    return clean_name(name).casefold()


def split_credit(text: str) -> list[str]:
    """Split a credit on a comma and on ``&`` only; empty names are dropped."""
    names = (clean_name(part) for part in _SEPARATORS.split(text))
    return [name for name in names if name]


def dedupe_names(names: Iterable[str]) -> list[str]:
    """Keep the first spelling of each identity, in order."""
    seen: set[str] = set()
    kept: list[str] = []
    for name in names:
        cleaned = clean_name(name)
        key = normalize_key(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            kept.append(cleaned)
    return kept


def split_file_stem(stem: str) -> tuple[str, str]:
    """Split ``Artist - Title`` on the first `` - ``; no separator gives no credit."""
    index = stem.find(" - ")
    if index < 0:
        return "", clean_name(stem)
    return clean_name(stem[:index]), clean_name(stem[index + 3 :])


def extract_remixers(title: str) -> list[str]:
    """Return the artists named by ``(X Remix)``, ``(X Flip)`` or ``(X Bootleg)``."""
    names: list[str] = []
    for found in _VERSION.finditer(title):
        who = clean_name(found.group("who"))
        if not who or who.casefold() in _GENERIC_VERSIONS:
            continue
        names.extend(split_credit(who))
    return dedupe_names(names)


def is_usable_title(title: str) -> bool:
    """Return whether ``title`` can name a file: something readable must remain."""
    return any(character.isalnum() for character in title)


def _usable_prefix(prefix: str) -> bool:
    if not prefix or _NUMERIC_PREFIX.fullmatch(prefix):
        return False
    return any(character.isalnum() for character in prefix)


def propose(artist_values: Sequence[str], title_values: Sequence[str], file_stem: str) -> Proposal:
    """Build the proposal of a track from its tags and its file name."""
    tag_names = dedupe_names(name for value in artist_values for name in split_credit(str(value)))
    tag_title = clean_name(title_values[0]) if title_values else ""
    prefix, stem_title = split_file_stem(file_stem)
    prefix_usable = _usable_prefix(prefix)
    title = tag_title or stem_title
    if tag_names:
        original = tag_names
        category = CATEGORY_FROM_TAGS
        source = "tags"
        note = ""
        if prefix_usable:
            file_names = dedupe_names(split_credit(prefix))
            if {normalize_key(name) for name in file_names} != {
                normalize_key(name) for name in tag_names
            }:
                note = f"The file name says “{prefix}”."
    elif prefix_usable:
        original = dedupe_names(split_credit(prefix))
        category = CATEGORY_SUGGESTED
        source = "filename"
        note = ""
    else:
        original = []
        category = CATEGORY_NEEDS_INPUT
        source = "none"
        note = ""
    entries = [CreditEntry(name) for name in original]
    known = {normalize_key(name) for name in original}
    for remixer in extract_remixers(title):
        if normalize_key(remixer) not in known:
            known.add(normalize_key(remixer))
            entries.append(CreditEntry(remixer, ROLE_REMIXER))
    if entries and category == CATEGORY_NEEDS_INPUT:
        # Only a remixer is named: an explicit, editable suggestion.
        category = CATEGORY_SUGGESTED
        source = "title"
    return Proposal(category, tuple(entries), title, source, note)


def choose_spelling(observed: Sequence[str], current: str = "", *, locked: bool = False) -> str:
    """Pick the display spelling among the observed ones, deterministically.

    A spelling fixed by hand never changes. A short all-capitals name (``MPH``) stays in
    capitals; otherwise the most frequent spelling wins, ties keep the current spelling
    and then the first observation.
    """
    if locked and current:
        return current
    if not observed:
        return current
    counts = Counter(observed)
    for spelling in observed:
        letters = [character for character in spelling if character.isalpha()]
        if 2 <= len(letters) <= 4 and all(character.isupper() for character in letters):
            return spelling
    best = max(counts.values())
    leaders = [spelling for spelling in dict.fromkeys(observed) if counts[spelling] == best]
    if current in leaders:
        return current
    return leaders[0]


def build_stem(names: Sequence[str], title: str) -> str:
    """Return ``Artist A, Artist B - Title``."""
    return f"{', '.join(names)} - {title}"


def safe_file_name(stem: str, extension: str, *, directory_length: int = 0) -> tuple[str, bool]:
    """Return a Windows-safe file name for ``stem`` and whether it was shortened.

    The characters a Windows name cannot hold, a reserved device name, a trailing dot
    or space and an excessive length are handled here, for the file name only: the
    musical title stored in the catalog is never changed.
    """
    text = stem.translate(_INVALID_WITH_DASH).translate(_INVALID_WITH_UNDERSCORE)
    text = "".join(character for character in text if ord(character) >= 32)
    text = _SPACES.sub(" ", text).strip()
    limit = max(24, min(_MAX_STEM_CHARACTERS, 250 - len(extension), 255 - directory_length - 12))
    shortened = len(text) > limit
    if shortened:
        text = text[:limit]
    text = text.rstrip(" .")
    if text.split(".")[0].upper() in _RESERVED_NAMES:
        text = f"{text}_"
    return f"{text}{extension}", shortened

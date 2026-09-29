"""Musical keys and their Camelot or classic notations.

A key is a tonic pitch class (``C`` is 0) and a mode. The Camelot wheel numbers
the major keys ``1B``…``12B`` and their relative minors ``1A``…``12A``, with
``8B`` for C major and ``8A`` for A minor. The classic notation is compact and
uses sharps: ``C``, ``F#m``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "KEY_NOTATIONS",
    "MusicalKey",
    "format_key",
    "parse_key",
]

KEY_NOTATIONS = ("camelot", "classic")

_PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_LETTER_PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_CAMELOT = re.compile(r"^\s*(1[0-2]|0?[1-9])\s*([ABab])\s*$")
_CLASSIC = re.compile(
    r"^\s*([A-Ga-g])\s*([#b♯♭]?)\s*"
    r"(m|min|minor|mi|maj|major|ma|M)?\s*$"
)


@dataclass(frozen=True, slots=True)
class MusicalKey:
    """A major or minor key."""

    tonic: int
    minor: bool

    def __post_init__(self) -> None:
        if not 0 <= self.tonic <= 11:
            raise ValueError("tonic must be a pitch class between 0 and 11")

    @property
    def camelot(self) -> str:
        """Return the Camelot code, for example ``8B`` for C major."""
        major_tonic = (self.tonic + 3) % 12 if self.minor else self.tonic
        number = ((major_tonic * 7) % 12 + 7) % 12 + 1
        return f"{number}{'A' if self.minor else 'B'}"

    @property
    def classic(self) -> str:
        """Return the compact classic name, for example ``F#m``."""
        return _PITCH_NAMES[self.tonic] + ("m" if self.minor else "")

    def text(self, notation: str) -> str:
        """Return this key written in ``notation`` (``camelot`` or ``classic``)."""
        return self.classic if notation == "classic" else self.camelot


def parse_key(text: str) -> MusicalKey | None:
    """Return the key written as ``text`` in either notation, or ``None``.

    Accepts Camelot codes (``8A``), compact names (``Am``, ``F#m``, ``Bb``),
    flat and sharp signs, and the words ``minor``/``major``.
    """
    if not isinstance(text, str):
        return None
    camelot = _CAMELOT.match(text)
    if camelot is not None:
        number = int(camelot.group(1))
        minor = camelot.group(2).upper() == "A"
        major_tonic = ((number - 1 - 7) % 12 * 7) % 12  # inverse of the wheel numbering
        tonic = (major_tonic - 3) % 12 if minor else major_tonic
        return MusicalKey(tonic, minor)
    classic = _CLASSIC.match(text)
    if classic is None:
        return None
    letter, accidental, mode = classic.groups()
    tonic = _LETTER_PITCH[letter.upper()]
    if accidental in {"#", "♯"}:
        tonic += 1
    elif accidental in {"b", "♭"}:
        tonic -= 1
    # A lone lower-case "b" is the note B, not a flat; the letter regex already
    # takes "b" as the letter, and "bb" as B flat.
    minor = mode in {"m", "min", "minor", "mi"}
    return MusicalKey(tonic % 12, minor)


def format_key(text: str, notation: str) -> str:
    """Return ``text`` written in ``notation`` when it is a known key.

    An empty value stays empty and a value that is not a key is shown unchanged,
    so a tag written by another tool is never hidden.
    """
    if not text:
        return ""
    key = parse_key(text)
    return key.text(notation) if key is not None else text

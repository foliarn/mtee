"""Tag values that could not be written because the file stores the field ambiguously.

A FLAC or Ogg file can hold the same field under several names (``KEY`` and
``INITIALKEY``). MTEE never guesses which one to update, so the calculated value is
kept aside as a conflict until the user chooses to replace the old values.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FIELD_LABELS", "TagConflict", "TagConflictEntry"]

FIELD_LABELS = {"bpm": "BPM", "key": "Key"}


@dataclass(frozen=True, slots=True)
class TagConflictEntry:
    """One field: the tag names that hold it now, and the value waiting to be written."""

    field: str
    aliases: tuple[str, ...]
    value: str

    @property
    def label(self) -> str:
        return FIELD_LABELS.get(self.field, self.field.replace("_", " ").title())

    @property
    def summary(self) -> str:
        return f"{self.label}: {', '.join(self.aliases)} → {self.value}"


@dataclass(frozen=True, slots=True)
class TagConflict:
    """A track whose calculated values wait for the user's choice to replace its tags."""

    track_id: str
    file_name: str
    entries: tuple[TagConflictEntry, ...]

    @property
    def summary(self) -> str:
        return "\n".join(entry.summary for entry in self.entries)

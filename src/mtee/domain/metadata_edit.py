"""Explicit metadata patches and outcomes for verified source edits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision

__all__ = [
    "EDITABLE_METADATA_FIELDS",
    "MetadataEditResult",
    "MetadataFieldCapability",
    "MetadataPatch",
    "serialize_artists",
]

EDITABLE_METADATA_FIELDS: tuple[str, ...] = (
    "title",
    "artist",
    "album",
    "genre",
    "date",
    "comment",
    "track_number",
    "bpm",
    "key",
)


def serialize_artists(names: Sequence[str]) -> str:
    """Return the credit as one tag value: the names in order, joined by ``", "``.

    Every supported container stores the credit as this single value, so reading it back
    and splitting on a comma or ``&`` gives the same names in the same order. The
    identities themselves (UUID and order) stay in the catalog database.
    """
    return ", ".join(name for name in names if name)


@dataclass(frozen=True, slots=True)
class MetadataPatch:
    """Values changed in one editing action; ``None`` means explicit removal."""

    changes: tuple[tuple[str, str | None], ...]
    # Some containers can hold one field under several tag names (``KEY`` and
    # ``INITIALKEY``). By default such a field is left alone; with this flag the
    # write deletes every old name and value of the field and stores the new one.
    replace_aliases: bool = False
    fields: ClassVar[tuple[str, ...]] = EDITABLE_METADATA_FIELDS

    def __post_init__(self) -> None:
        keys = [key for key, _value in self.changes]
        if not keys:
            raise ValueError("A metadata patch must change at least one field.")
        if len(keys) != len(set(keys)):
            raise ValueError("A metadata patch cannot change one field more than once.")
        invalid = set(keys) - set(self.fields)
        if invalid:
            raise ValueError(f"Unsupported metadata fields: {', '.join(sorted(invalid))}")
        for key, value in self.changes:
            if value is not None and (not isinstance(value, str) or "\x00" in value):
                raise ValueError(f"Invalid value for metadata field {key}.")

    @classmethod
    def one(cls, field: str, value: str | None, *, replace_aliases: bool = False) -> MetadataPatch:
        return cls(((field, value),), replace_aliases)

    @classmethod
    def from_credit(
        cls, artists: Sequence[str] | None, title: str | None = None, *, write_title: bool = True
    ) -> MetadataPatch:
        """Write an ordered artist credit, and its title, replacing any previous values.

        ``artists`` of ``None`` or empty removes the artist tag. The credit is stored with
        ``serialize_artists``; ``replace_aliases`` lets the writer replace an artist field
        that a file holds as several values or names, which a plain edit refuses to touch.
        """
        changes: dict[str, str | None] = {"artist": serialize_artists(artists) if artists else None}
        if write_title and title is not None:
            changes["title"] = title
        return cls(tuple(changes.items()), True)

    @classmethod
    def from_mapping(
        cls, changes: dict[str, str | None], *, replace_aliases: bool = False
    ) -> MetadataPatch:
        return cls(tuple(changes.items()), replace_aliases)

    def as_dict(self) -> dict[str, str | None]:
        return dict(self.changes)


@dataclass(frozen=True, slots=True)
class MetadataFieldCapability:
    """Whether one field can be edited for the currently selected sources."""

    field: str
    label: str
    editable: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class MetadataEditResult:
    """Per-track result from a save or undo operation."""

    track_id: str
    status: str
    message: str = ""
    operation_id: str = ""
    revision: SourceRevision | None = None
    snapshot: MetadataSnapshot | None = None
    before: tuple[tuple[str, str | None], ...] = ()
    after: tuple[tuple[str, str | None], ...] = ()

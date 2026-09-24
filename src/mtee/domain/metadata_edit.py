"""Explicit metadata patches and outcomes for verified source edits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision

__all__ = [
    "EDITABLE_METADATA_FIELDS",
    "MetadataEditResult",
    "MetadataFieldCapability",
    "MetadataPatch",
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


@dataclass(frozen=True, slots=True)
class MetadataPatch:
    """Values changed in one editing action; ``None`` means explicit removal."""

    changes: tuple[tuple[str, str | None], ...]
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
    def one(cls, field: str, value: str | None) -> MetadataPatch:
        return cls(((field, value),))

    @classmethod
    def from_mapping(cls, changes: dict[str, str | None]) -> MetadataPatch:
        return cls(tuple(changes.items()))

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

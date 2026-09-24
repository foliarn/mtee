"""Immutable source metadata read from an audio file.

Tag values remain tuples so repeated values in source files are not discarded.
Calculated analysis and future manual corrections belong to separate records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

__all__ = ["MetadataSnapshot", "TechnicalInfo"]


@dataclass(frozen=True, slots=True)
class TechnicalInfo:
    duration_us: int | None = None
    container: str = ""
    codec: str = ""
    bitrate: int | None = None
    sample_rate: int | None = None
    bits_per_sample: int | None = None
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MetadataSnapshot:
    title: tuple[str, ...] = ()
    artist: tuple[str, ...] = ()
    album: tuple[str, ...] = ()
    genre: tuple[str, ...] = ()
    date: tuple[str, ...] = ()
    bpm: tuple[str, ...] = ()
    key: tuple[str, ...] = ()
    track_number: tuple[str, ...] = ()
    comment: tuple[str, ...] = ()
    technical: TechnicalInfo = TechnicalInfo()
    status: str = "readable"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["technical"] = self.technical.to_dict()
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MetadataSnapshot:
        raw = dict(value)
        technical = raw.get("technical", {})
        raw["technical"] = (
            TechnicalInfo(**technical) if isinstance(technical, dict) else TechnicalInfo()
        )
        for field in (
            "title",
            "artist",
            "album",
            "genre",
            "date",
            "bpm",
            "key",
            "track_number",
            "comment",
        ):
            item = raw.get(field, ())
            raw[field] = (
                tuple(str(part) for part in item) if isinstance(item, (tuple, list)) else ()
            )
        return cls(**raw)

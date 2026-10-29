"""Immutable source metadata read from an audio file.

Tag values remain tuples so repeated values in source files are not discarded.
Technical properties describe the source and are kept separate from its tags.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

__all__ = ["MetadataSnapshot", "TechnicalInfo", "format_bitrate", "normalize_isrc"]

_ISRC_PATTERN = re.compile(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}")


def format_bitrate(bits_per_second: int | None) -> str:
    """Format a measured bitrate for display without changing its numeric value."""
    if bits_per_second is None or bits_per_second <= 0:
        return "—"
    return f"{round(bits_per_second / 1000):d} kbps"


def normalize_isrc(value: str | None) -> str | None:
    """Return the canonical 12-character ISRC, or None when the value is not one.

    Hyphens and spaces are dropped and letters uppercased, so ``us-rc1-76-07839``
    becomes ``USRC17607839``.
    """
    if value is None:
        return None
    text = value.strip().upper().replace("-", "").replace(" ", "")
    return text if _ISRC_PATTERN.fullmatch(text) else None


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
    isrc: str | None = None
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
        # Stored JSON written before ISRC support has no key; it then reads as None.
        isrc = raw.get("isrc")
        raw["isrc"] = normalize_isrc(isrc) if isinstance(isrc, str) else None
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

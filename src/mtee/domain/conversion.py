"""Shared audio source contract, read by analysis, waveforms and decoding.

The conversion contracts (settings, requests, previews, results) live in the conversion
plugin, ``mtee.plugins.conversion.domain``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mtee.domain.tracks import SourceRevision

__all__ = ["ConversionSource"]


@dataclass(frozen=True, slots=True)
class ConversionSource:
    track_id: str
    path: Path
    revision: SourceRevision

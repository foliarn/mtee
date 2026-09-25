"""Versioned, provenance-aware audio analysis contracts."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from mtee.domain.tracks import SourceRevision

__all__ = [
    "AnalysisMetric",
    "AnalysisOverride",
    "AnalysisResult",
    "AnalysisRunSummary",
    "AnalysisSpec",
    "AnalysisStatus",
    "new_analysis_id",
]


def new_analysis_id() -> str:
    return str(uuid.uuid4())


class AnalysisStatus(StrEnum):
    AVAILABLE = "available"
    UNCERTAIN = "uncertain"
    NOT_APPLICABLE = "not_applicable"
    STALE = "stale"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AnalysisSpec:
    analyzer: str
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.analyzer not in {"technical", "silence", "loudness", "tempo", "key"}:
            raise ValueError(f"Unknown analysis method: {self.analyzer}")
        json.dumps(self.config, sort_keys=True, allow_nan=False)


@dataclass(frozen=True, slots=True)
class AnalysisMetric:
    name: str
    value: float | int | str | None
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("metric name is required")
        if isinstance(self.value, float) and (
            self.value != self.value or abs(self.value) == float("inf")
        ):
            raise ValueError("analysis metrics must be finite")


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    result_id: str
    run_id: str
    track_id: str
    analyzer: str
    analyzer_version: str
    source_revision: SourceRevision
    config: dict[str, Any]
    status: AnalysisStatus
    metrics: tuple[AnalysisMetric, ...] = ()
    segments: tuple[dict[str, Any], ...] = ()
    diagnostics: str = ""
    coverage: float | None = None
    created_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not self.result_id or not self.run_id or not self.track_id or not self.analyzer:
            raise ValueError("analysis result identity fields are required")
        if self.coverage is not None and not 0 <= self.coverage <= 1:
            raise ValueError("analysis coverage must be between zero and one")
        json.dumps(self.config, sort_keys=True, allow_nan=False)
        json.dumps(self.segments, sort_keys=True, allow_nan=False)


@dataclass(frozen=True, slots=True)
class AnalysisOverride:
    override_id: str
    track_id: str
    field_name: str
    value: float | str | None
    source_revision: SourceRevision
    created_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    active: bool = True

    def __post_init__(self) -> None:
        if not self.override_id or not self.track_id or not self.field_name:
            raise ValueError("override identity fields are required")
        json.dumps(self.value, allow_nan=False)


@dataclass(frozen=True, slots=True)
class AnalysisRunSummary:
    run_id: str
    track_id: str
    status: str
    completed: int
    total: int
    error: str = ""

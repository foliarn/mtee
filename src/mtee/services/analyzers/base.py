"""Shared analyzer interface and immutable execution context."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mtee.domain.analysis import AnalysisResult, AnalysisSpec
from mtee.domain.conversion import ConversionSource


@dataclass(frozen=True, slots=True)
class AnalyzerContext:
    run_id: str
    is_cancelled: Callable[[], bool]
    report_progress: Callable[[float], None]

    def raise_if_cancelled(self) -> None:
        from mtee.domain.jobs import JobCancelledError

        if self.is_cancelled():
            raise JobCancelledError("analysis cancelled")


class Analyzer(Protocol):
    name: str
    version: str

    def analyze(
        self, source: ConversionSource, spec: AnalysisSpec, context: AnalyzerContext
    ) -> AnalysisResult: ...

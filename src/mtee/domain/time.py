"""Internal time representation.

Internal times are integers in microseconds. ``TimeRange`` excludes its end
bound; the conversion to sample indices uses an explicit rounding rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

__all__ = ["MICROSECONDS_PER_SECOND", "TimeRange"]

MICROSECONDS_PER_SECOND = 1_000_000


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Half-open range ``[start_us, end_us)`` expressed in microseconds."""

    start_us: int
    end_us: int

    def __post_init__(self) -> None:
        if not isinstance(self.start_us, int) or not isinstance(self.end_us, int):
            raise TypeError("TimeRange bounds must be integers of microseconds")
        if self.start_us < 0:
            raise ValueError("start_us must not be negative")
        if self.end_us <= self.start_us:
            raise ValueError("end_us must be greater than start_us")

    @staticmethod
    def from_seconds(start_seconds: float, end_seconds: float) -> TimeRange:
        """Return the range of the given seconds, rounded to the nearest microsecond."""
        return TimeRange(
            round(start_seconds * MICROSECONDS_PER_SECOND),
            round(end_seconds * MICROSECONDS_PER_SECOND),
        )

    @property
    def duration_us(self) -> int:
        """Return the duration covered by the range."""
        return self.end_us - self.start_us

    def contains(self, position_us: int) -> bool:
        """Return whether ``position_us`` belongs to the range, end excluded."""
        return self.start_us <= position_us < self.end_us

    def overlaps(self, other: TimeRange) -> bool:
        """Return whether the two half-open ranges share at least one microsecond."""
        return self.start_us < other.end_us and other.start_us < self.end_us

    def to_sample_range(self, sample_rate_hz: int) -> tuple[int, int]:
        """Return the half-open sample indices covering the range.

        The start is rounded down and the end is rounded up, so the samples
        returned always cover the whole range. The end index is kept strictly
        greater than the start index, even for a range shorter than one sample.
        """
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        start_index = floor(self.start_us * sample_rate_hz / MICROSECONDS_PER_SECOND)
        end_index = ceil(self.end_us * sample_rate_hz / MICROSECONDS_PER_SECOND)
        return start_index, max(end_index, start_index + 1)

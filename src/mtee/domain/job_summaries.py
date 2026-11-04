"""One sentence per finished job, written from the counts the job reports.

A job hands ``JobService.submit`` a ``SummaryFn``. The service calls it once, on the
graphical thread, when the job reaches a terminal state. When the job has no summary, when
the function raises, or when it returns nothing, the sentence is ``fallback_summary``.

Pure functions only: no Qt, so the sentences can be tested from a plain ``JobStatus``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from mtee.domain.jobs import JobState, JobStatus

__all__ = [
    "SummaryFn",
    "analysis_summary",
    "copied_summary",
    "count_sentence",
    "counted",
    "errors_text",
    "fallback_summary",
    "fixed",
    "job_summary",
    "moved_summary",
    "plural",
    "recorded",
    "recycled_summary",
    "saved_summary",
    "scan_summary",
]

logger = logging.getLogger(__name__)

SummaryFn = Callable[[JobStatus], str]
_MAX_SENTENCE = 160


def plural(count: int, one: str, many: str) -> str:
    """Return ``count`` and the noun in its singular or plural form: ``1 song``, ``2 songs``."""
    return f"{count} {one if count == 1 else many}"


def errors_text(count: int) -> str:
    """Return ``0 errors``, ``1 error``, ``3 errors``."""
    return plural(count, "error", "errors")


def _first_sentence(text: str) -> str:
    lines = text.strip().splitlines()
    first = lines[0].strip() if lines else ""
    return first[:_MAX_SENTENCE]


def fallback_summary(status: JobStatus) -> str:
    """Return the generic sentence: ``<label>: done``, ``<label>: 3 of 120 failed``, etc."""
    label = status.label or "Background task"
    if status.state is JobState.CANCELLED:
        return f"{label}: cancelled"
    if status.is_interrupted:
        return f"{label}: stopped before completion"
    failed = max(status.failure_total, len(status.failures))
    if failed:
        if status.total:
            return f"{label}: {failed} of {status.total} failed"
        return f"{label}: {failed} failed"
    if status.state is JobState.FAILED:
        message = _first_sentence(status.error.message) if status.error else ""
        return f"{label}: failed ({message})" if message else f"{label}: failed"
    return f"{label}: done"


def job_summary(status: JobStatus, summary: SummaryFn | None) -> str:
    """Return the sentence of a terminal ``status``, from ``summary`` or the fallback."""
    if summary is None:
        return fallback_summary(status)
    try:
        text = summary(status)
    except Exception:
        logger.exception(
            "The summary of job %s failed; the generic sentence is used.", status.job_id
        )
        return fallback_summary(status)
    cleaned = " ".join(str(text or "").split())
    return cleaned[:_MAX_SENTENCE] or fallback_summary(status)


def counted(done: Callable[[int | None, int], str]) -> SummaryFn:
    """Build a summary from the counter and the failures of a finished job.

    ``done(completed, failures)`` writes the sentence for a success or a partial failure
    (``completed`` is ``None`` when the job did not count its elements). Cancelled and
    failed jobs keep the generic sentence.
    """

    def summary(status: JobStatus) -> str:
        if status.state is JobState.SUCCEEDED or status.is_partial:
            failures = max(status.failure_total, len(status.failures))
            return done(status.completed, failures)
        return fallback_summary(status)

    return summary


def fixed(text: str) -> SummaryFn:
    """Build a summary that is ``text`` when the job succeeded, the generic sentence otherwise."""

    def summary(status: JobStatus) -> str:
        if status.state is JobState.SUCCEEDED:
            return text
        return fallback_summary(status)

    return summary


def recorded(sentences: list[str]) -> SummaryFn:
    """Use the last sentence the job wrote into ``sentences`` while it ran, when it succeeded.

    For a job whose task already knows its one-line result (a message shown to the user).
    """

    def summary(status: JobStatus) -> str:
        if status.state is JobState.SUCCEEDED and sentences:
            return sentences[-1]
        return fallback_summary(status)

    return summary


def count_sentence(
    completed: int | None,
    failures: int,
    *,
    one: str,
    many: str,
    finished: str,
) -> str:
    """Return ``3 songs analysed, 1 error``, or ``<finished>, 1 error`` when no count is known."""
    errors = errors_text(failures)
    if completed is None:
        return f"{finished}, {errors}"
    return f"{plural(completed, one, many)}, {errors}"


def analysis_summary() -> SummaryFn:
    """Analysis of the tracks: ``123 songs analysed, 0 errors``."""
    return counted(
        lambda completed, failures: count_sentence(
            completed,
            failures,
            one="song analysed",
            many="songs analysed",
            finished="Analysis finished",
        )
    )


def scan_summary(root_name: str) -> SummaryFn:
    """Scan of a library folder: ``Music scanned: 340 files read, 0 errors``."""
    return counted(
        lambda completed, failures: (
            f"{root_name} scanned: "
            + count_sentence(
                completed,
                failures,
                one="file read",
                many="files read",
                finished="Scan finished",
            )
        )
    )


def moved_summary() -> SummaryFn:
    """Move of files into a folder: ``8 files moved, 0 errors``.

    The counter counts the files tried, so the moved files are the tried ones minus the failures.
    """

    def done(completed: int | None, failures: int) -> str:
        moved = None if completed is None else max(0, completed - failures)
        return count_sentence(
            moved, failures, one="file moved", many="files moved", finished="Move finished"
        )

    return counted(done)


def copied_summary() -> SummaryFn:
    """Copy of files into a folder: ``8 files copied, 0 errors``."""

    def done(completed: int | None, failures: int) -> str:
        copied = None if completed is None else max(0, completed - failures)
        return count_sentence(
            copied, failures, one="file copied", many="files copied", finished="Copy finished"
        )

    return counted(done)


def recycled_summary() -> SummaryFn:
    """Move of tracks to the Recycle Bin: ``3 files moved to the Recycle Bin, 0 errors``."""
    return counted(
        lambda completed, failures: count_sentence(
            completed,
            failures,
            one="file moved to the Recycle Bin",
            many="files moved to the Recycle Bin",
            finished="Recycle Bin move finished",
        )
    )


def saved_summary() -> SummaryFn:
    """Metadata saved to files: ``5 files saved, 0 errors``."""
    return counted(
        lambda completed, failures: count_sentence(
            completed,
            failures,
            one="file saved",
            many="files saved",
            finished="Metadata saved",
        )
    )

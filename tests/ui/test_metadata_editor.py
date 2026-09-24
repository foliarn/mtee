"""The editor captures its targets before work runs in the background."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.metadata_edit import (
    EDITABLE_METADATA_FIELDS,
    MetadataEditResult,
    MetadataPatch,
)
from mtee.domain.tracks import SourceRevision
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.persistence.library_repository import LibraryRepository, TrackSource
from mtee.services.jobs import JobService
from mtee.services.metadata_writer import MetadataEditService


class _Library:
    def __init__(self) -> None:
        self.sources = {
            "first": TrackSource(
                "first",
                Path("first.wav"),
                SourceRevision(100, 10, "1:1", 0),
                MetadataSnapshot(title=("First",)),
                "readable",
            ),
            "second": TrackSource(
                "second",
                Path("second.wav"),
                SourceRevision(200, 20, "1:2", 0),
                MetadataSnapshot(title=("Second",)),
                "readable",
            ),
        }

    def source_record(self, track_id: str) -> TrackSource | None:
        return self.sources.get(track_id)


class _Writer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.read_only_ids: set[str] = set()

    def capabilities(self, track_id: str) -> dict[str, tuple[bool, str]]:
        editable = track_id not in self.read_only_ids
        reason = "This format is read-only." if not editable else ""
        return {field: (editable, reason) for field in EDITABLE_METADATA_FIELDS}

    def save(
        self,
        track_id: str,
        expected: SourceRevision,
        patch: MetadataPatch,
        _draft_id: str,
    ) -> MetadataEditResult:
        value = patch.as_dict()["title"]
        self.calls.append((track_id, value))
        if track_id in self.read_only_ids:
            return MetadataEditResult(track_id, "unsupported", "This format is read-only.")
        return MetadataEditResult(
            track_id,
            "saved",
            operation_id=f"operation-{len(self.calls)}",
            revision=expected.bumped(),
        )

    def undo(self, _operation_id: str, _draft_id: str) -> MetadataEditResult:
        raise AssertionError("Undo is not part of this test.")

    def incomplete_operations(self) -> list[dict[str, object]]:
        return []


def test_field_commit_uses_the_selection_captured_on_focus(qapp) -> None:
    library = _Library()
    writer = _Writer()
    jobs = JobService(qapp, max_thread_count=1)
    selection = ["first"]
    editor = MetadataEditorModel(
        cast(LibraryRepository, library),
        cast(MetadataEditService, writer),
        jobs,
        lambda: selection,
    )

    editor.begin_field_edit("title")
    assert writer.calls == []
    selection[:] = ["second"]
    editor.commit_field("title", "Edited first")

    deadline = time.monotonic() + 5
    while jobs.active_count() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        QTest.qWait(5)
    QCoreApplication.processEvents()

    assert jobs.active_count() == 0
    assert writer.calls == [("first", "Edited first")]
    assert editor.saveState == "saved", editor.saveMessage
    jobs.shutdown()


def test_mixed_selection_saves_supported_files_and_reports_the_rest(qapp) -> None:
    library = _Library()
    writer = _Writer()
    writer.read_only_ids.add("second")
    jobs = JobService(qapp, max_thread_count=1)
    selection = ["first", "second"]
    editor = MetadataEditorModel(
        cast(LibraryRepository, library),
        cast(MetadataEditService, writer),
        jobs,
        lambda: selection,
    )

    fields = cast(list[dict[str, Any]], editor.infoFields)
    title = next(field for field in fields if field["key"] == "title")
    assert title["editable"] is True
    assert title["mixed"] is True
    editor.begin_field_edit("title")
    editor.commit_field("title", "Apply where supported")

    deadline = time.monotonic() + 5
    while jobs.active_count() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        QTest.qWait(5)
    QCoreApplication.processEvents()

    assert jobs.active_count() == 0
    assert writer.calls == [
        ("first", "Apply where supported"),
        ("second", "Apply where supported"),
    ]
    assert cast(str, editor.saveState) == "error"
    assert "Saved 1 of 2" in cast(str, editor.saveMessage)
    jobs.shutdown()

"""Tag changes are staged and written together on Save; fields never wait after a save."""

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
            name: TrackSource(
                name,
                Path(f"{name}.wav"),
                SourceRevision(100, 10, f"1:{name}", 0),
                MetadataSnapshot(title=(name.title(),), artist=(artist,)),
                "readable",
            )
            for name, artist in (("one", "Hedex, Bou"), ("two", "Bou"))
        }

    def source_record(self, track_id: str) -> TrackSource | None:
        return self.sources.get(track_id)

    def tag_values(self, _field: str) -> list[str]:
        return []


class _Writer:
    def __init__(self, library: _Library) -> None:
        self.library = library
        self.patches: list[tuple[str, dict[str, str | None]]] = []
        self.inspections = 0

    def inspect(self, track_id: str):
        self.inspections += 1
        source = self.library.sources[track_id]
        capabilities = {field: (True, "") for field in EDITABLE_METADATA_FIELDS}
        return source.revision, source.snapshot, capabilities

    def save(
        self, track_id: str, expected: SourceRevision, patch: MetadataPatch, _draft: str
    ) -> MetadataEditResult:
        self.patches.append((track_id, patch.as_dict()))
        source = self.library.sources[track_id]
        values = {
            field: (() if value is None else (value,)) for field, value in patch.as_dict().items()
        }
        snapshot = MetadataSnapshot(
            title=values.get("title", source.snapshot.title),
            artist=values.get("artist", source.snapshot.artist),
            date=values.get("date", source.snapshot.date),
        )
        revision = expected.bumped()
        self.library.sources[track_id] = TrackSource(
            track_id, source.path, revision, snapshot, "readable"
        )
        return MetadataEditResult(
            track_id,
            "saved",
            operation_id=f"op-{len(self.patches)}",
            revision=revision,
            snapshot=snapshot,
        )

    def undo(self, *_args: Any) -> MetadataEditResult:
        raise AssertionError("not used")

    def incomplete_operations(self) -> list[dict[str, object]]:
        return []


class _CreditRules:
    """Credit rules that cut at commas only; records the One/Several answers."""

    def __init__(self) -> None:
        self.choices: list[tuple[str, bool]] = []

    def split(self, text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()]

    def needs_choice(self, text: str) -> bool:
        return "," in text

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        return [{"id": "x", "name": "Hedex", "established": True}][:limit] if query else []

    def record_credit_choice(self, text: str, *, one_artist: bool) -> None:
        self.choices.append((text, one_artist))


def _make(qapp, selection: list[str]):
    library = _Library()
    writer = _Writer(library)
    rules = _CreditRules()
    jobs = JobService(qapp, max_thread_count=1)
    editor = MetadataEditorModel(
        cast(LibraryRepository, library),
        cast(MetadataEditService, writer),
        jobs,
        lambda: selection,
        artist_rules=rules,
    )
    editor.prepareTrackInspection()
    _wait(jobs, editor)
    return library, writer, rules, jobs, editor


def _wait(jobs: JobService, editor: MetadataEditorModel) -> None:
    deadline = time.monotonic() + 5
    while jobs.active_count() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        QTest.qWait(5)
    QCoreApplication.processEvents()
    QTest.qWait(20)
    QCoreApplication.processEvents()


def _fields(editor: MetadataEditorModel) -> dict[str, dict[str, Any]]:
    return {field["key"]: field for field in cast(list[dict[str, Any]], editor.infoFields)}


def test_nothing_is_written_until_save_then_one_patch_per_track(qapp) -> None:
    _library, writer, _artists, jobs, editor = _make(qapp, ["one"])
    editor.stageField("title", "Renamed")
    editor.stageField("date", "2024/3/5")
    assert writer.patches == []
    assert editor.changeCount == 2 and editor.canSave
    assert _fields(editor)["date"]["dirty"] is True

    editor.saveChanges()
    _wait(jobs, editor)
    assert writer.patches == [("one", {"title": "Renamed", "date": "2024-03-05"})]
    assert editor.saveState == "saved"
    assert editor.changeCount == 0

    # The fields stay editable: the new revision does not start another inspection.
    assert all(field["editable"] for field in _fields(editor).values())
    assert _fields(editor)["title"]["value"] == "Renamed"
    jobs.shutdown()


def test_invalid_values_block_save_and_revert_restores_them(qapp) -> None:
    _library, writer, _artists, jobs, editor = _make(qapp, ["one"])
    editor.stageField("date", "March")
    assert editor.canSave is False
    assert "date" in cast(dict, editor.fieldErrors)
    editor.saveChanges()
    assert writer.patches == []
    editor.revertField("date")
    assert editor.changeCount == 0
    editor.stageField("title", "One")  # same as the shown value: no change
    assert editor.changeCount == 0
    jobs.shutdown()


def test_artist_chips_are_staged_and_saved_as_tags_only(qapp) -> None:
    _library, writer, rules, jobs, editor = _make(qapp, ["one"])
    assert [chip["name"] for chip in cast(list, editor.artistChips)] == ["Hedex", "Bou"]
    editor.stageArtistRemove("Hedex")
    editor.stageArtistAdd("Nikita, the Wicked")
    assert [chip["name"] for chip in cast(list, editor.artistChips)] == [
        "Bou",
        "Nikita, the Wicked",
    ]
    editor.saveChanges()
    _wait(jobs, editor)
    assert writer.patches == [("one", {"artist": "Bou, Nikita, the Wicked"})]
    # Saving writes tags only: the credit rules never hear about the saved credit.
    assert rules.choices == []
    jobs.shutdown()


def test_artist_changes_apply_to_every_selected_track(qapp) -> None:
    _library, writer, _rules, jobs, editor = _make(qapp, ["one", "two"])
    chips = {chip["name"]: chip for chip in cast(list, editor.artistChips)}
    assert chips["Bou"]["count"] == 2 and chips["Hedex"]["count"] == 1
    editor.stageArtistAdd("Hedex")  # one track already has it
    editor.saveChanges()
    _wait(jobs, editor)
    assert dict(writer.patches) == {
        "one": {"artist": "Hedex, Bou"},
        "two": {"artist": "Bou, Hedex"},
    }
    jobs.shutdown()


def test_one_artist_or_several_answer_reaches_the_credit_rules(qapp) -> None:
    _library, _writer, rules, jobs, editor = _make(qapp, ["one"])
    editor.recordCreditChoice("  Nikita,  the Wicked ", True)
    editor.recordCreditChoice("Bou & Hedex", False)
    editor.recordCreditChoice("   ", True)
    assert rules.choices == [("Nikita, the Wicked", True), ("Bou & Hedex", False)]
    jobs.shutdown()


def test_default_credit_rules_split_as_typed_and_keep_nothing(qapp) -> None:
    library = _Library()
    writer = _Writer(library)
    jobs = JobService(qapp, max_thread_count=1)
    editor = MetadataEditorModel(
        cast(LibraryRepository, library),
        cast(MetadataEditService, writer),
        jobs,
        lambda: ["one"],
    )
    # Without an index, a comma always splits, an ampersand between two names does not, and a
    # comma or an ampersand asks "One artist or several?" until the user answers.
    assert editor.splitPreview("Nikita, the Wicked") == ["Nikita", "the Wicked"]
    assert editor.splitPreview("Bou & Hedex") == ["Bou & Hedex"]
    assert editor.creditNeedsChoice("Nikita, the Wicked") is True
    assert editor.creditNeedsChoice("Bou & Hedex") is True
    assert editor.creditNeedsChoice("Bou") is False
    assert editor.artistSuggestions("Hed") == []
    editor.recordCreditChoice("Nikita, the Wicked", True)
    jobs.shutdown()


def test_unsaved_changes_are_kept_per_selection(qapp) -> None:
    selection = ["one"]
    library = _Library()
    writer = _Writer(library)
    jobs = JobService(qapp, max_thread_count=1)
    editor = MetadataEditorModel(
        cast(LibraryRepository, library),
        cast(MetadataEditService, writer),
        jobs,
        lambda: selection,
    )
    notices: list[str] = []
    editor.noticeRaised.connect(notices.append)
    editor.refresh_selection()
    editor.stageField("genre", "Rollers")
    selection[:] = ["two"]
    editor.refresh_selection()
    assert editor.changeCount == 0 and notices
    selection[:] = ["one"]
    editor.refresh_selection()
    assert editor.dirtyFields == ["genre"]
    jobs.shutdown()

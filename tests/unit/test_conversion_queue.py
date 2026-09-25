from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QUrl

from mtee.models.conversion_queue_model import ConversionQueueModel
from mtee.persistence.database import Database
from mtee.persistence.derivations_repository import DerivationsRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.conversion_service import ConversionService
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.jobs import JobService


def test_queue_accepts_files_reviews_an_output_and_starts_on_explicit_second_action(
    qapp, tmp_path: Path
) -> None:
    repository = Path(__file__).resolve().parents[2]
    fixture = repository / ".local" / "fixtures" / "07-metadata" / "audio" / "wav.wav"
    if not fixture.is_file():
        return
    database = Database(tmp_path / "queue.sqlite3")
    database.migrate()
    jobs = JobService(qapp, max_thread_count=2)
    model = ConversionQueueModel(
        LibraryRepository(database),
        jobs,
        ConversionService(),
        FileAccessCoordinator(),
        DerivationsRepository(database),
    )
    output = tmp_path / "outputs"
    output.mkdir()
    model.add_files([QUrl.fromLocalFile(str(fixture))])
    model.set_output_folder(QUrl.fromLocalFile(str(output)).toString())

    inputs = cast(list[dict[str, Any]], model.inputs)
    assert len(inputs) == 1
    assert model.outputFolder == str(output)
    model.preview_or_start()
    assert model.hasPreview
    assert model.previewExecutable
    assert "Preview: 1 ready" in cast(str, model.previewSummary)

    model.preview_or_start()
    assert jobs.wait_for_done(30_000)
    assert cast(list[dict[str, Any]], model.inputs)[0]["status"] == "completed"
    assert (output / "wav.mp3").is_file()
    assert DerivationsRepository(database).attempts()[0]["status"] == "completed"
    jobs.shutdown()
    database.close()


def test_advanced_settings_cycle_only_available_output_values(qapp, tmp_path: Path) -> None:
    database = Database(tmp_path / "options.sqlite3")
    database.migrate()
    jobs = JobService(qapp, max_thread_count=1)
    model = ConversionQueueModel(
        LibraryRepository(database),
        jobs,
        ConversionService(),
        FileAccessCoordinator(),
        DerivationsRepository(database),
    )

    formats = cast(list[dict[str, str]], model.formats)
    assert formats[cast(int, model.formatIndex)]["id"] == "mp3"
    model.next_format()
    formats = cast(list[dict[str, str]], model.formats)
    assert formats[cast(int, model.formatIndex)]["id"] == "flac"
    assert cast(list[str], model.bitDepthOptions) == ["Keep source", "16-bit", "24-bit"]
    model.next_bit_depth()
    model.next_sample_rate()
    assert cast(str, model.bitDepth) == "16-bit"
    assert cast(str, model.sampleRate) == "22.05 kHz"
    jobs.shutdown()
    database.close()

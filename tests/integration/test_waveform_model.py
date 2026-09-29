"""The playing track's waveform: computed once, stored, then read back without decoding."""

from __future__ import annotations

import struct
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from tests.helpers.analysis_audio import drum_loop, write_wav

from mtee.domain.tracks import SourceRevision
from mtee.models.waveform_model import WaveformModel
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.jobs import JobService
from mtee.services.metadata_reader import MetadataReader


class _Player(QObject):
    """The part of the player the waveform model listens to."""

    stateChanged = Signal()  # noqa: N815 - the name the waveform model connects to

    def __init__(self) -> None:
        super().__init__()
        self.state = SimpleNamespace(current_id="", duration_us=0)
        self.seeks: list[int] = []

    def play(self, track_id: str) -> None:
        self.state = SimpleNamespace(current_id=track_id, duration_us=0)
        self.stateChanged.emit()

    def seek(self, position_us: int) -> None:
        self.seeks.append(position_us)


def _wait(predicate, seconds: float = 20.0) -> None:
    """Pump events without holding the interpreter lock, so worker threads can run."""
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_the_waveform_is_computed_once_then_read_from_the_database(qapp, tmp_path: Path) -> None:
    try:
        FfmpegRuntime().executable("ffmpeg")
    except FfmpegRuntimeError:
        pytest.skip("The bundled FFmpeg runtime is unavailable.")
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root = library.add_root(tmp_path / "music")
    generation = library.begin_scan(root["id"])
    ids = []
    for index, bpm in enumerate((120.0, 128.0)):
        path = tmp_path / "music" / f"track{index}.wav"
        write_wav(path, drum_loop(bpm, 20, rate=44_100), 44_100)
        library.upsert_locations(
            root["id"],
            [(path.name, path, SourceRevision.observe(path), MetadataReader().read(path))],
            generation,
        )
        ids.append(library.path_owner(path))
    jobs = JobService(qapp, max_thread_count=2)
    player = _Player()
    model = WaveformModel(
        player,  # type: ignore[arg-type]
        library,
        jobs,
        FileAccessCoordinator(),
        AnalysisRepository(database),
    )
    try:
        registered = lambda: len(jobs._statuses)  # type: ignore[attr-defined]  # noqa: E731
        before = registered()
        player.play(ids[0])
        assert model.state == "generating"
        _wait(lambda: model.state == "ready")
        assert registered() == before + 1  # the first play decodes the file once
        assert model.durationUs == pytest.approx(20_000_000, abs=100_000)
        packed = bytes(model.samples.data())
        assert len(packed) == 1000 * 2 * 4  # one (low, high) float32 pair per 20 ms bin
        values = struct.unpack(f"<{len(packed) // 4}f", packed)
        assert min(values) < -0.3 and max(values) > 0.3
        assert all(-1.0 <= value <= 1.0 for value in values)

        player.play(ids[1])
        _wait(lambda: model.state == "ready" and model.durationUs > 0)
        jobs.wait_for_done(5_000)

        # Back to the first track: no job, no decoding, the stored waveform at once.
        submitted = registered()
        player.play(ids[0])
        assert model.state == "ready"
        assert bytes(model.samples.data()) == packed
        assert registered() == submitted

        model.seekRatio(0.5)
        assert player.seeks == [round(0.5 * model.durationUs)]
    finally:
        jobs.begin_shutdown()
        jobs.wait_for_done(5_000)
        database.close()

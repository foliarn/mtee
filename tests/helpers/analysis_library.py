"""A scanned library of synthetic tracks with the analysis and tag services around it."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.domain.tracks import SourceRevision
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.services.analysis_service import AnalysisService
from mtee.services.audio_analyzer import AudioAnalyzer
from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.metadata_reader import MetadataReader
from mtee.services.metadata_writer import MetadataEditService
from tests.helpers.analysis_audio import drum_loop, key_progression, write_wav

RATE = 44_100


def require_ffmpeg() -> None:
    try:
        FfmpegRuntime().executable("ffmpeg")
    except FfmpegRuntimeError:
        pytest.skip("The bundled FFmpeg runtime is unavailable.")


class AnalysisLibrary:
    """A scanned library holding synthetic tracks, with the services around it."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.repository = AnalysisRepository(self.database)
        self.access = FileAccessCoordinator()
        self.analyzer = AudioAnalyzer(MediaDecodeService(self.access), self.access)
        self.writer = MetadataEditService(
            self.library, MetadataHistoryRepository(self.database), self.access
        )
        self.root_id = self.library.add_root(base / "music")["id"]

    def add_track(self, relative: str, bpm: float, tonic: int, minor: bool, seconds: int) -> str:
        path = self.base / "music" / relative
        signal = 0.5 * key_progression(tonic, minor, seconds, rate=RATE)
        signal = signal + 0.6 * drum_loop(bpm, seconds, rate=RATE)
        write_wav(path, signal, RATE)
        return self.register(relative)

    def register(self, relative: str) -> str:
        """Catalog the file ``music/<relative>`` (already on disk) and return its track id."""
        path = self.base / "music" / relative
        generation = self.library.begin_scan(self.root_id)
        snapshot = MetadataReader().read(path)
        self.library.upsert_locations(
            self.root_id,
            [(relative, path, SourceRevision.observe(path), snapshot)],
            generation,
        )
        owner = self.library.path_owner(path)
        assert owner is not None
        return owner

    def service(self, *, write_tags: bool = False) -> AnalysisService:
        return AnalysisService(
            self.library,
            self.repository,
            self.analyzer,
            self.writer if write_tags else None,
        )

    def close(self) -> None:
        self.database.close()

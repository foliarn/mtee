"""Create an isolated six-track playlist review library in a fresh data directory."""

from __future__ import annotations

import argparse
import math
import struct
import wave
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.services.playlist_service import PlaylistService

TRACKS = (
    ("Afterlight", "Northline"),
    ("Control (Original Mix)", "Second Signal"),
    ("Low Orbit", "Velar"),
    ("Wired", "Second Signal"),
    ("A Very Long Track Title That Must Stay Readable in a Narrow Panel", "The Night Array"),
    ("Homebound", "Northline"),
)


def write_wave(path: Path, frequency: float) -> None:
    rate = 16_000
    seconds = 18
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        for start in range(0, seconds * rate, rate):
            samples = (
                int(1800 * math.sin(2 * math.pi * frequency * (start + offset) / rate))
                for offset in range(rate)
            )
            handle.writeframes(struct.pack("<" + "h" * rate, *samples))


def create_fixture(data_dir: Path) -> None:
    if data_dir.exists() and any(data_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite a non-empty directory: {data_dir}")
    data_dir.mkdir(parents=True, exist_ok=True)
    audio = data_dir / "fixture-audio"
    audio.mkdir()
    database = Database(data_dir / "mtee.sqlite3")
    try:
        database.migrate()
        library = LibraryRepository(database)
        repository = PlaylistsRepository(database)
        service = PlaylistService(repository, library)
        root = library.add_root(audio)
        generation = library.begin_scan(root["id"])
        track_ids = []
        for index, (title, artist) in enumerate(TRACKS):
            path = audio / f"review-{index + 1:02d}.wav"
            write_wave(path, 180 + index * 35)
            track_ids.append(
                library.upsert_location(
                    root["id"],
                    path.name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(
                        title=(title,),
                        artist=(artist,),
                        technical=TechnicalInfo(duration_us=18_000_000),
                    ),
                    generation,
                )
            )
        library.finish_scan(root["id"], generation, complete=True)
        sets = repository.create_folder("Sets")
        warmup = repository.create_folder("Warm-up", sets)
        covers = data_dir / "playlist-covers"
        covers.mkdir()
        for name, color in (("night.png", "#264c72"), ("focus.png", "#7c3458")):
            image = QImage(400, 400, QImage.Format.Format_RGB32)
            image.fill(QColor(color))
            if not image.save(str(covers / name)):
                raise OSError(f"Could not create cover {name}")
        night = repository.create("Night drive", warmup, cover="night.png")
        service.add(night, track_ids[:5])
        repository.pin(night, True)
        focus = repository.create("Deep focus", sets, cover="focus.png")
        service.add(focus, track_ids[2:])
        repository.create(
            "Archive",
            entries=[
                {
                    "track_id": None,
                    "snapshot": {
                        "title": "Lost Signal",
                        "artist": "Unknown artist",
                        "duration": "4:20",
                    },
                }
            ],
        )
        repository.like(track_ids[0], True)
        print(f"Created {len(track_ids)} WAV tracks and 3 playlists in {data_dir}")
    finally:
        database.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    create_fixture(args.data_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

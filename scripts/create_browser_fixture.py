"""Create an isolated, reproducible WAV library for Explorer validation."""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

__all__ = ["create_fixture", "main"]


def create_fixture(output: Path, count: int) -> int:
    """Write ``count`` tiny valid WAVs; refuse to replace non-empty data."""
    if count < 0:
        raise ValueError("count must not be negative")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError(f"Refusing to write into a non-empty fixture folder: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "empty folder").mkdir(exist_ok=True)
    audio = b"\x00\x00" * 80
    for index in range(count):
        group = output / f"Collection {index // 1000 + 1:02d}" / ("Été" if index % 2 else "Live")
        group.mkdir(parents=True, exist_ok=True)
        path = group / f"Track {index + 1:05d}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8_000)
            handle.writeframes(audio)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new or empty fixture directory")
    parser.add_argument(
        "--count", required=True, type=int, help="number of synthetic WAV files to create"
    )
    arguments = parser.parse_args(argv)
    try:
        count = create_fixture(arguments.output, arguments.count)
    except (FileExistsError, OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Created {count:,} synthetic WAV files under {arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

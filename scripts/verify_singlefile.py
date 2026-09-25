"""Verify the pinned native payload embedded in the PyInstaller EXE."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from PyInstaller.archive.readers import CArchiveReader


def _normalise(name: str) -> str:
    """Normalise an archive path for Windows and POSIX comparisons."""
    return name.replace("\\", "/").lstrip("./").casefold()


def _manifest(path: Path) -> dict[str, Any]:
    """Read one pinned runtime manifest."""
    return json.loads(path.read_text(encoding="utf-8"))


def _read_entry(reader: CArchiveReader, entry_name: str) -> bytes:
    """Return a required archive entry, with a useful error when it is absent."""
    entries = {_normalise(name): name for name in reader.toc}
    actual_name = entries.get(_normalise(entry_name))
    if actual_name is None:
        raise RuntimeError(f"The single-file executable is missing {entry_name}.")
    return reader.extract(actual_name)


def _verify_entry(
    reader: CArchiveReader,
    entry_name: str,
    expected_size: int,
    expected_sha256: str,
) -> bytes:
    """Check the bytes stored in the executable against a pinned manifest."""
    payload = _read_entry(reader, entry_name)
    actual_hash = hashlib.sha256(payload).hexdigest()
    if len(payload) != expected_size or actual_hash != expected_sha256.lower():
        raise RuntimeError(
            f"Embedded payload does not match its manifest: {entry_name} "
            f"(size={len(payload)}, sha256={actual_hash})."
        )
    return payload


def _write_runtime_file(root: Path, archive_name: str, payload: bytes) -> None:
    """Extract a verified file beneath the temporary runtime check directory."""
    target = root.joinpath(*PurePosixPath(archive_name).parts).resolve()
    resolved_root = root.resolve()
    if not target.is_relative_to(resolved_root):
        raise RuntimeError(f"Unsafe embedded path: {archive_name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def verify(executable: Path, ffmpeg_path: Path, mpv_path: Path, runtime_root: Path) -> int:
    """Verify runtime hashes and extract FFmpeg for a version-banner check."""
    ffmpeg_manifest = _manifest(ffmpeg_path)
    mpv_manifest = _manifest(mpv_path)
    reader = CArchiveReader(str(executable))

    _read_entry(reader, "mtee/qml/Main.qml")

    license_info = ffmpeg_manifest["license"]
    license_path = str(license_info["bundled_path"])
    _verify_entry(
        reader,
        license_path,
        int(license_info["size_bytes"]),
        str(license_info["sha256"]),
    )

    library_info = mpv_manifest["library"]
    mpv_archive_path = str(library_info["packaged_path"])
    _verify_entry(
        reader,
        mpv_archive_path,
        int(library_info["size_bytes"]),
        str(library_info["sha256"]),
    )

    for binary in ffmpeg_manifest["binaries"]:
        archive_path = f"mtee/native/ffmpeg/bin/{binary['name']}"
        payload = _verify_entry(
            reader,
            archive_path,
            int(binary["size_bytes"]),
            str(binary["sha256"]),
        )
        _write_runtime_file(runtime_root, archive_path, payload)

    print("Verified embedded QML, FFmpeg notice, libmpv, and FFmpeg runtime hashes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--ffmpeg-manifest", type=Path, required=True)
    parser.add_argument("--mpv-manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        return verify(
            arguments.executable,
            arguments.ffmpeg_manifest,
            arguments.mpv_manifest,
            arguments.runtime_root,
        )
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

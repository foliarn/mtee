"""Atomic, versioned and quota-bounded waveform cache files."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
import zlib
from pathlib import Path

from mtee.domain.tracks import SourceRevision
from mtee.domain.waveform import WaveformConfig, WaveformData, WaveformLevel

__all__ = ["WaveformCache"]

_MAGIC = b"MTEEWFM1"
_MAX_CACHE_BYTES = 256 * 1024 * 1024
_MAX_HEADER_BYTES = 64 * 1024
_MAX_LEVELS = 32


class WaveformCache:
    def __init__(self, root: Path, *, quota_bytes: int = _MAX_CACHE_BYTES) -> None:
        if quota_bytes < 1024:
            raise ValueError("quota_bytes must be at least 1024")
        self._root = (Path(root) / "waveforms").resolve()
        self._quota = quota_bytes

    def load(
        self, track_id: str, revision: SourceRevision, config: WaveformConfig
    ) -> WaveformData | None:
        path = self._path(track_id, revision, config)
        try:
            if path.stat().st_size > min(self._quota, _MAX_CACHE_BYTES):
                return None
            raw = path.read_bytes()
            if len(raw) > min(self._quota, _MAX_CACHE_BYTES) or raw[: len(_MAGIC)] != _MAGIC:
                return None
            header_length = struct.unpack_from("<I", raw, len(_MAGIC))[0]
            header_start = len(_MAGIC) + 4
            payload_start = header_start + header_length
            if (
                header_length < 2
                or header_length > _MAX_HEADER_BYTES
                or payload_start >= len(raw)
            ):
                return None
            header = json.loads(raw[header_start : header_start + header_length])
            if header.get("track_id") != track_id:
                return None
            if header.get("revision") != _revision_data(revision):
                return None
            if header.get("config") != _config_data(config):
                return None
            channels = config.channels
            raw_levels = header.get("levels")
            if not isinstance(raw_levels, list) or not 1 <= len(raw_levels) <= _MAX_LEVELS:
                return None
            bin_counts = []
            expected_bytes = 0
            previous = 0
            for value in raw_levels:
                if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                    return None
                if previous and value > previous:
                    return None
                previous = value
                bin_counts.append(value)
                expected_bytes += value * channels * 4
                if expected_bytes > self._quota:
                    return None
            decompressor = zlib.decompressobj()
            payload = decompressor.decompress(raw[payload_start:], expected_bytes + 1)
            if (
                len(payload) != expected_bytes
                or not decompressor.eof
                or decompressor.unused_data
                or decompressor.unconsumed_tail
            ):
                return None
            offset = 0
            levels = []
            for bin_count in bin_counts:
                count = bin_count * channels * 2
                size = count * 2
                if bin_count < 1 or offset + size > len(payload):
                    return None
                values = struct.unpack_from("<" + "h" * count, payload, offset)
                levels.append(WaveformLevel(int(bin_count), channels, values))
                offset += size
            if offset != len(payload):
                return None
            return WaveformData(
                track_id, revision, config, int(header["duration_us"]), tuple(levels)
            )
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            struct.error,
            zlib.error,
            OverflowError,
        ):
            return None

    def store(self, data: WaveformData) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._path(data.track_id, data.source_revision, data.config)
        header = json.dumps(
            {
                "track_id": data.track_id,
                "revision": _revision_data(data.source_revision),
                "config": _config_data(data.config),
                "duration_us": data.duration_us,
                "levels": [level.bin_count for level in data.levels],
            },
            separators=(",", ":"),
        ).encode("utf-8")
        payload = b"".join(
            struct.pack("<" + "h" * len(level.values), *level.values) for level in data.levels
        )
        raw = _MAGIC + struct.pack("<I", len(header)) + header + zlib.compress(payload, 6)
        if len(raw) > self._quota:
            raise ValueError("The waveform cache item exceeds its configured quota.")
        fd, temporary = tempfile.mkstemp(prefix=".waveform-", suffix=".tmp", dir=self._root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            self._evict(target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return target

    def invalidate(self, track_id: str, revision: SourceRevision | None = None) -> int:
        if not self._root.is_dir():
            return 0
        prefix = hashlib.sha256(track_id.encode("utf-8")).hexdigest()[:24]
        removed = 0
        for path in self._root.glob(f"{prefix}-*.wfm"):
            if path.resolve().parent != self._root:
                continue
            if revision is not None:
                try:
                    raw = path.read_bytes()
                    header_start = len(_MAGIC) + 4
                    header_length = struct.unpack_from("<I", raw, len(_MAGIC))[0]
                    header = json.loads(raw[header_start : header_start + header_length])
                    if header.get("revision") == _revision_data(revision):
                        continue
                except (OSError, ValueError, KeyError, TypeError, struct.error):
                    pass
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def _path(self, track_id: str, revision: SourceRevision, config: WaveformConfig) -> Path:
        track_key = hashlib.sha256(track_id.encode("utf-8")).hexdigest()[:24]
        key = hashlib.sha256(
            json.dumps(
                {
                    "revision": _revision_data(revision),
                    "config": _config_data(config),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:32]
        return self._root / f"{track_key}-{key}.wfm"

    def _evict(self, keep: Path) -> None:
        paths = [path for path in self._root.glob("*.wfm") if path.resolve().parent == self._root]
        total = sum(path.stat().st_size for path in paths if path.exists())
        for path in sorted(paths, key=lambda item: item.stat().st_mtime_ns):
            if total <= self._quota or path == keep:
                continue
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            total -= size


def _revision_data(revision: SourceRevision) -> dict[str, object]:
    return {
        "size_bytes": revision.size_bytes,
        "mtime_ns": revision.mtime_ns,
        "file_id": revision.file_id,
        "generation": revision.generation,
    }


def _config_data(config: WaveformConfig) -> dict[str, int]:
    return {
        "sample_rate": config.sample_rate,
        "channels": config.channels,
        "bin_ms": config.bin_ms,
        "algorithm_version": config.algorithm_version,
    }

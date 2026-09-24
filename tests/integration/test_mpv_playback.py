"""Native libmpv decoding smoke test using generated, license-free PCM audio."""

from __future__ import annotations

import math
import os
import struct
import threading
import time
import wave
from pathlib import Path

import pytest

from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import BackendEvent


def _write_tone(path: Path, duration_seconds: float = 3.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 44_100
    sample_count = int(sample_rate * duration_seconds)
    pcm = bytearray()
    for index in range(sample_count):
        value = round(12_000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        pcm.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def _integer(value: object) -> int:
    return value if isinstance(value, int) else 0


@pytest.mark.native_audio
def test_native_libmpv_decodes_seeks_and_pauses_wav(tmp_path: Path) -> None:
    audio_path = tmp_path / "MTEE native test épuré" / "tone 440Hz.wav"
    _write_tone(audio_path)
    events: list[BackendEvent] = []
    event_lock = threading.Lock()
    event_changed = threading.Event()
    packaged_runtime = os.environ.get("MTEE_TEST_MPV_LIBRARY")
    backend = MpvBackend(
        Path(packaged_runtime) if packaged_runtime else None,
        audio_output="null",
    )

    def on_event(event: BackendEvent) -> None:
        with event_lock:
            events.append(event)
        event_changed.set()

    backend.set_event_handler(on_event)
    try:
        backend.load(audio_path, 41)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with event_lock:
                if any(event.name in {"loaded", "error"} for event in events):
                    break
            event_changed.wait(0.1)
            event_changed.clear()
        with event_lock:
            snapshot = list(events)
        assert any(event.name == "loaded" and event.session_id == 41 for event in snapshot)
        assert not any(event.name == "error" for event in snapshot)

        deadline = time.monotonic() + 3
        duration = 0
        codec = ""
        seekable = False
        while time.monotonic() < deadline:
            with event_lock:
                snapshot = list(events)
            duration = next(
                (
                    _integer(event.value)
                    for event in snapshot
                    if event.name == "duration" and _integer(event.value) > 0
                ),
                0,
            )
            codec = next((str(event.value) for event in snapshot if event.name == "codec"), "")
            seekable = any(event.name == "seekable" and event.value is True for event in snapshot)
            if duration and codec and seekable:
                break
            event_changed.wait(0.05)
            event_changed.clear()
        assert duration >= 2_900_000
        assert codec
        assert seekable

        backend.set_paused(True)
        backend.set_paused(False)
        backend.seek(1_000_000)
        deadline = time.monotonic() + 2
        positions = []
        while time.monotonic() < deadline:
            position = backend.position_us()
            if position is not None:
                positions.append(position)
                if 700_000 <= position <= 1_300_000:
                    break
            time.sleep(0.025)
        assert positions
        assert min(abs(position - 1_000_000) for position in positions) <= 300_000
    finally:
        backend.close()

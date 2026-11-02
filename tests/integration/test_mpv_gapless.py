"""Gapless switch between two files through the real libmpv, captured with ao=pcm.

The PCM audio output writes the exact stream to a file, so no sound card is needed. Two
files hold one continuous sine, split in the middle; the second one is queued with a
different gain. The captured stream must have no hole at the boundary and the gain must
change on the very first sample of the second file.
"""

from __future__ import annotations

import array
import math
import os
import queue
import struct
import time
import wave
from pathlib import Path

import pytest

from mtee.domain.source_tracks import PlayableSource
from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import BackendEvent

RATE = 44_100
HALF = RATE * 3 // 2
AMPLITUDE = 12_000
GAIN_DB = -6.0


def _sine(count: int, start: int) -> list[int]:
    return [
        round(AMPLITUDE * math.sin(2 * math.pi * 1000 * (start + n) / RATE)) for n in range(count)
    ]


def _write_stereo(path: Path, samples: list[int]) -> None:
    frames = b"".join(struct.pack("<hh", value, value) for value in samples)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)


def _zero_runs(samples: array.array) -> list[int]:
    runs: list[int] = []
    length = 0
    for value in samples:
        if value == 0:
            length += 1
        else:
            if length:
                runs.append(length)
            length = 0
    if length:
        runs.append(length)
    return runs


@pytest.mark.native_audio
def test_two_consecutive_files_play_with_no_gap_and_the_gain_changes_at_the_boundary(
    tmp_path: Path,
) -> None:
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    _write_stereo(first, _sine(HALF, 0))
    _write_stereo(second, _sine(HALF, HALF))
    output = tmp_path / "out.pcm"
    packaged_runtime = os.environ.get("MTEE_TEST_MPV_LIBRARY")
    backend = MpvBackend(
        Path(packaged_runtime) if packaged_runtime else None,
        audio_output="pcm",
        extra_options={"ao-pcm-file": str(output), "ao-pcm-waveheader": "no"},
    )
    events: queue.Queue[BackendEvent] = queue.Queue()
    backend.set_event_handler(events.put)
    seen: list[BackendEvent] = []
    try:
        backend.set_paused(True)
        backend.load(first, 1)
        backend.queue_next(second, 2, GAIN_DB)
        backend.set_paused(False)
        end_events = 0
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and end_events < 2:
            try:
                event = events.get(timeout=0.1)
            except queue.Empty:
                continue
            seen.append(event)
            end_events += event.name in {"eof", "error"}
        time.sleep(0.3)
    finally:
        backend.close()

    names = [(event.name, event.session_id) for event in seen]
    assert ("eof", 1) in names and ("eof", 2) in names, names
    assert names.index(("eof", 1)) < names.index(("start-file", 2)) < names.index(("loaded", 2))
    # The new entry's stream values are sent even when they equal the previous entry's.
    assert any(e.name == "duration" and e.session_id == 2 for e in seen)
    assert any(e.name == "seekable" and e.session_id == 2 and e.value is True for e in seen)
    assert not any(e.name == "error" for e in seen)

    raw = array.array("h")
    raw.frombytes(output.read_bytes())
    left = array.array("h", raw[0::2])
    assert len(left) == 2 * HALF
    # A sine sampled at 44.1 kHz has at most one exact zero in a row; a gap would have more.
    assert max(_zero_runs(left), default=0) <= 1

    expected = _sine(2 * HALF, 0)
    # libmpv turns dB into a factor as 2 ** (dB / 6), which is 0.02 dB off at -6 dB.
    scale = 2 ** (GAIN_DB / 6)
    first_error = max(abs(left[n] - expected[n]) for n in range(HALF))
    second_error = max(abs(left[n] - round(expected[n] * scale)) for n in range(HALF, 2 * HALF))
    assert first_error <= 2
    assert second_error <= 2  # the gain applies from the first sample of the second file


class _CountingBackend(MpvBackend):
    loads = 0

    def load(self, source: Path | PlayableSource, session_id: int) -> None:
        self.loads += 1
        super().load(source, session_id)


@pytest.mark.native_audio
def test_the_player_service_switches_tracks_without_loading_the_second_one(
    qapp, qtbot, tmp_path: Path
) -> None:
    from mtee.domain.playback import PlaybackStatus
    from mtee.domain.tracks import TrackId
    from mtee.services.file_access import FileAccessCoordinator
    from mtee.services.player_service import PlayerService

    paths = [tmp_path / "one.wav", tmp_path / "two.wav"]
    for index, path in enumerate(paths):
        _write_stereo(path, _sine(RATE * 2, index * RATE * 2))
    ids = [str(TrackId.new()) for _ in paths]
    rows = {
        track_id: {
            "id": track_id,
            "title": path.stem,
            "path": str(path),
            "durationUs": 2_000_000,
            "status": "readable",
        }
        for track_id, path in zip(ids, paths, strict=True)
    }
    packaged_runtime = os.environ.get("MTEE_TEST_MPV_LIBRARY")
    backend = _CountingBackend(
        Path(packaged_runtime) if packaged_runtime else None, audio_output="null"
    )
    service = PlayerService(
        lambda track_id: dict(rows[track_id]), FileAccessCoordinator(), backend, parent=qapp
    )
    try:
        service.play_queue(ids)
        qtbot.waitUntil(
            lambda: (
                service.state.current_id == ids[1]
                and service.state.status is PlaybackStatus.PLAYING
                and service.state.seekable
            ),
            timeout=15_000,
        )
        assert backend.loads == 1  # the second track was appended, not loaded
        assert service.state.current_index == 1
        assert service.state.duration_us is not None and service.state.duration_us > 1_900_000
        qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.ENDED, timeout=15_000)
    finally:
        service.close()

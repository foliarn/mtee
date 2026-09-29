from __future__ import annotations

import numpy as np
import pytest
from tests.helpers.analysis_audio import drum_loop, to_stereo_pcm

from mtee.services.analysis.features import ENVELOPE_RATE, SAMPLE_RATE, FeatureExtractor
from mtee.services.analysis.tempo import estimate_tempo


def _envelope(signal: np.ndarray) -> np.ndarray:
    extractor = FeatureExtractor(tonality=False)
    pcm = to_stereo_pcm(signal)
    step = 131_072
    for start in range(0, len(pcm), step):
        extractor.feed(pcm[start : start + step])
    return extractor.finish().onset_envelope


@pytest.mark.parametrize(
    ("pattern", "bpm", "swing", "seconds"),
    [
        ("house", 128.0, 0.0, 90),
        ("house", 127.98, 0.0, 90),
        ("house", 124.37, 0.0, 90),
        ("house", 150.0, 0.0, 40),
        ("garage", 130.0, 0.35, 90),
        ("garage", 133.3, 0.2, 120),
    ],
)
def test_steady_tempo_is_found_to_a_few_hundredths_of_a_bpm(
    pattern: str, bpm: float, swing: float, seconds: int
) -> None:
    estimate = estimate_tempo(
        _envelope(drum_loop(bpm, seconds, pattern=pattern, swing=swing)),
        ENVELOPE_RATE,
        70,
        180,
    )
    assert estimate is not None
    assert estimate.bpm == pytest.approx(bpm, abs=0.03)


def test_tempo_is_folded_into_the_requested_range() -> None:
    envelope = _envelope(drum_loop(128.0, 90, pattern="house"))
    folded = estimate_tempo(envelope, ENVELOPE_RATE, 40, 100)
    assert folded is not None
    assert folded.bpm == pytest.approx(64.0, abs=0.03)
    kept = estimate_tempo(envelope, ENVELOPE_RATE, 100, 200)
    assert kept is not None
    assert kept.bpm == pytest.approx(128.0, abs=0.03)


def test_a_partly_silent_track_keeps_its_tempo() -> None:
    signal = np.concatenate([np.zeros(30 * SAMPLE_RATE, dtype=np.float32), drum_loop(122.0, 90)])
    estimate = estimate_tempo(_envelope(signal), ENVELOPE_RATE, 70, 180)
    assert estimate is not None
    assert estimate.bpm == pytest.approx(122.0, abs=0.03)


def test_without_a_pulse_no_tempo_is_invented() -> None:
    generator = np.random.default_rng(5)
    for signal in (
        np.zeros(60 * SAMPLE_RATE),
        0.2 * generator.standard_normal(60 * SAMPLE_RATE),
    ):
        assert estimate_tempo(_envelope(signal), ENVELOPE_RATE, 70, 180) is None


def test_material_that_is_too_short_gives_no_tempo() -> None:
    assert estimate_tempo(_envelope(drum_loop(128.0, 5)), ENVELOPE_RATE, 70, 180) is None


def test_a_range_narrower_than_an_octave_is_refused() -> None:
    with pytest.raises(ValueError):
        estimate_tempo(np.ones(2000, dtype=np.float32), ENVELOPE_RATE, 100, 150)


def test_streaming_in_odd_blocks_gives_the_same_envelope_as_one_block() -> None:
    pcm = to_stereo_pcm(drum_loop(126.0, 20))
    whole = FeatureExtractor(tonality=False)
    whole.feed(pcm)
    pieces = FeatureExtractor(tonality=False)
    position = 0
    for size in (4_000, 12, 7_776, 400, 100_000, 4):
        pieces.feed(pcm[position : position + size])
        position += size
    while position < len(pcm):
        pieces.feed(pcm[position : position + 5_000])
        position += 5_000
    first = whole.finish().onset_envelope
    second = pieces.finish().onset_envelope
    assert first.shape == second.shape
    assert np.allclose(first, second, atol=1e-4)

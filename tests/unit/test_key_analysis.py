from __future__ import annotations

import numpy as np
import pytest
from tests.helpers.analysis_audio import drum_loop, key_progression, to_stereo_pcm

from mtee.domain.musical_key import MusicalKey
from mtee.services.analysis.features import SAMPLE_RATE, FeatureExtractor
from mtee.services.analysis.key import estimate_key


def _key_of(signal: np.ndarray):
    extractor = FeatureExtractor(rhythm=False)
    pcm = to_stereo_pcm(signal)
    step = 131_072
    for start in range(0, len(pcm), step):
        extractor.feed(pcm[start : start + step])
    features = extractor.finish()
    return estimate_key(features.pitch_profile, features.bass_profile)


def _detuned(signal: np.ndarray, cents: float) -> np.ndarray:
    positions = np.arange(0, signal.size - 1, 2 ** (cents / 1200))
    return np.interp(positions, np.arange(signal.size), signal).astype(np.float32)


@pytest.mark.parametrize("tonic", range(12))
@pytest.mark.parametrize("minor", [False, True])
def test_all_twenty_four_keys_are_recognised(tonic: int, minor: bool) -> None:
    estimate = _key_of(key_progression(tonic, minor, 40))
    assert estimate is not None
    assert estimate.key == MusicalKey(tonic, minor)


@pytest.mark.parametrize("cents", [30, -40])
def test_a_recording_tuned_away_from_a440_keeps_its_key(cents: int) -> None:
    for tonic, minor in ((0, False), (9, True), (6, True)):
        estimate = _key_of(_detuned(key_progression(tonic, minor, 40), cents))
        assert estimate is not None
        assert estimate.key == MusicalKey(tonic, minor)


def test_the_key_survives_a_drum_loop_over_the_harmony() -> None:
    mix = 0.5 * key_progression(3, True, 40) + 0.6 * drum_loop(124.0, 40, pattern="house")
    estimate = _key_of(mix)
    assert estimate is not None
    assert estimate.key == MusicalKey(3, True)


def test_without_tonal_evidence_no_key_is_invented() -> None:
    generator = np.random.default_rng(3)
    assert _key_of(np.zeros(20 * SAMPLE_RATE)) is None
    for seed in (3, 4):
        noise = 0.2 * np.random.default_rng(seed).standard_normal(20 * SAMPLE_RATE)
        assert _key_of(noise) is None
    assert generator is not None


def test_a_profile_of_the_wrong_shape_is_ignored() -> None:
    assert estimate_key(np.zeros(12)) is None
    assert estimate_key(np.full(36, np.nan)) is None

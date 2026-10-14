"""Playback gain from the stored loudness: target, peak ceiling, and the cases without data."""

from __future__ import annotations

import pytest

from mtee.domain.loudness import (
    GAIN_LIMITS_DB,
    MAX_BOOST_DB,
    NORMALIZATION_LEVELS,
    PEAK_CEILING_DBFS,
    NormalizationSettings,
    playback_gain_db,
)

NORMAL = NormalizationSettings(enabled=True, level="normal")


def test_the_defaults_are_on_and_normal() -> None:
    settings = NormalizationSettings()

    assert settings.enabled is True
    assert settings.level == "normal"
    assert settings.target_lufs == -14.0


def test_the_three_levels_are_the_documented_targets() -> None:
    assert NORMALIZATION_LEVELS == {"quiet": -23.0, "normal": -14.0, "loud": -11.0}


def test_a_quiet_track_is_turned_up_to_the_target() -> None:
    assert playback_gain_db(-20.0, -10.0, NORMAL) == pytest.approx(6.0)


def test_a_loud_track_is_turned_down_to_the_target_without_any_peak_check() -> None:
    assert playback_gain_db(-8.0, 0.0, NORMAL) == pytest.approx(-6.0)


def test_a_boost_stops_where_the_peak_reaches_the_ceiling() -> None:
    # The target needs +10 dB, and the peak at -12 dBFS leaves exactly 10 dB before -2 dBFS.
    assert playback_gain_db(-24.0, -12.0, NORMAL) == pytest.approx(10.0)
    assert playback_gain_db(-24.0, -6.0, NORMAL) == pytest.approx(4.0)


def test_the_ceiling_is_minus_two_dbfs_exactly() -> None:
    gain = playback_gain_db(-30.0, -10.0, NORMAL)

    assert PEAK_CEILING_DBFS == -2.0
    assert gain == pytest.approx(8.0)
    assert -10.0 + gain == pytest.approx(-2.0)


def test_a_track_whose_peak_is_already_at_the_ceiling_is_not_boosted() -> None:
    assert playback_gain_db(-30.0, -2.0, NORMAL) == 0.0
    assert playback_gain_db(-30.0, -1.0, NORMAL) == 0.0
    assert playback_gain_db(-30.0, 0.0, NORMAL) == 0.0


def test_a_peak_above_the_ceiling_never_gives_a_boost() -> None:
    assert playback_gain_db(-30.0, -1.5, NORMAL) == 0.0


def test_a_boost_is_capped_at_twelve_decibels() -> None:
    # The target needs +26 dB and the peak leaves 28 dB, so only the cap applies.
    assert MAX_BOOST_DB == 12.0
    assert playback_gain_db(-40.0, -30.0, NORMAL) == pytest.approx(12.0)


def test_the_boost_cap_does_not_limit_a_cut() -> None:
    assert playback_gain_db(0.0, 0.0, NormalizationSettings(level="quiet")) == pytest.approx(-23.0)


def test_a_cut_is_not_limited_by_the_peak() -> None:
    # A loud track with a peak above the ceiling is only turned down, never up.
    assert playback_gain_db(-4.0, 0.5, NORMAL) == pytest.approx(-10.0)


def test_a_track_without_loudness_plays_with_no_gain() -> None:
    assert playback_gain_db(None, -6.0, NORMAL) == 0.0
    assert playback_gain_db(None, None, NORMAL) == 0.0


def test_a_boost_without_a_peak_is_refused_rather_than_guessed() -> None:
    assert playback_gain_db(-30.0, None, NORMAL) == 0.0


def test_a_cut_without_a_peak_still_applies() -> None:
    assert playback_gain_db(-4.0, None, NORMAL) == pytest.approx(-10.0)


def test_disabled_normalization_is_always_zero() -> None:
    off = NormalizationSettings(enabled=False, level="loud")

    assert playback_gain_db(-30.0, -10.0, off) == 0.0
    assert playback_gain_db(-4.0, 0.0, off) == 0.0


def test_each_level_moves_the_same_track_by_its_own_target() -> None:
    gains = {
        level: playback_gain_db(-18.0, -20.0, NormalizationSettings(level=level))
        for level in NORMALIZATION_LEVELS
    }

    assert gains == {"quiet": -5.0, "normal": 4.0, "loud": 7.0}


def test_the_gain_stays_inside_the_range_the_native_player_accepts() -> None:
    low, high = GAIN_LIMITS_DB

    assert high > MAX_BOOST_DB
    assert playback_gain_db(-120.0, -200.0, NORMAL) == MAX_BOOST_DB
    assert playback_gain_db(110.0, 0.0, NORMAL) == low


def test_an_unknown_level_falls_back_to_the_default() -> None:
    settings = NormalizationSettings(enabled=True, level="deafening").normalized()

    assert settings.level == "normal"

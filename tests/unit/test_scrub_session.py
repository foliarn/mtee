from __future__ import annotations

import pytest

from mtee.domain.scrub import EnsurePlaying, Next, ScrubCommand, ScrubSession, Seek, Silence

WIDTH = 1000.0  # pixels: 2000 px/s is a ratio speed of 2.0 per second


def _run(session: ScrubSession, steps: list[tuple[str, float, float]]) -> list[ScrubCommand]:
    commands: list[ScrubCommand] = []
    for kind, ratio, t_ms in steps:
        if kind == "press":
            commands += session.press(ratio, t_ms)
        elif kind == "move":
            commands += session.move(ratio, t_ms)
        elif kind == "tick":
            commands += session.tick(t_ms)
        else:
            commands += session.release(ratio, t_ms)
    return commands


def _seeks(commands: list[ScrubCommand]) -> list[float]:
    return [command.ratio for command in commands if isinstance(command, Seek)]


def test_a_simple_click_seeks_then_makes_sure_playback_runs() -> None:
    session = ScrubSession(WIDTH)
    commands = _run(session, [("press", 0.4, 0), ("release", 0.4, 40)])
    assert commands == [Seek(0.4), EnsurePlaying(), EnsurePlaying()]


def test_a_still_hold_adds_no_seek_even_after_many_ticks() -> None:
    session = ScrubSession(WIDTH)
    commands = _run(session, [("press", 0.4, 0)])
    for t in range(20, 3_000, 20):
        commands += session.tick(t)
    commands += session.release(0.4, 3_000)
    assert _seeks(commands) == [0.4]
    assert not any(isinstance(command, Silence) for command in commands)


def test_slow_moves_seek_at_most_every_hundred_milliseconds() -> None:
    session = ScrubSession(WIDTH)
    commands = session.press(0.10, 0)
    ratio = 0.10
    for t in range(10, 410, 10):
        ratio += 0.001  # 0.1 per second: far below the speed threshold
        commands += session.move(ratio, t)
        commands += session.tick(t)
    seek_ratios = _seeks(commands)
    assert 4 <= len(seek_ratios) <= 5  # the press, then one about every 100 ms
    assert seek_ratios == sorted(seek_ratios)
    assert not any(isinstance(command, Silence) for command in commands)


def test_a_move_that_waits_for_the_interval_is_applied_by_a_tick() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.2, 0)
    assert session.move(0.25, 30) == []  # too soon after the press
    assert session.tick(60) == []
    assert session.tick(100) == [Seek(0.25)]
    assert session.tick(140) == []  # nothing new to apply


def test_a_fast_move_cuts_the_sound_once_without_any_seek() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.1, 0)
    commands = _run(
        session,
        [
            ("move", 0.2, 20),
            ("move", 0.4, 40),
            ("move", 0.6, 60),
            ("move", 0.8, 80),
            ("tick", 0, 90),
        ],
    )
    assert commands == [Silence(True)]
    assert session.silent
    assert _seeks(commands) == []


def test_slowing_down_seeks_then_restores_the_sound() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.1, 0)
    session.move(0.4, 20)
    session.move(0.8, 40)  # fast: 20 ratio per second
    assert session.silent
    commands: list[ScrubCommand] = []
    for t in range(60, 400, 20):
        commands += session.tick(t)
    assert commands == [Seek(0.8), Silence(False)]
    assert not session.silent


def test_release_after_a_move_not_yet_applied_seeks_there() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.2, 0)
    session.move(0.22, 30)
    commands = session.release(0.22, 40)
    assert commands == [Seek(0.22), EnsurePlaying()]


def test_release_while_silent_restores_the_sound_after_the_final_seek() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.1, 0)
    session.move(0.5, 20)
    session.move(0.9, 40)
    assert session.silent
    assert session.release(0.9, 50) == [Seek(0.9), Silence(False), EnsurePlaying()]
    assert not session.silent


def test_leaving_by_the_left_holds_the_start() -> None:
    session = ScrubSession(WIDTH, fast_px_per_s=1e9)  # speed is not what this is about
    session.press(0.5, 0)
    commands = session.move(-0.2, 150)
    commands += session.tick(300)
    assert _seeks(commands) == [0.0]
    assert session.release(-0.4, 400) == [EnsurePlaying()]  # already at 0: no new seek


def test_leaving_by_the_right_cuts_the_sound_without_seeking_and_releases_to_next() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.9, 0)
    commands = session.move(1.2, 150)
    assert commands == [Silence(True)]
    assert session.beyond_end
    assert session.tick(400) == []  # a seek to the end would finish the track
    assert session.release(1.5, 500) == [Silence(False), Next()]


def test_coming_back_before_the_release_skips_nothing() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.9, 0)
    session.move(1.2, 150)
    session.move(0.7, 300)
    assert not session.beyond_end
    commands: list[ScrubCommand] = []
    for t in range(320, 600, 20):
        commands += session.tick(t)
    assert commands == [Seek(0.7), Silence(False)]
    release = session.release(0.7, 700)
    assert Next() not in release
    assert release == [EnsurePlaying()]


def test_a_release_without_any_move_since_the_last_seek_adds_none() -> None:
    session = ScrubSession(WIDTH)
    session.press(0.3, 0)
    session.move(0.3, 50)
    assert session.release(0.3, 60) == [EnsurePlaying()]


def test_a_press_beyond_the_end_is_silent_and_seeks_nothing() -> None:
    session = ScrubSession(WIDTH)
    assert session.press(1.3, 0) == [Silence(True), EnsurePlaying()]
    assert session.release(1.3, 100) == [Silence(False), Next()]


def test_the_threshold_scales_with_the_width() -> None:
    narrow = ScrubSession(500.0)  # 2000 px/s is 4 ratio per second
    wide = ScrubSession(2000.0)  # 2000 px/s is 1 ratio per second
    for session in (narrow, wide):
        session.press(0.1, 0)
        session.move(0.2, 50)  # 2 ratio per second
    assert not narrow.silent
    assert wide.silent


def test_an_invalid_width_is_refused() -> None:
    with pytest.raises(ValueError):
        ScrubSession(0)

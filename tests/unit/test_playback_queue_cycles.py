"""Shuffle and repeat cycles of the pure queue, with deterministic random order."""

from __future__ import annotations

import random

from mtee.domain.playback_queue import QueueEntry, QueueState


def context(*names: str) -> list[QueueEntry]:
    return [QueueEntry.create(name, "context", source="folder:test") for name in names]


def manual(*names: str) -> list[QueueEntry]:
    return [QueueEntry.create(name, "manual") for name in names]


def names(entries: tuple[QueueEntry, ...] | list[QueueEntry]) -> list[str]:
    return [entry.track_id for entry in entries]


def test_start_context_shuffles_only_the_entries_after_the_start_when_shuffle_is_on() -> None:
    entries = context("1", "2", "3", "4", "5", "6")
    expected = ["3", "4", "5", "6"]
    random.Random(7).shuffle(expected)

    queue = QueueState().set_shuffle(True).start_context(entries, 1, rng=random.Random(7))

    assert queue.current is entries[1]
    assert names(queue.past) == ["1"]
    assert names(queue.upcoming) == expected
    assert queue.context_order == tuple(entries)
    assert queue.shuffle is True


def test_start_context_keeps_manual_entries_first_and_turning_shuffle_off_restores_order() -> None:
    entries = context("1", "2", "3", "4")
    nine = manual("9")[0]
    queue = QueueState().set_shuffle(True).enqueue([nine])

    started = queue.start_context(entries, 0, rng=random.Random(2))

    assert started.upcoming[0] is nine
    assert sorted(names(started.upcoming[1:])) == ["2", "3", "4"]
    restored = started.set_shuffle(False)
    assert restored.upcoming == (nine, *entries[1:])


def test_start_context_without_shuffle_keeps_the_order() -> None:
    entries = context("1", "2", "3")

    queue = QueueState().start_context(entries, 0, rng=random.Random(1))

    assert queue.upcoming == tuple(entries[1:])


def test_repeat_all_reshuffles_the_cycle_and_keeps_the_original_context_order() -> None:
    entries = context("1", "2", "3", "4")
    queue = QueueState().set_shuffle(True).start_context(entries, 0, rng=random.Random(0))
    while queue.upcoming:
        queue = queue.next()

    expected = list(entries)
    random.Random(3).shuffle(expected)
    restarted = queue.repeat_all(rng=random.Random(3))

    assert restarted.current is expected[0]
    assert list(restarted.upcoming) == expected[1:]
    assert restarted.past == ()
    assert restarted.context_order == tuple(entries)


def test_repeat_all_without_shuffle_restarts_in_context_order() -> None:
    entries = context("1", "2", "3")
    queue = QueueState().start_context(entries, 2)

    restarted = queue.set_repeat("all").repeat_all()

    assert restarted.current is entries[0]
    assert restarted.upcoming == (entries[1], entries[2])


def test_repeat_all_without_context_restarts_the_whole_queue_in_order() -> None:
    zero, one, two = manual("0")[0], manual("1")[0], manual("2")[0]
    queue = QueueState().insert_current(zero).enqueue([one, two]).next()
    assert queue.current is one

    restarted = queue.repeat_all()

    assert restarted.current is zero
    assert restarted.upcoming == (one, two)
    assert restarted.past == ()


def test_repeat_all_on_an_empty_queue_changes_nothing() -> None:
    queue = QueueState()

    assert queue.repeat_all() is queue

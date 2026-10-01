"""Occurrence identity and ordering transitions for the pure queue."""

from __future__ import annotations

import random

from mtee.domain.playback_queue import QueueEntry, QueueState


def context(*names: str) -> list[QueueEntry]:
    return [QueueEntry.create(name, "context", source="folder:test") for name in names]


def manual(*names: str) -> list[QueueEntry]:
    return [QueueEntry.create(name, "manual") for name in names]


def names(entries: tuple[QueueEntry, ...]) -> list[str]:
    return [entry.track_id for entry in entries]


def test_fifo_duplicates_and_context_change_preserve_manual_occurrences() -> None:
    first = context("1", "2", "3", "4", "5")
    queue = QueueState().start_context(first, 0, source="folder:first")
    nine, eight = manual("9", "8")
    queue = queue.enqueue([nine]).enqueue([eight])
    assert names(queue.upcoming) == ["9", "8", "2", "3", "4", "5"]
    second = context("A", "B", "C")
    queue = queue.start_context(second, 1, source="folder:second")
    assert queue.current is second[1]
    assert queue.upcoming == (nine, eight, second[2])

    another_nine = manual("9")[0]
    queue = queue.enqueue([another_nine])
    assert len({entry.entry_id for entry in queue.upcoming}) == 4
    queue = queue.remove(another_nine.entry_id)
    assert nine in queue.upcoming and another_nine not in queue.upcoming


def test_move_reorders_both_origins_and_stale_targets_do_nothing() -> None:
    first = context("1", "2", "3")
    nine = manual("9")[0]
    queue = QueueState().start_context(first, 0).enqueue([nine])
    queue = queue.move(nine.entry_id, None)
    assert names(queue.upcoming) == ["2", "3", "9"]
    queue = queue.move(first[2].entry_id, first[1].entry_id)
    assert names(queue.upcoming) == ["3", "2", "9"]
    revision = queue.revision
    assert queue.move("missing", first[1].entry_id) is queue
    assert queue.move(nine.entry_id, "missing") is queue
    assert queue.revision == revision


def test_previous_and_next_keep_entry_id_for_duplicate_tracks() -> None:
    first = context("1", "2")
    a, b = manual("9", "9")
    queue = QueueState().start_context(first, 0).enqueue([a, b])
    queue = queue.next().next()
    assert queue.current is b
    queue = queue.previous()
    assert queue.current is a and queue.upcoming[0] is b
    queue = queue.next()
    assert queue.current is b and queue.upcoming == (first[1],)


def test_shuffle_preserves_manual_slots_and_unshuffle_omits_consumed() -> None:
    first = context("1", "2", "3", "4")
    a, b = manual("9", "8")
    queue = QueueState().start_context(first, 0).enqueue([a, b])
    queue = queue.move(a.entry_id, first[2].entry_id)
    queue = queue.set_shuffle(True, rng=random.Random(42))
    manual_slots = [
        (i, entry.entry_id) for i, entry in enumerate(queue.upcoming) if entry.origin == "manual"
    ]
    assert manual_slots == [(0, b.entry_id), (2, a.entry_id)]
    consumed = queue.upcoming[0]
    queue = queue.next().set_shuffle(False)
    assert consumed not in queue.upcoming
    assert [entry.track_id for entry in queue.upcoming if entry.origin == "context"] == [
        "2",
        "3",
        "4",
    ]


def test_repeat_one_leaves_pending_and_repeat_all_reuses_context_only() -> None:
    first = context("1", "2")
    nine = manual("9")[0]
    queue = QueueState().start_context(first, 0).enqueue([nine]).set_repeat("one")
    assert queue.current is first[0] and queue.upcoming[0] is nine
    queue = queue.set_repeat("all").next().next().repeat_all()
    assert queue.current is first[0]
    assert queue.upcoming == (first[1],)
    assert nine not in queue.upcoming


def test_insert_current_keeps_upcoming_and_moves_the_previous_current_to_the_past() -> None:
    first = context("1", "2", "3")
    queue = QueueState().start_context(first, 0, source="folder:test")
    queue = queue.enqueue(manual("9"))
    inserted = manual("7")[0]

    result = queue.insert_current(inserted)

    assert result.current is inserted
    assert names(result.past) == ["1"]
    assert result.upcoming == queue.upcoming
    assert result.revision == queue.revision + 1
    assert result.previous().current is first[0]


def test_insert_current_without_a_current_occurrence() -> None:
    inserted = manual("7")[0]

    result = QueueState().insert_current(inserted)

    assert result.current is inserted
    assert result.past == () and result.upcoming == ()

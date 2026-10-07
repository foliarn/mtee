"""Pure occurrence based playback queue transitions."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Any, Literal
from uuid import uuid4

Origin = Literal["manual", "context"]


@dataclass(frozen=True, slots=True)
class QueueEntry:
    entry_id: str
    track_id: str
    origin: Origin
    source: str = ""
    source_title: str = ""
    snapshot: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        track_id: str,
        origin: Origin,
        *,
        source: str = "",
        source_title: str = "",
        snapshot: dict[str, Any] | None = None,
    ) -> QueueEntry:
        return cls(
            str(uuid4()),
            track_id,
            origin,
            source,
            source_title,
            dict(snapshot) if snapshot is not None else None,
        )


@dataclass(frozen=True, slots=True)
class QueueState:
    revision: int = 0
    past: tuple[QueueEntry, ...] = ()
    current: QueueEntry | None = None
    upcoming: tuple[QueueEntry, ...] = ()
    context_order: tuple[QueueEntry, ...] = ()
    source: str = ""
    source_title: str = ""
    shuffle: bool = False
    repeat: Literal["off", "one", "all"] = "off"

    def validate(self) -> None:
        active = (*self.past, *((self.current,) if self.current else ()), *self.upcoming)
        ids = [entry.entry_id for entry in active]
        if len(ids) != len(set(ids)):
            raise ValueError("Queue occurrence IDs must be unique")
        reference = [entry.entry_id for entry in self.context_order]
        if len(reference) != len(set(reference)):
            raise ValueError("Context reference IDs must be unique")
        if any(entry.origin != "context" for entry in self.context_order):
            raise ValueError("Context reference contains manual occurrences")
        if self.revision < 0:
            raise ValueError("Queue revision cannot be negative")

    def _changed(self, **changes: Any) -> QueueState:
        result = replace(self, revision=self.revision + 1, **changes)
        result.validate()
        return result

    def enqueue(self, entries: list[QueueEntry] | tuple[QueueEntry, ...]) -> QueueState:
        if not entries:
            return self
        if any(entry.origin != "manual" for entry in entries):
            raise ValueError("Only manual occurrences can be enqueued")
        upcoming = list(self.upcoming)
        position = 0
        for index, entry in enumerate(upcoming):
            if entry.origin == "manual":
                position = index + 1
        upcoming[position:position] = entries
        return self._changed(upcoming=tuple(upcoming))

    def start_context(
        self,
        entries: list[QueueEntry] | tuple[QueueEntry, ...],
        start_index: int,
        *,
        source: str = "",
        source_title: str = "",
    ) -> QueueState:
        if not entries or not 0 <= start_index < len(entries):
            raise ValueError("Invalid context start")
        if any(entry.origin != "context" for entry in entries):
            raise ValueError("Context contains manual occurrences")
        manual = tuple(entry for entry in self.upcoming if entry.origin == "manual")
        past = (*self.past, *((self.current,) if self.current else ()), *entries[:start_index])
        return self._changed(
            past=past,
            current=entries[start_index],
            upcoming=(*manual, *entries[start_index + 1 :]),
            context_order=tuple(entries),
            source=source,
            source_title=source_title,
        )

    def next(self) -> QueueState:
        if not self.upcoming:
            return self
        past = (*self.past, *((self.current,) if self.current else ()))
        return self._changed(past=past, current=self.upcoming[0], upcoming=self.upcoming[1:])

    def previous(self) -> QueueState:
        if not self.past:
            return self
        upcoming = (*((self.current,) if self.current else ()), *self.upcoming)
        return self._changed(past=self.past[:-1], current=self.past[-1], upcoming=upcoming)

    def previous_wrap(self) -> QueueState:
        """Wrap from the first occurrence to the final context occurrence."""
        if self.past or not self.context_order:
            return self
        manual = tuple(entry for entry in self.upcoming if entry.origin == "manual")
        return self._changed(
            past=self.context_order[:-1],
            current=self.context_order[-1],
            upcoming=manual,
        )

    def play_entry(self, entry_id: str) -> QueueState:
        for index, entry in enumerate(self.upcoming):
            if entry.entry_id == entry_id:
                # Entries jumped over move to the past so playback continues after ``entry``.
                past = (
                    *self.past,
                    *((self.current,) if self.current else ()),
                    *self.upcoming[:index],
                )
                return self._changed(
                    past=past, current=entry, upcoming=self.upcoming[index + 1 :]
                )
        return self

    def insert_current(self, entry: QueueEntry) -> QueueState:
        """Make ``entry`` the current occurrence; the previous one goes to the past.

        What waits in ``upcoming`` is left as it is, manual additions included.
        """
        past = (*self.past, *((self.current,) if self.current else ()))
        return self._changed(past=past, current=entry)

    def remove(self, entry_id: str) -> QueueState:
        upcoming = tuple(entry for entry in self.upcoming if entry.entry_id != entry_id)
        if len(upcoming) == len(self.upcoming):
            return self
        reference = tuple(entry for entry in self.context_order if entry.entry_id != entry_id)
        return self._changed(upcoming=upcoming, context_order=reference)

    def move(self, entry_id: str, before_entry_id: str | None) -> QueueState:
        if entry_id == before_entry_id:
            return self
        upcoming = list(self.upcoming)
        source = next((i for i, entry in enumerate(upcoming) if entry.entry_id == entry_id), -1)
        if source < 0:
            return self
        entry = upcoming.pop(source)
        if before_entry_id is None or before_entry_id == "":
            target = len(upcoming)
        else:
            target = next(
                (i for i, item in enumerate(upcoming) if item.entry_id == before_entry_id), -1
            )
            if target < 0:
                return self
        upcoming.insert(target, entry)
        if tuple(upcoming) == self.upcoming:
            return self
        reference = self.context_order
        if entry.origin == "context":
            waiting_ids = {item.entry_id for item in upcoming if item.origin == "context"}
            earlier = [item for item in reference if item.entry_id not in waiting_ids]
            waiting = [item for item in upcoming if item.origin == "context"]
            reference = tuple((*earlier, *waiting))
        return self._changed(upcoming=tuple(upcoming), context_order=reference)

    def set_shuffle(self, enabled: bool, *, rng: random.Random | None = None) -> QueueState:
        if enabled == self.shuffle:
            return self
        upcoming = list(self.upcoming)
        context_positions = [i for i, entry in enumerate(upcoming) if entry.origin == "context"]
        if enabled:
            context = [upcoming[i] for i in context_positions]
            (rng or random).shuffle(context)
        else:
            waiting = {upcoming[i].entry_id for i in context_positions}
            context = [entry for entry in self.context_order if entry.entry_id in waiting]
            known = {entry.entry_id for entry in context}
            context.extend(
                upcoming[i] for i in context_positions if upcoming[i].entry_id not in known
            )
        for position, entry in zip(context_positions, context, strict=True):
            upcoming[position] = entry
        return self._changed(upcoming=tuple(upcoming), shuffle=enabled)

    def set_repeat(self, repeat: Literal["off", "one", "all"]) -> QueueState:
        if repeat not in ("off", "one", "all"):
            raise ValueError("Unknown repeat mode")
        return self if repeat == self.repeat else self._changed(repeat=repeat)

    def repeat_all(self) -> QueueState:
        if not self.context_order:
            return self
        return self._changed(
            past=(), current=self.context_order[0], upcoming=self.context_order[1:]
        )

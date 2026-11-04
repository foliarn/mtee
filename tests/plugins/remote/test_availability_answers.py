"""The answers of the availability are reused until the plugin says they changed (review 0.3.0).

``status`` runs on the graphical thread at each draw of a list while the filter is on, and the
badge column once per row: both read four tables per call without these answers.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path

import mtee.plugins.remote.availability as availability_module  # pyright: ignore[reportMissingImports]
import pytest
from mtee.plugins.remote import RemoteService  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.availability import (  # pyright: ignore[reportMissingImports]
    AvailabilityAnswers,
    availability_of,
)
from mtee.plugins.remote.store import RemoteStore  # pyright: ignore[reportMissingImports]
from tests.plugins.remote.helpers import FakeLibrary, make_context, track

from mtee.plugins.api import PluginContext


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """The tracks each read of the tables asked for."""
    asked: list[list[str]] = []
    real = availability_module._read

    def counting(context: PluginContext, store: RemoteStore, ids: list[str]) -> object:
        asked.append(list(ids))
        return real(context, store, ids)

    monkeypatch.setattr(availability_module, "_read", counting)
    return asked


@pytest.fixture
def context(tmp_path: Path) -> PluginContext:
    music = tmp_path / "music"
    return make_context(tmp_path, FakeLibrary([music], [track("t1", music / "a.flac")]))


def test_a_track_answered_recently_is_not_read_again(
    context: PluginContext, reads: list[list[str]]
) -> None:
    store = RemoteStore(context)
    answers = AvailabilityAnswers()

    assert availability_of(context, store, ["t1", "t2"], answers) == {"t1": "local", "t2": "local"}
    assert availability_of(context, store, ["t1", "t2", "t3"], answers)["t3"] == "local"

    assert reads == [["t1", "t2"], ["t3"]]


def test_availability_changed_forgets_the_answers_then_tells_the_core(
    context: PluginContext, reads: list[list[str]]
) -> None:
    store = RemoteStore(context)
    answers = AvailabilityAnswers()
    told: list[Sequence[str] | None] = []
    changed = answers.wrap(told.append)
    availability_of(context, store, ["t1", "t2"], answers)

    changed(["t1"])
    availability_of(context, store, ["t1", "t2"], answers)
    changed(None)
    availability_of(context, store, ["t1", "t2"], answers)

    assert told == [["t1"], None]
    assert reads == [["t1", "t2"], ["t1"], ["t1", "t2"]]


def test_an_answer_older_than_its_time_is_read_again(
    context: PluginContext, reads: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RemoteStore(context)
    answers = AvailabilityAnswers(ttl_s=2.0)
    clock = [100.0]
    monkeypatch.setattr(availability_module.time, "monotonic", lambda: clock[0])
    availability_of(context, store, ["t1"], answers)
    clock[0] += 1.9
    availability_of(context, store, ["t1"], answers)
    clock[0] += 0.2
    availability_of(context, store, ["t1"], answers)
    assert reads == [["t1"], ["t1"]]


def test_the_plugin_hands_every_part_the_context_that_forgets_the_answers(
    context: PluginContext,
) -> None:
    told: list[Sequence[str] | None] = []
    service = RemoteService(dataclasses.replace(context, availability_changed=told.append))
    try:
        answers = service._answers
        answers.keep({"t1": "remote"})
        service._context.availability_changed(["t1"])
        assert told == [["t1"]]
        assert answers.split(["t1"]) == ({}, ["t1"])
    finally:
        service.unload()

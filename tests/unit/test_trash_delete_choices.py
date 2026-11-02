"""The choices a plugin adds to the Recycle Bin confirmation (plan 125.4), at the model.

The source of the choices is a fake of ``DeleteChoiceSource``; the library, the journal and the
file access are the real ones of ``test_trash_model`` and the Shell is its fake. What matters
here: the confirmation of the core is the same without a plugin and when a plugin fails, the
default button follows the rule of the UX review, a choice runs on a job thread and reports
a readable result, and no choice ever moves a file by itself.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any, cast

from PySide6.QtCore import QObject
from tests.unit import test_trash_model as _trash_tests
from tests.unit.test_trash_model import _Env, _results, _statuses

from mtee.domain.jobs import JobState
from mtee.models.trash_model import TrashModel
from mtee.services.jobs import JobContext

env = _trash_tests.env  # the fixture of test_trash_model, found by pytest under this name


def _choice(
    key: str,
    label: str,
    *,
    tone: str = "normal",
    replaces: bool = False,
    description: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "description": description,
        "tone": tone,
        "replaces": replaces,
    }


def _group(plugin: str, *choices: dict[str, Any]) -> dict[str, Any]:
    return {"plugin": plugin, "pluginId": plugin.lower(), "choices": list(choices)}


class _Source:
    """A ``DeleteChoiceSource`` that records what the model asks of it."""

    def __init__(self, *groups: dict[str, Any]) -> None:
        self.groups = list(groups)
        self.offered: list[list[str]] = []
        self.runs: list[tuple[str, list[str], int]] = []
        self.error: Exception | None = None
        self.offer_error: Exception | None = None
        self.answer = "Done on the server."
        self.gate: threading.Event | None = None

    def delete_choices(self, track_ids: Sequence[str]) -> list[dict[str, Any]]:
        self.offered.append(list(track_ids))
        if self.offer_error is not None:
            raise self.offer_error
        return [{**group, "choices": [dict(c) for c in group["choices"]]} for group in self.groups]

    def run_delete_choice(self, key: str, track_ids: Sequence[str], job: JobContext) -> str:
        self.runs.append((key, list(track_ids), threading.get_ident()))
        if self.gate is not None:
            while not job.is_cancelled:
                if self.gate.wait(0.01):
                    break
            job.raise_if_cancelled()
        if self.error is not None:
            raise self.error
        return self.answer


class _ReadableError(Exception):
    readable = True


def _model(env: _Env, source: _Source | None) -> TrashModel:
    model = env.make_model()
    if source is not None:
        model.attach_delete_choices(source)
    return model


def _buttons(model: TrashModel) -> list[tuple[str, str]]:
    return [(b["label"], b["kind"]) for b in cast(list[dict[str, Any]], model.choiceButtons)]


# --- without a plugin: the confirmation of the core, unchanged -------------------------------


def test_without_a_source_there_is_nothing_to_choose_and_the_core_button_stays(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = _model(env, None)

    env.prepare(model, [track])

    assert model.state == "confirm"
    assert model.choiceGroups == [] and model.choiceButtons == []
    assert model.replacesRecycle is False
    model.confirm()
    env.wait(lambda: model.state == "result")
    assert _statuses(model) == ["recycled"] and len(env.service.calls) == 1


def test_a_source_with_nothing_to_offer_changes_nothing(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source()
    model = _model(env, source)

    env.prepare(model, [track])

    assert source.offered == [[track]]  # asked once, with the selection
    assert model.choiceGroups == [] and model.choiceButtons == []
    assert model.replacesRecycle is False


def test_a_source_that_fails_leaves_the_core_action_working(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Remote", _choice("remote.x", "Remote: x")))
    source.offer_error = RuntimeError("the plugin is broken")
    model = _model(env, source)

    env.prepare(model, [track])

    assert model.state == "confirm" and model.choiceGroups == []
    assert model.replacesRecycle is False
    model.confirm()
    env.wait(lambda: model.state == "result")
    assert _statuses(model) == ["recycled"]  # the file went to the (fake) Recycle Bin as usual
    assert not (env.music / "a.wav").exists()


# --- what is offered, and which button is the default ----------------------------------------


def test_a_choice_that_does_not_replace_sits_next_to_the_core_button(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(
        _group("Sample", _choice("sample.log", "Log only", description="Writes a line.")),
    )
    model = _model(env, source)

    env.prepare(model, [track])

    assert model.replacesRecycle is False  # the core button stays, and stays the default
    assert _buttons(model) == [("Log only", "neutral")]
    groups = cast(list[dict[str, Any]], model.choiceGroups)
    assert groups[0]["plugin"] == "Sample"
    assert groups[0]["choices"][0]["description"] == "Writes a line."


def test_a_replacing_choice_takes_the_place_of_the_core_button(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(
        _group(
            "Remote",
            _choice("remote.everywhere", "Delete everywhere", tone="danger", replaces=True),
            _choice("remote.local", "Remove from this computer", replaces=True),
        ),
    )
    model = _model(env, source)

    env.prepare(model, [track])

    assert model.replacesRecycle is True
    # The plugin's primary choice is the default (first); the danger one comes after it.
    assert _buttons(model) == [
        ("Remove from this computer", "primary"),
        ("Delete everywhere", "danger"),
    ]


def test_a_danger_choice_is_never_the_default_button(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(
        _group("Remote", _choice("remote.all", "Delete everywhere", tone="danger", replaces=True))
    )
    model = _model(env, source)

    env.prepare(model, [track])

    assert model.replacesRecycle is True
    assert _buttons(model) == [("Delete everywhere", "danger")]


def test_the_choices_of_two_plugins_are_two_groups_and_one_replacing_hides_the_core_button(
    env: _Env,
) -> None:
    track = env.add_track("a.wav")
    source = _Source(
        _group("Alpha", _choice("alpha.a", "Alpha a")),
        _group("Beta", _choice("beta.b", "Beta b", replaces=True)),
    )
    model = _model(env, source)

    env.prepare(model, [track])

    groups = cast(list[dict[str, Any]], model.choiceGroups)
    assert [group["plugin"] for group in groups] == ["Alpha", "Beta"]
    assert model.replacesRecycle is True
    assert _buttons(model) == [("Beta b", "primary"), ("Alpha a", "neutral")]


def test_choices_exist_only_while_the_confirmation_is_open(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Sample", _choice("sample.log", "Log only")))
    model = _model(env, source)
    assert model.choiceGroups == []  # idle

    env.prepare(model, [track])
    assert model.choiceGroups != []
    model.confirm()
    env.wait(lambda: model.state == "result")

    assert model.choiceGroups == [] and model.choiceButtons == []
    assert model.replacesRecycle is False


# --- running a choice -------------------------------------------------------------------------


def test_a_choice_runs_on_a_job_thread_with_the_selected_ids_and_moves_no_file(
    env: _Env,
) -> None:
    first, second = env.add_track("a.wav"), env.add_track("b.wav")
    source = _Source(_group("Sample", _choice("sample.log", "Log only")))
    model = _model(env, source)
    env.prepare(model, [first, second, first])

    model.run_choice("sample.log")

    assert model.state == "running" and model.canCancel
    env.wait(lambda: model.state == "result")
    env.settle()
    assert source.runs == [("sample.log", [first, second], source.runs[0][2])]
    assert source.runs[0][2] != threading.get_ident()  # not the graphical thread
    assert _statuses(model) == ["done"]
    assert _results(model)[0]["source"] == "Sample: Log only"
    assert model.message == "Done on the server."
    assert not model.canCancel
    # The core action was not run: nothing recycled, nothing journaled, both files in place.
    assert env.service.calls == [] and env.journal_rows() == []
    assert (env.music / "a.wav").is_file() and (env.music / "b.wav").is_file()
    assert env.job_status("Sample: Log only").state is JobState.SUCCEEDED


def test_a_readable_error_is_shown_as_its_message_and_the_job_fails(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Remote", _choice("remote.x", "Remote: x")))
    source.error = _ReadableError("The server is not reachable. Check the address in Settings.")
    model = _model(env, source)
    env.prepare(model, [track])

    model.run_choice("remote.x")
    env.wait(lambda: model.state == "result")
    env.settle()

    assert _statuses(model) == ["failed"]
    assert _results(model)[0]["message"] == (
        "The server is not reachable. Check the address in Settings."
    )
    assert model.message == "Remote: Remote: x did not complete."
    assert env.job_status("Remote: Remote: x").state is JobState.FAILED


def test_any_other_error_is_shown_with_its_class_like_in_tasks(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Remote", _choice("remote.x", "Remote: x")))
    source.error = RuntimeError("boom")
    model = _model(env, source)
    env.prepare(model, [track])

    model.run_choice("remote.x")
    env.wait(lambda: model.state == "result")

    assert _results(model)[0]["message"] == "RuntimeError: boom"


def test_the_core_recycle_still_works_after_a_choice_failed(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Remote", _choice("remote.x", "Remote: x")))
    source.error = RuntimeError("boom")
    model = _model(env, source)
    env.prepare(model, [track])
    model.run_choice("remote.x")
    env.wait(lambda: model.state == "result")

    env.run_to_result(model, [track])  # asks again, the user confirms the Recycle Bin

    assert _statuses(model) == ["recycled"]
    assert not (env.music / "a.wav").exists()


def test_a_choice_can_be_cancelled_and_says_so(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Remote", _choice("remote.x", "Remote: x")))
    source.gate = threading.Event()  # the run waits until the job is cancelled
    model = _model(env, source)
    env.prepare(model, [track])
    model.run_choice("remote.x")
    env.wait(lambda: bool(source.runs))

    model.cancel()
    env.wait(lambda: model.state == "result")

    assert _results(model)[0]["message"] == "Cancelled."
    assert _statuses(model) == ["failed"]


def test_an_unknown_choice_or_a_wrong_moment_runs_nothing(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Sample", _choice("sample.log", "Log only")))
    model = _model(env, source)

    model.run_choice("sample.log")  # idle: no confirmation is open
    assert model.state == "idle"
    env.prepare(model, [track])
    model.run_choice("sample.other")  # not offered
    model.run_choice("")
    env.settle()

    assert model.state == "confirm" and source.runs == []


def test_a_choice_without_a_source_does_nothing(env: _Env) -> None:
    track = env.add_track("a.wav")
    model = _model(env, None)
    env.prepare(model, [track])

    model.run_choice("sample.log")

    assert model.state == "confirm"


def test_a_choice_asked_during_shutdown_ends_in_a_result_message(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Sample", _choice("sample.log", "Log only")))
    model = _model(env, source)
    env.prepare(model, [track])
    env.jobs.begin_shutdown()

    model.run_choice("sample.log")

    assert model.state == "result" and "shutting down" in str(model.message)
    assert source.runs == []


def test_qml_reads_the_new_properties_through_qt(env: _Env) -> None:
    track = env.add_track("a.wav")
    source = _Source(_group("Sample", _choice("sample.log", "Log only")))
    model = _model(env, source)
    env.prepare(model, [track])

    qml_view = cast(QObject, model)  # what the dialog reads: Qt properties by name
    assert qml_view.property("replacesRecycle") is False
    assert len(qml_view.property("choiceGroups")) == 1
    assert [button["key"] for button in qml_view.property("choiceButtons")] == ["sample.log"]

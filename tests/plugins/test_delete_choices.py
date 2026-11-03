"""The ``DeleteChoices`` contribution through the core (plan 125.4), without a window.

The sample plugin offers one choice that does not replace the core action. Small plugins
written into a temporary folder cover what the sample does not: two plugins at once, a plugin
whose ``offer`` or ``run`` fails, and a plugin that declares the contribution twice. The
confirmation itself is the real ``TrashModel`` of the core, over the real library and the fake
Shell of ``tests/unit/test_trash_model.py``.
"""

from __future__ import annotations

import sys
import textwrap
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from tests.plugins import test_contract as _contract
from tests.plugins.test_contract import SAMPLE, Harness
from tests.unit import test_trash_model as _trash_tests
from tests.unit.test_trash_model import _Env, _results, _statuses

from mtee.domain.recycling import RecycleOutcome
from mtee.domain.source_tracks import SourceTrack
from mtee.models.plugin_ui_model import PluginUiModel
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.api import DeleteRequest
from mtee.plugins.loader import LoadedPlugin, PluginStatus

# The fixtures of the other test modules, under their own names (pytest finds them here).
harness = _contract.harness
env = _trash_tests.env

_PLUGIN = """
from mtee.plugins.api import DeleteChoice, DeleteChoices

RUNS = []


class Service:
    def contributions(self):
        return [DeleteChoices(self._offer, self._run)]

    def _offer(self, ids):
{offer}

    def _run(self, request):
{run}

    def unload(self):
        pass


def create(context):
    return Service()
"""

_TWICE = """
from mtee.plugins.api import DeleteChoices


class Service:
    def contributions(self):
        return [DeleteChoices(lambda ids: [], lambda *a: None),
                DeleteChoices(lambda ids: [], lambda *a: None)]

    def unload(self):
        pass


def create(context):
    return Service()
"""


# The body of a run that recycles its selection: one refused id, then the whole selection.
_RECYCLE_RUN = """
refused = ""
try:
    request.recycle(["not-selected"])
except ValueError as error:
    refused = str(error)
outcome = request.recycle(request.track_ids)
return f"{refused} | {len(outcome.recycled)} recycled | {len(outcome.failed)} failed"
"""


def _no_recycle(track_ids: Sequence[str]) -> RecycleOutcome:
    raise AssertionError(f"this choice must not recycle {list(track_ids)}")


def _write_plugin(folder: Path, plugin_id: str, title: str, source: str) -> None:
    package = folder / plugin_id
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(source, encoding="utf-8")
    (package / "manifest.py").write_text(
        textwrap.dedent(
            f"""
            from mtee.plugins.api import PluginManifest

            MANIFEST = PluginManifest(
                plugin_id="{plugin_id}", title="{title}", description="", version="1",
                api_version=1, factory="mtee.plugins.{plugin_id}:create",
            )
            """
        ),
        encoding="utf-8",
    )


def _delete_plugin(offer: str, run: str) -> str:
    indent = textwrap.indent
    return _PLUGIN.format(
        offer=indent(textwrap.dedent(offer).strip(), " " * 8),
        run=indent(textwrap.dedent(run).strip(), " " * 8),
    )


def _start(harness: Harness, folder: Path, *plugin_ids: str) -> dict[str, LoadedPlugin]:
    return harness.start(folder, *plugin_ids)


def _sample_module() -> Any:
    return sys.modules[f"mtee.plugins.{SAMPLE.plugin_id}"]


# --- what the sample offers -------------------------------------------------------------------


def test_the_sample_offers_one_choice_that_does_not_replace_the_core_action(
    harness: Harness,
) -> None:
    record = harness.start(harness.stage(SAMPLE), SAMPLE.plugin_id)[SAMPLE.plugin_id]
    shown = PluginUiModel()
    shown.register([record])
    events = _sample_module().EVENTS
    events.clear()

    groups = shown.delete_choices(["t1", "t2"])

    assert events == ["delete offered t1,t2"]  # the plugin saw the selection
    assert groups == [
        {
            "plugin": "Sample plugin",
            "pluginId": "sample",
            "choices": [
                {
                    "key": "sample.log_only",
                    "label": "Sample: log only",
                    "description": "Records the selection in the sample log. "
                    "No file is moved or changed.",
                    "tone": "normal",
                    "replaces": False,
                }
            ],
        }
    ]


def test_a_plugin_that_is_off_offers_nothing(harness: Harness) -> None:
    folder = harness.stage(SAMPLE)
    harness.preferences.set_enabled(SAMPLE.plugin_id, False)
    record = harness.start(folder)[SAMPLE.plugin_id]
    shown = PluginUiModel()
    shown.register([record])

    assert shown.delete_choices(["t1"]) == []


def test_the_sample_choice_runs_off_the_graphical_thread_with_the_selected_ids(
    harness: Harness,
    env: _Env,
) -> None:
    record = harness.start(harness.stage(SAMPLE), SAMPLE.plugin_id)[SAMPLE.plugin_id]
    shown = PluginUiModel()
    shown.register([record])
    first, second = env.add_track("a.wav"), env.add_track("b.wav")
    model = env.make_model()
    model.attach_delete_choices(shown)
    runs = _sample_module().DELETE_RUNS
    runs.clear()

    env.prepare(model, [first, second])
    assert [button["label"] for button in cast(list[dict[str, Any]], model.choiceButtons)] == [
        "Sample: log only"
    ]
    model.run_choice("sample.log_only")
    env.wait(lambda: model.state == "result")
    env.settle()

    assert [(choice, ids) for choice, ids, _thread in runs] == [("log_only", (first, second))]
    assert runs[0][2] != threading.get_ident()
    assert _statuses(model) == ["done"] and model.message == "Logged 2 track(s)."
    assert env.service.calls == [] and (env.music / "a.wav").is_file()  # nothing was recycled


# --- other plugins ----------------------------------------------------------------------------


_ONE_CHOICE = """
return [DeleteChoice("{cid}", "{label}", "{label} does it.", {extra})]
"""


def _offering(cid: str, label: str, extra: str = "") -> str:
    return _ONE_CHOICE.format(cid=cid, label=label, extra=extra)


def test_two_plugins_are_two_groups_in_the_order_of_their_registration(
    harness: Harness,
    tmp_path: Path,
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    _write_plugin(
        folder,
        "delete_alpha",
        "Alpha plugin",
        _delete_plugin(_offering("a", "Alpha a"), "return 'alpha ran'"),
    )
    _write_plugin(
        folder,
        "delete_beta",
        "Beta plugin",
        _delete_plugin(
            _offering("b", "Beta b", 'tone="danger", replaces_recycle=True'),
            "return None",
        ),
    )
    records = _start(harness, folder, "delete_alpha", "delete_beta")
    shown = PluginUiModel()
    shown.register([records["delete_alpha"], records["delete_beta"]])

    groups = shown.delete_choices(["t1"])

    assert [(g["plugin"], [c["key"] for c in g["choices"]]) for g in groups] == [
        ("Alpha plugin", ["delete_alpha.a"]),
        ("Beta plugin", ["delete_beta.b"]),
    ]
    beta = groups[1]["choices"][0]
    assert beta["tone"] == "danger" and beta["replaces"] is True
    assert groups[0]["choices"][0]["tone"] == "normal"
    # A sentence from the plugin is the result; none gives the default "Done.".
    job = MagicMock()
    assert shown.run_delete_choice("delete_alpha.a", ["t1"], job, _no_recycle) == "alpha ran"
    assert shown.run_delete_choice("delete_beta.b", ["t1"], job, _no_recycle) == "Done."


def test_unusable_choices_are_left_out_and_a_plugin_with_none_has_no_group(
    harness: Harness,
    tmp_path: Path,
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    _write_plugin(
        folder,
        "delete_messy",
        "Messy plugin",
        _delete_plugin(
            """
            return [DeleteChoice("", "No id"), DeleteChoice("x", "  "), "junk",
                    DeleteChoice("ok", "Fine", tone="loud"), DeleteChoice("ok", "Again")]
            """,
            "return None",
        ),
    )
    _write_plugin(
        folder, "delete_quiet", "Quiet plugin", _delete_plugin("return []", "return None")
    )
    records = _start(harness, folder, "delete_messy", "delete_quiet")
    shown = PluginUiModel()
    shown.register(list(records.values()))

    groups = shown.delete_choices(["t1"])

    assert [g["plugin"] for g in groups] == ["Messy plugin"]
    assert [(c["key"], c["label"], c["tone"]) for c in groups[0]["choices"]] == [
        ("delete_messy.ok", "Fine", "normal")  # an unknown tone is a normal one; no duplicates
    ]


def test_a_plugin_whose_offer_crashes_is_announced_once_and_never_blocks_the_core_action(
    harness: Harness,
    tmp_path: Path,
    env: _Env,
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    _write_plugin(
        folder,
        "delete_crash",
        "Crashing plugin",
        _delete_plugin("raise RuntimeError('offer exploded')", "return None"),
    )
    records = _start(harness, folder, "delete_crash")
    shown = PluginUiModel()
    notices: list[str] = []
    shown.noticeRaised.connect(notices.append)
    shown.register([records["delete_crash"]])
    track = env.add_track("a.wav")
    model = env.make_model()
    model.attach_delete_choices(shown)

    env.prepare(model, [track])
    assert model.state == "confirm"
    assert model.choiceGroups == [] and model.replacesRecycle is False
    model.confirm()  # the usual Recycle Bin action
    env.wait(lambda: model.state == "result")
    env.run_to_result(model, [env.add_track("b.wav")])  # a second time: still one notice

    assert _statuses(model) == ["recycled"]
    assert len(env.service.calls) == 2
    assert len(notices) == 1
    assert "Crashing plugin" in notices[0] and "offer exploded" in notices[0]


def test_a_plugin_whose_run_crashes_shows_the_error_and_the_core_action_still_works(
    harness: Harness,
    tmp_path: Path,
    env: _Env,
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    _write_plugin(
        folder,
        "delete_fail",
        "Failing plugin",
        _delete_plugin(_offering("go", "Go"), "raise ValueError('no server today')"),
    )
    records = _start(harness, folder, "delete_fail")
    shown = PluginUiModel()
    shown.register([records["delete_fail"]])
    track = env.add_track("a.wav")
    model = env.make_model()
    model.attach_delete_choices(shown)
    env.prepare(model, [track])

    model.run_choice("delete_fail.go")
    env.wait(lambda: model.state == "result")

    assert _statuses(model) == ["failed"]
    assert _results(model)[0]["message"] == "ValueError: no server today"
    assert (env.music / "a.wav").is_file()
    env.run_to_result(model, [track])
    assert _statuses(model) == ["recycled"]


def test_a_choice_of_a_plugin_that_is_gone_is_refused_with_a_readable_error() -> None:
    shown = PluginUiModel()

    with pytest.raises(LookupError, match="no longer running"):
        shown.run_delete_choice("gone.x", ["t1"], MagicMock(), _no_recycle)


def test_declaring_delete_choices_twice_fails_only_that_plugin(
    harness: Harness,
    tmp_path: Path,
) -> None:
    folder = harness.stage(SAMPLE)
    _write_plugin(folder, "delete_twice", "Twice plugin", _TWICE)

    records = _start(harness, folder, SAMPLE.plugin_id, "delete_twice")

    assert records[SAMPLE.plugin_id].status is PluginStatus.RUNNING
    assert records["delete_twice"].status is PluginStatus.FAILED
    assert "declares it twice" in records["delete_twice"].error


# --- request.recycle and a selection without local files --------------------------------------


def test_a_request_refuses_a_track_outside_its_selection() -> None:
    asked: list[tuple[str, ...]] = []

    def recycle(track_ids: Sequence[str]) -> RecycleOutcome:
        asked.append(tuple(track_ids))
        return RecycleOutcome(recycled=tuple(track_ids))

    request = DeleteRequest("local", ("t1",), MagicMock(), recycle)

    with pytest.raises(ValueError, match="t2"):
        request.recycle(["t1", "t2"])
    assert asked == []  # a refused request recycles nothing
    assert request.recycle(["t1", "t1"]) == RecycleOutcome(recycled=("t1",))
    assert asked == [("t1",)]  # a repeated identifier is asked once


def test_a_choice_recycles_its_selection_through_the_core_and_opens_no_second_dialog(
    harness: Harness,
    tmp_path: Path,
    env: _Env,
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    _write_plugin(
        folder,
        "delete_recycle",
        "Recycle plugin",
        _delete_plugin(_offering("local", "Remove here", "replaces_recycle=True"), _RECYCLE_RUN),
    )
    records = _start(harness, folder, "delete_recycle")
    shown = PluginUiModel()
    shown.register([records["delete_recycle"]])
    first, second = env.add_track("a.wav"), env.add_track("b.wav")
    model = env.make_model()
    model.attach_delete_choices(shown)
    env.prepare(model, [first, second])
    dialogs: list[int] = []
    model.dialogRequested.connect(lambda: dialogs.append(1))

    model.run_choice("delete_recycle.local")
    env.wait(lambda: model.state == "result")
    env.settle()

    assert model.message == (
        "These tracks are not part of this delete choice: not-selected | 2 recycled | 0 failed"
    )
    assert dialogs == []  # the user confirmed the selection already
    assert env.service.calls == [env.music / "a.wav", env.music / "b.wav"]
    assert [(row[0], row[1]) for row in env.journal_rows()] == [
        (first, "recycled"),
        (second, "recycled"),
    ]
    assert _statuses(model) == ["done"]


def test_a_selection_of_plugin_tracks_opens_with_the_plugin_choices_only(
    harness: Harness,
    env: _Env,
) -> None:
    record = harness.start(harness.stage(SAMPLE), SAMPLE.plugin_id)[SAMPLE.plugin_id]
    shown = PluginUiModel()
    shown.register([record])
    identities, _changed = SourceTrackRepository(env.database).upsert(
        SAMPLE.plugin_id,
        [
            SourceTrack(
                "provided",
                "Provided by the sample",
                artists=("Ann",),
                album="Album",
                duration_us=2_000_000,
            )
        ],
    )
    provided = identities["provided"]
    model = env.make_model()
    model.attach_delete_choices(shown)
    runs = _sample_module().DELETE_RUNS
    runs.clear()

    env.prepare(model, [provided])  # no local file: the core button is not offered

    assert model.state == "confirm" and model.hasLocalFiles is False
    assert model.replacesRecycle is True
    buttons = cast(list[dict[str, Any]], model.choiceButtons)
    assert [button["label"] for button in buttons] == ["Sample: log only"]
    model.run_choice("sample.log_only")
    env.wait(lambda: model.state == "result")
    env.settle()

    assert [(choice, ids) for choice, ids, _thread in runs] == [("log_only", (provided,))]
    assert model.message == "Logged 1 track(s)."
    assert env.service.calls == []

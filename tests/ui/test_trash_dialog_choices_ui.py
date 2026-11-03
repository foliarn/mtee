"""The Recycle Bin confirmation with the choices of a plugin, in the real window (plan 125.4).

Offscreen, like ``test_sample_ui.py``: the real ``Main.qml``, a folder of tiny WAV tracks, and
``TrashDialog`` opened by the trash model as the Delete key does. The dialog without any plugin
is the reference: its texts, its single action button and its height must not change.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickItem, QQuickWindow
from tests.helpers.ui_plugin import (
    click,
    find_items,
    plugin_module,
    settle,
    start_app,
    window_of,
    workspace_of,
)
from tests.plugins.sample.track_source import SOURCE_KEY
from tests.plugins.test_contract import SAMPLE
from tests.ui.track_list_fixtures import add_folder_tracks

from mtee.app import _Runtime, _shutdown
from mtee.domain.recycling import RecycleOutcome
from mtee.models.trash_model import TrashModel
from mtee.services.jobs import JobContext

# The dialog without a plugin is this tall (TrashDialog.qml) and has one action button.
_PLAIN_HEIGHT = 510


def _trash(runtime: _Runtime) -> TrashModel:
    return cast(TrashModel, cast(Any, workspace_of(runtime)).trashModel)


def _open_confirmation(runtime: _Runtime, track_ids: list[str]) -> QQuickWindow:
    window = window_of(runtime)
    _trash(runtime).request_recycle(track_ids)
    settle(runtime)
    assert _trash(runtime).state == "confirm"
    return window


def _dialog_height(window: QQuickWindow) -> float:
    dialog = window.findChild(QObject, "trashDialog")
    assert dialog is not None, "the Recycle Bin dialog is not in the window"
    return float(dialog.property("height"))


def _dialog_texts(window: QQuickWindow) -> list[str]:
    """The visible texts inside the dialog (its buttons included), not those of the window."""
    dialog = window.findChild(QObject, "trashDialog")
    assert dialog is not None
    pending = [cast(QQuickItem, dialog.property("contentItem"))]
    found: list[str] = []
    while pending:
        item = pending.pop()
        text = item.property("text")
        if isinstance(text, str) and item.isVisible():
            found.append(text)
        pending.extend(item.childItems())
    return found


def _shown(window: QQuickWindow, name: str) -> list[QQuickItem]:
    return [item for item in find_items(window, name) if item.isVisible()]


class _Source:
    """Choices of two invented plugins, as ``PluginUiModel`` would hand them over."""

    def __init__(self) -> None:
        self.runs: list[tuple[str, int]] = []

    def delete_choices(self, track_ids: Sequence[str]) -> list[dict[str, Any]]:
        def choice(key: str, label: str, tone: str, replaces: bool) -> dict[str, Any]:
            return {
                "key": key,
                "label": label,
                "description": f"{label} does something.",
                "tone": tone,
                "replaces": replaces,
            }

        return [
            {
                "plugin": "Alpha plugin",
                "pluginId": "alpha",
                "choices": [choice("alpha.safe", "Remove here", "normal", True)],
            },
            {
                "plugin": "Beta plugin",
                "pluginId": "beta",
                "choices": [choice("beta.all", "Delete everywhere", "danger", True)],
            },
        ]

    def run_delete_choice(
        self,
        key: str,
        track_ids: Sequence[str],
        job: JobContext,
        recycle: Callable[[Sequence[str]], RecycleOutcome],
    ) -> str:
        self.runs.append((key, threading.get_ident()))
        return "Done."


def test_without_a_plugin_the_dialog_is_the_one_of_the_core(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        _root, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 2)
        window = _open_confirmation(runtime, track_ids[:1])

        texts = _dialog_texts(window)
        # A TextButton and its label both have a text: one button is two entries.
        assert texts.count("Move to Recycle Bin") == 2
        assert "Move 1 selected audio file(s) to the Windows Recycle Bin?" in texts
        assert _shown(window, "trashChoices") == []
        assert _shown(window, "trashChoiceCard") == []
        assert _shown(window, "trashChoiceHeading") == []
        assert _dialog_height(window) == _PLAIN_HEIGHT
        assert _trash(runtime).choiceButtons == [] and not _trash(runtime).replacesRecycle
    finally:
        _shutdown(runtime)


def test_the_sample_choice_is_drawn_next_to_the_core_button_and_runs(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data", (SAMPLE.folder,), (SAMPLE.plugin_id,))
    try:
        _root, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 2)
        window = _open_confirmation(runtime, track_ids[:1])
        module = plugin_module(SAMPLE.plugin_id)
        assert module is not None

        texts = _dialog_texts(window)
        assert texts.count("Move to Recycle Bin") == 2  # the core button stays, as the default
        assert len(_shown(window, "trashChoices")) == 1
        heading = _shown(window, "trashChoiceHeading")
        assert [item.property("text") for item in heading] == ["Sample plugin"]
        assert "Sample: log only" in texts
        assert "Records the selection in the sample log. No file is moved or changed." in texts
        assert _dialog_height(window) >= _PLAIN_HEIGHT
        [button] = _shown(window, "trashChoice_sample.log_only")
        assert button.property("kind") == "neutral"

        click(window, button)
        settle(runtime)

        assert [(choice, ids) for choice, ids, _thread in module.DELETE_RUNS] == [
            ("log_only", (track_ids[0],))
        ]
        assert module.DELETE_RUNS[0][2] != threading.get_ident()
        assert _trash(runtime).state == "result"
        texts = _dialog_texts(window)
        assert "Logged 1 track(s)." in texts and "DONE  Sample plugin: Sample: log only" in texts
        assert Path(tmp_path / "audio" / "track-000.wav").is_file()  # nothing was recycled
    finally:
        _shutdown(runtime)


def test_a_replacing_choice_takes_the_core_button_and_a_danger_choice_is_red(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        _root, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 1)
        source = _Source()
        _trash(runtime).attach_delete_choices(source)
        window = _open_confirmation(runtime, track_ids)

        texts = _dialog_texts(window)
        assert "Move to Recycle Bin" not in texts  # the button is replaced
        headings = [item.property("text") for item in _shown(window, "trashChoiceHeading")]
        assert sorted(headings) == ["Alpha plugin", "Beta plugin"]  # one small heading each
        assert len(_shown(window, "trashChoiceCard")) == 2
        # The plugin's primary choice is the default button (lime), the danger one is red.
        safe = _shown(window, "trashChoice_alpha.safe")
        assert len(safe) == 1 and safe[0].property("kind") == "primary"
        danger = _shown(window, "trashChoice_beta.all")
        assert len(danger) == 1 and danger[0].property("text") == "Delete everywhere"
        assert danger[0].property("color").name().lower() == "#ff4d4d"  # Theme.danger
        # The danger button is farther from the default one, which is the rightmost.
        assert danger[0].mapToScene(danger[0].position()).x() < (
            safe[0].mapToScene(safe[0].position()).x()
        )
        assert _dialog_height(window) >= _PLAIN_HEIGHT

        click(window, safe[0])
        settle(runtime)

        assert [key for key, _thread in source.runs] == ["alpha.safe"]
        assert _trash(runtime).state == "result"
        assert Path(tmp_path / "audio" / "track-000.wav").is_file()  # no choice moved the file
    finally:
        _shutdown(runtime)


def test_cancel_closes_the_confirmation_and_runs_nothing(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        _root, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 1)
        window = _open_confirmation(runtime, track_ids)
        dialog = window.findChild(QObject, "trashDialog")
        assert dialog is not None
        [cancel] = _shown(window, "trashCancel")
        assert cancel.property("text") == "Cancel"

        click(window, cancel)
        settle(runtime)

        assert dialog.property("visible") is False  # closed, as Escape closes it
        assert _trash(runtime).state == "confirm" and _trash(runtime).results == []
        assert Path(tmp_path / "audio" / "track-000.wav").is_file()  # nothing was recycled
    finally:
        _shutdown(runtime)


def test_a_track_without_a_file_is_named_by_its_title_not_its_identifier(
    qapp, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (SAMPLE.folder,), (SAMPLE.plugin_id,))
    try:
        records = cast(Any, runtime.plugins).plugins
        record = next(item for item in records if item.plugin_id == SAMPLE.plugin_id)
        served = cast(Any, record.service).provide_tracks(b"not really audio", 3_000_000)
        track_id = served[SOURCE_KEY]
        window = window_of(runtime)

        _trash(runtime).request_recycle([track_id])
        settle(runtime)

        # The sample's track has no file: the row names it by artist and title, never by its id.
        [result] = cast(list[dict[str, Any]], _trash(runtime).results)
        assert result["status"] == "conflict"
        assert result["source"] == "Sample artist - Served over HTTP"
        texts = _dialog_texts(window)
        assert "CONFLICT  Sample artist - Served over HTTP" in texts
        assert not any(track_id in text for text in texts)
    finally:
        _shutdown(runtime)


def test_the_recycle_bin_dialog_is_centred_over_the_window(qapp, tmp_path: Path) -> None:
    runtime = start_app(tmp_path / "data")
    try:
        _root, track_ids = add_folder_tracks(runtime, tmp_path / "audio", 1)
        window = _open_confirmation(runtime, track_ids)
        dialog = window.findChild(QObject, "trashDialog")
        assert dialog is not None
        x, y = float(dialog.property("x")), float(dialog.property("y"))
        width, height = float(dialog.property("width")), float(dialog.property("height"))

        # Centred like the other dialogs of the core, not on the 0 x 0 loader at the corner.
        assert abs(x + width / 2 - window.width() / 2) <= 1
        assert abs(y + height / 2 - window.height() / 2) <= 1
    finally:
        _shutdown(runtime)

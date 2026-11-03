"""The status bar item of a plugin (plan 125.5), through the real host and the core model.

The sample declares one item and shows "Sample: ready". Small plugins written into a temporary
folder cover the rest: the items in plugin load order, a change made from a worker thread, a
click that fails, and the checks that refuse a bad declaration or a bad value. The model is the
real ``StatusBarModel``; the services of the host are mocks, as in the contract tests.
"""

from __future__ import annotations

import sys
import textwrap
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QCoreApplication
from tests.plugins.test_contract import SAMPLE

from mtee.models.status_bar_model import StatusBarModel, make_status_state
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import StatusItem
from mtee.plugins.context import PluginHost
from mtee.plugins.contributions import check_contributions
from mtee.plugins.loader import LoadedPlugin, PluginManager, PluginPreferences, PluginStatus


class Env:
    """A host with the status bar of the window, over a temporary database."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "mtee.sqlite3")
        self.database.migrate()
        self.preferences = PluginPreferences(SettingsRepository(self.database))
        self.manager = PluginManager(self.preferences, notify=lambda text: None)
        self.host = PluginHost(
            data_dir=base,
            database=self.database,
            settings=SettingsRepository(self.database),
            library=MagicMock(),
            playlists=MagicMock(),
            jobs=MagicMock(),
            file_moves=MagicMock(),
            recycle=MagicMock(),
            roots=MagicMock(),
            refresh_playlists=lambda: None,
        )
        self.bar = StatusBarModel()
        self.host.attach_status_bar(self.bar)
        self.notices: list[str] = []
        self.bar.noticeRaised.connect(self.notices.append)

    def load(self, folder: Path, *plugin_ids: str) -> list[LoadedPlugin]:
        """Enable ``plugin_ids``, load them from ``folder`` and show their items."""
        for plugin_id in plugin_ids:
            self.preferences.set_enabled(plugin_id, True)
        records = self.manager.load_enabled(self.host.context_for, [folder])
        self.bar.register(records)
        return records

    def close(self) -> None:
        self.manager.unload_all()


@pytest.fixture
def env(qapp, tmp_path: Path) -> Any:
    created = Env(tmp_path)
    yield created
    created.close()


def _write_plugin(folder: Path, plugin_id: str, source: str) -> None:
    package = folder / plugin_id
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(source, encoding="utf-8")
    (package / "manifest.py").write_text(
        textwrap.dedent(
            f"""
            from mtee.plugins.api import PluginManifest

            MANIFEST = PluginManifest(
                plugin_id="{plugin_id}", title="{plugin_id} title", description="", version="1",
                api_version=1, factory="mtee.plugins.{plugin_id}:create",
            )
            """
        ),
        encoding="utf-8",
    )


def _source(*, click: bool = True, click_fails: bool = False) -> str:
    """A plugin with one status item; its context and its clicks are kept in the module."""
    on_click = "_click" if click else "None"
    failure = 'raise RuntimeError("the click broke")' if click_fails else "pass"
    return textwrap.dedent(
        f"""
        import threading

        from mtee.plugins.api import StatusItem

        CONTEXT = None
        CLICKS = []


        def _click():
            CLICKS.append(threading.get_ident())
            {failure}


        class Service:
            def __init__(self, context):
                self._context = context

            def contributions(self):
                return [StatusItem("status", "cloud", on_click={on_click})]

            def unload(self):
                pass


        def create(context):
            global CONTEXT
            CONTEXT = context
            return Service(context)
        """
    )


def _module(plugin_id: str) -> Any:
    return sys.modules[f"mtee.plugins.{plugin_id}"]


def _rows(bar: StatusBarModel) -> list[dict[str, Any]]:
    """The rows as QML reads them: one dictionary per row, keyed by role name."""
    names = {role: bytes(name.data()).decode() for role, name in bar.roleNames().items()}
    return [
        {names[role]: bar.data(bar.index(row, 0), role) for role in names}
        for row in range(bar.rowCount())
    ]


def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Let the queued calls of the graphical thread run until ``predicate`` holds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


# --- the value a plugin passes -------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"tone": "danger"}, ValueError),
        ({"tone": "primary"}, ValueError),  # not a tone of the contract
        ({"progress": 1.5}, ValueError),
        ({"progress": -0.1}, ValueError),
        ({"progress": float("nan")}, ValueError),
        ({"progress": True}, ValueError),
        ({"tooltip": 3}, TypeError),
        ({"icon": "  "}, ValueError),
    ],
)
def test_a_bad_value_is_refused_before_anything_is_shown(
    kwargs: dict[str, Any], error: type
) -> None:
    with pytest.raises(error):
        make_status_state("Syncing", **kwargs)


def test_a_good_value_keeps_its_parts() -> None:
    state = make_status_state("Syncing 212 of 340", "warning", 1, "Long text", "repeat")
    assert state.text == "Syncing 212 of 340"
    assert state.tone == "warning"
    assert state.progress == 1.0 and isinstance(state.progress, float)
    assert (state.tooltip, state.icon) == ("Long text", "repeat")
    assert make_status_state("Ready").progress is None


# --- the declaration -----------------------------------------------------------------------


def test_the_sample_declares_one_item_and_it_is_shown_at_once(env: Any) -> None:
    records = env.load(SAMPLE.folder, SAMPLE.plugin_id)
    record = next(item for item in records if item.plugin_id == SAMPLE.plugin_id)
    assert record.status is PluginStatus.RUNNING
    items = [item for item in record.contributions if isinstance(item, StatusItem)]
    assert [(item.item_id, item.icon) for item in items] == [("status", "cloud")]
    assert _wait_until(lambda: env.bar.count == 1)
    assert _rows(env.bar)[0]["text"] == "Sample: ready"
    assert _rows(env.bar)[0]["itemId"] == "status"


def test_a_bad_declaration_makes_the_plugin_fail() -> None:
    item = StatusItem("status", "cloud")
    with pytest.raises(ValueError, match="at most one status item"):
        check_contributions("p", [item, StatusItem("second", "cloud")])
    with pytest.raises(ValueError, match="identifier"):
        check_contributions("p", [StatusItem("Status", "cloud")])
    with pytest.raises(ValueError, match="icon"):
        check_contributions("p", [StatusItem("status", "")])
    with pytest.raises(ValueError, match="not callable"):
        check_contributions("p", [StatusItem("status", "cloud", on_click="open")])  # type: ignore[arg-type]
    check_contributions("p", [item])  # the good declaration passes


# --- the item through the context ----------------------------------------------------------


def test_the_item_appears_changes_and_disappears(env: Any, tmp_path: Path) -> None:
    folder = tmp_path / "plugins"
    _write_plugin(folder, "status_one", _source())
    env.load(folder, "status_one")
    context = _module("status_one").CONTEXT
    assert env.bar.count == 0  # nothing is shown until the plugin updates

    context.status_item.update("Syncing 212 of 340", "warning", 0.62, "Server, user", "repeat")
    assert _wait_until(lambda: env.bar.count == 1)
    row = _rows(env.bar)[0]
    assert (row["text"], row["tone"], row["icon"], row["tooltip"]) == (
        "Syncing 212 of 340",
        "warning",
        "repeat",
        "Server, user",
    )
    assert row["progress"] == pytest.approx(0.62) and row["clickable"] is True

    context.status_item.update("Offline")
    assert _wait_until(lambda: _rows(env.bar)[0]["text"] == "Offline")
    row = _rows(env.bar)[0]
    assert row["tone"] == "neutral" and row["progress"] == -1 and row["icon"] == "cloud"
    assert env.bar.count == 1  # the change replaces the row, it does not add one

    context.status_item.clear()
    assert _wait_until(lambda: env.bar.count == 0)


def test_a_bad_value_raises_in_the_plugin_and_shows_nothing(env: Any, tmp_path: Path) -> None:
    folder = tmp_path / "plugins"
    _write_plugin(folder, "status_bad", _source())
    env.load(folder, "status_bad")
    with pytest.raises(ValueError):
        _module("status_bad").CONTEXT.status_item.update("Syncing", "danger")
    QCoreApplication.processEvents()
    assert env.bar.count == 0


def test_an_update_from_a_worker_thread_arrives_on_the_graphical_thread(
    env: Any, tmp_path: Path
) -> None:
    folder = tmp_path / "plugins"
    _write_plugin(folder, "status_thread", _source())
    env.load(folder, "status_thread")
    context = _module("status_thread").CONTEXT
    arrived: list[int] = []
    env.bar.rowsInserted.connect(lambda *_args: arrived.append(threading.get_ident()))
    worker_threads: list[int] = []

    def from_worker() -> None:
        worker_threads.append(threading.get_ident())
        context.status_item.update("From a job")
        context.status_item.update("From a job again", "secondary")

    worker = threading.Thread(target=from_worker)
    worker.start()
    worker.join()
    assert _wait_until(lambda: env.bar.count == 1)
    assert _wait_until(lambda: _rows(env.bar)[0]["text"] == "From a job again")
    assert arrived == [threading.get_ident()]  # the row was inserted on the graphical thread
    assert worker_threads[0] != threading.get_ident()
    assert _rows(env.bar)[0]["tone"] == "secondary"


# --- the click ------------------------------------------------------------------------------


def test_a_click_runs_on_the_graphical_thread(env: Any, tmp_path: Path) -> None:
    folder = tmp_path / "plugins"
    _write_plugin(folder, "status_click", _source())
    env.load(folder, "status_click")
    _module("status_click").CONTEXT.status_item.update("Open me")
    assert _wait_until(lambda: env.bar.count == 1)

    env.bar.activate(0)

    assert [threading.get_ident()] == _module("status_click").CLICKS
    assert env.notices == []


def test_a_failing_click_is_announced_once_and_the_application_goes_on(
    env: Any, tmp_path: Path
) -> None:
    folder = tmp_path / "plugins"
    _write_plugin(folder, "status_broken", _source(click_fails=True))
    env.load(folder, "status_broken")
    context = _module("status_broken").CONTEXT
    context.status_item.update("Click me")
    assert _wait_until(lambda: env.bar.count == 1)

    env.bar.activate(0)
    env.bar.activate(0)

    assert len(_module("status_broken").CLICKS) == 2  # each click ran
    assert len(env.notices) == 1  # the same failure is announced once
    assert "status_broken title failed while clicking a status item" in env.notices[0]
    assert "the click broke" in env.notices[0]
    context.status_item.update("Still alive")  # the item keeps working after the failure
    assert _wait_until(lambda: _rows(env.bar)[0]["text"] == "Still alive")


def test_an_item_without_a_click_is_not_clickable(env: Any, tmp_path: Path) -> None:
    folder = tmp_path / "plugins"
    _write_plugin(folder, "status_plain", _source(click=False))
    env.load(folder, "status_plain")
    _module("status_plain").CONTEXT.status_item.update("Plain text")
    assert _wait_until(lambda: env.bar.count == 1)
    assert _rows(env.bar)[0]["clickable"] is False
    env.bar.activate(0)  # nothing to run, nothing to announce
    assert env.notices == []


# --- the order -----------------------------------------------------------------------------


def test_the_items_are_listed_in_plugin_load_order(env: Any, tmp_path: Path) -> None:
    folder = tmp_path / "plugins"
    for plugin_id in ("status_alpha", "status_beta", "status_gamma"):
        _write_plugin(folder, plugin_id, _source())
    records = env.load(folder, "status_alpha", "status_beta", "status_gamma")
    order = [record.plugin_id for record in records]
    assert sorted(order) == ["status_alpha", "status_beta", "status_gamma"]

    # The last plugin in load order is updated first: the rows still follow the load order.
    for plugin_id in reversed(order):
        _module(plugin_id).CONTEXT.status_item.update(f"{plugin_id} shows")
    assert _wait_until(lambda: env.bar.count == 3)
    assert [row["pluginId"] for row in _rows(env.bar)] == order

    # Hiding the middle one keeps the other two in their order.
    _module(order[1]).CONTEXT.status_item.clear()
    assert _wait_until(lambda: env.bar.count == 2)
    assert [row["pluginId"] for row in _rows(env.bar)] == [order[0], order[2]]

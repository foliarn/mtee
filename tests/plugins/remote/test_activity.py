"""The Remote activity (plan 126.9): the rows of its four sections, and what its actions call.

The engine is a stand-in that records the calls the pane makes (the real engine runs passes and
jobs, and is tested with the sync). The conflicts are the real feature, over the real tables; the
library and the files are the fakes of the remote tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from mtee.plugins.remote.activity import (  # pyright: ignore[reportMissingImports]
    BACKUPS_ID,
    CHANGES_ID,
    CONFLICTS_ID,
    LOG_ID,
    RemoteActivity,
)
from mtee.plugins.remote.conflicts import (  # pyright: ignore[reportMissingImports]
    TAB_KIND,
    ConflictFeature,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    CONFLICT_OPEN,
    RemoteStore,
    enqueue,
    insert_conflict,
    write_log,
)
from PySide6.QtCore import QObject, Signal
from tests.plugins.remote.helpers import FakeLibrary, make_context, track

from mtee.plugins.api import (
    PaneAction,
    PluginActivity,
    PluginContext,
    SidebarSection,
    TabRequest,
)


class FakeEngine(QObject):
    """The sync engine as the pane sees it: its three commands and its ``changed`` signal."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def request_pass(self) -> None:
        self.calls.append("pass")

    def fetch_now(self) -> None:
        self.calls.append("fetch")

    def apply_pending(self) -> None:
        self.calls.append("apply")


class FakeLink:
    """The connection as the pane sees it; offline, so no backup list is read."""

    state = "offline"

    def client(self) -> None:
        return None

    def refresh_status(self) -> None:
        return None


@dataclass
class Harness:
    context: PluginContext
    store: RemoteStore
    engine: FakeEngine
    conflicts: ConflictFeature
    view: RemoteActivity
    contributions: list[Any]

    def rows(self, section_id: str) -> list[dict[str, Any]]:
        self.view.refresh()
        return self.view.model(section_id).rows()


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    music = tmp_path / "music"
    library = FakeLibrary(
        [music],
        [track("t1", music / "a.flac"), track("t2", music / "b.flac")],
    )
    context = make_context(tmp_path, library)
    store = RemoteStore(context)
    engine = FakeEngine()
    conflicts = ConflictFeature(context, store, FakeLink(), lambda: "Studio", lambda: None)
    view = RemoteActivity(context, store, engine, conflicts, FakeLink())
    return Harness(context, store, engine, conflicts, view, list(view.contributions()))


def _section(contributions: list[Any], section_id: str) -> SidebarSection:
    for item in contributions:
        if isinstance(item, SidebarSection) and item.section_id == section_id:
            return item
    raise AssertionError(f"no section {section_id}")


def _action(contributions: list[Any], action_id: str) -> PaneAction:
    for item in contributions:
        if isinstance(item, PluginActivity):
            actions: tuple[PaneAction, ...] = item.actions
        elif isinstance(item, SidebarSection):
            actions = item.actions
        else:
            continue
        for action in actions:
            if action.action_id == action_id:
                return action
    raise AssertionError(f"no action {action_id}")


def test_the_activity_and_its_four_sections_are_contributed(harness: Harness) -> None:
    activity = [item for item in harness.contributions if isinstance(item, PluginActivity)]
    assert len(activity) == 1
    assert activity[0].activity_id == "remote"
    assert activity[0].title == "Remote"
    assert activity[0].icon == "cloud"
    sections = [item for item in harness.contributions if isinstance(item, SidebarSection)]
    assert [item.section_id for item in sections] == [
        CHANGES_ID,
        CONFLICTS_ID,
        BACKUPS_ID,
        LOG_ID,
    ]
    assert {item.activity for item in sections} == {"remote"}
    for item in sections:
        assert item.model is harness.view.model(item.section_id)


def test_an_empty_plugin_says_everything_is_up_to_date(harness: Harness) -> None:
    assert harness.rows(CHANGES_ID) == [{"id": "up_to_date", "name": "Everything is up to date"}]
    assert harness.rows(CONFLICTS_ID) == []
    assert harness.rows(BACKUPS_ID) == []
    assert harness.rows(LOG_ID) == []


def test_queue_rows_name_each_operation_and_a_blocked_one_is_a_warning(harness: Harness) -> None:
    with harness.store.transaction() as conn:
        enqueue(conn, kind="upload", track_id="t1", item_id=None)
        enqueue(conn, kind="move", track_id="t2", item_id=None)
    with harness.store.transaction() as conn:
        conn.execute("UPDATE remote_queue SET state = 'blocked' WHERE track_id = 't2'")

    rows = harness.rows(CHANGES_ID)
    assert [row["name"] for row in rows] == ["Upload a", "Move b"]
    assert "tone" not in rows[0]
    assert rows[1]["tone"] == "warning"
    assert rows[1]["count"] == "blocked"


def test_a_done_queue_entry_is_not_listed(harness: Harness) -> None:
    with harness.store.transaction() as conn:
        enqueue(conn, kind="upload", track_id="t1", item_id=None)
    with harness.store.transaction() as conn:
        conn.execute("UPDATE remote_queue SET state = 'done'")

    assert harness.rows(CHANGES_ID) == [{"id": "up_to_date", "name": "Everything is up to date"}]


def test_a_conflict_row_names_the_track_and_its_reason_and_opens_its_tab(harness: Harness) -> None:
    with harness.store.transaction() as conn:
        insert_conflict(
            conn,
            track_id="t1",
            item_id="item-1",
            local={"kind": "both_changed", "relative_path": "House/a.flac"},
            server={"kind": "both_changed", "item_id": "item-1"},
            state=CONFLICT_OPEN,
        )
    harness.conflicts.refresh()

    rows = harness.rows(CONFLICTS_ID)
    assert len(rows) == 1
    conflict_id = rows[0]["id"]
    assert rows[0]["name"].startswith("a: ")
    assert rows[0]["tone"] == "warning"

    activate = _section(harness.contributions, CONFLICTS_ID).activate
    assert activate is not None
    assert activate(conflict_id) == TabRequest(TAB_KIND, conflict_id)
    assert activate("no-such-conflict") is None


def test_the_backups_list_the_ten_newest_with_date_and_kind(harness: Harness) -> None:
    raw = [
        {
            "backup_id": f"b{index:02d}",
            "created_at_utc": f"2026-11-{index + 1:02d}T03:00:00Z",
            "kind": "automatic" if index % 2 == 0 else "manual",
            "size_bytes": 90 * 1024 * 1024,
            "device_id": "",
        }
        for index in range(12)
    ]
    harness.view.set_backups(raw)

    rows = harness.rows(BACKUPS_ID)
    assert [row["id"] for row in rows] == [f"b{index:02d}" for index in range(10)]
    assert "Automatic" in rows[0]["name"]
    assert "Manual" in rows[1]["name"]
    assert rows[0]["count"] == "90 MB"
    assert _section(harness.contributions, BACKUPS_ID).activate is None


def test_the_log_is_newest_first_and_a_warning_has_the_warning_tone(harness: Harness) -> None:
    with harness.store.transaction() as conn:
        write_log(conn, "Fetched 5 changes")
        write_log(conn, "Server unreachable", "warning")

    rows = harness.rows(LOG_ID)
    assert [row["name"] for row in rows] == ["Server unreachable", "Fetched 5 changes"]
    assert rows[0]["tone"] == "warning"
    assert "tone" not in rows[1]
    assert rows[0]["count"].count(":") == 1


def test_the_log_shows_the_last_hundred_lines(harness: Harness) -> None:
    with harness.store.transaction() as conn:
        for index in range(105):
            write_log(conn, f"line {index}")

    rows = harness.rows(LOG_ID)
    assert len(rows) == 100
    assert rows[0]["name"] == "line 104"
    assert rows[-1]["name"] == "line 5"


def test_apply_fetch_and_sync_call_the_engine(harness: Harness) -> None:
    _action(harness.contributions, "apply").run()
    _action(harness.contributions, "fetch").run()
    _action(harness.contributions, "sync").run()

    assert harness.engine.calls == ["apply", "fetch", "pass"]


def test_the_apply_action_has_the_check_icon_and_its_tooltip(harness: Harness) -> None:
    apply = _action(harness.contributions, "apply")
    assert apply.icon == "check"
    assert apply.tip == "Apply pending changes"

"""The Remote activity (plan 126.9): the rows of its four sections, and what its actions call.

The engine is a stand-in that records the calls the pane makes (the real engine runs passes and
jobs, and is tested with the sync). The conflicts are the real feature, over the real tables; the
library and the files are the fakes of the remote tests.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from mtee.plugins.remote.activity import (  # pyright: ignore[reportMissingImports]  # pyright: ignore[reportMissingImports]
    BACKUPS_ID,
    CHANGES_ID,
    CONFLICTS_ID,
    LOG_ID,
    MORE_CHANGES_ID,
    SHOWN_CHANGES,
    RemoteActivity,
)
from mtee.plugins.remote.conflicts import (  # pyright: ignore[reportMissingImports]  # pyright: ignore[reportMissingImports]
    LIST_REF,
    LIST_TAB_KIND,
    MORE_ID,
    SHOWN,
    TAB_KIND,
    ConflictFeature,
)
from mtee.plugins.remote.engine import (  # pyright: ignore[reportMissingImports]
    AUTO,
    MANUAL,
    set_sync_mode,
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


UP_TO_DATE_ROW = {
    "id": "up_to_date",
    "name": "Everything is up to date",
    "icon": "check",
    "tone": "secondary",
}


class FakeLink:
    """The connection as the pane sees it; offline, so no backup list is read."""

    state = "offline"
    state_text = "The server cannot be reached."

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
    assert harness.rows(CHANGES_ID) == [UP_TO_DATE_ROW]
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
    # A blocked or failed operation is listed first, so a capped list never hides it.
    assert [row["name"] for row in rows] == ["Move b", "Upload a"]
    assert rows[0]["tone"] == "warning"
    assert rows[0]["count"] == "blocked"
    assert "tone" not in rows[1]


def test_a_done_queue_entry_is_not_listed(harness: Harness) -> None:
    with harness.store.transaction() as conn:
        enqueue(conn, kind="upload", track_id="t1", item_id=None)
    with harness.store.transaction() as conn:
        conn.execute("UPDATE remote_queue SET state = 'done'")

    assert harness.rows(CHANGES_ID) == [UP_TO_DATE_ROW]


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


def test_apply_is_a_text_button_drawn_in_manual_mode_only(harness: Harness) -> None:
    apply = _action(harness.contributions, "apply")
    assert apply.label == "Apply"
    assert apply.visible is not None
    assert apply.visible() is False  # Auto is the default
    set_sync_mode(harness.context, MANUAL)
    assert apply.visible() is True
    set_sync_mode(harness.context, AUTO)
    assert apply.visible() is False


def test_the_counts_are_the_operations_to_send_and_the_open_conflicts(harness: Harness) -> None:
    changes = _section(harness.contributions, CHANGES_ID)
    conflicts = _section(harness.contributions, CONFLICTS_ID)
    activity = next(item for item in harness.contributions if isinstance(item, PluginActivity))
    assert changes.count is not None and conflicts.count is not None
    assert activity.badge is not None
    assert (changes.count(), conflicts.count(), activity.badge()) == (0, 0, 0)

    with harness.store.transaction() as conn:
        enqueue(conn, kind="upload", track_id="t1", item_id=None)
        enqueue(conn, kind="move", track_id="t2", item_id=None)
        enqueue(conn, kind="upload", track_id="t1", item_id=None)
    with harness.store.transaction() as conn:
        conn.execute("UPDATE remote_queue SET state = 'blocked' WHERE track_id = 't2'")
        conn.execute("UPDATE remote_queue SET state = 'done' WHERE kind = 'upload' AND rowid = 3")
        insert_conflict(
            conn,
            track_id="t1",
            item_id="item-1",
            local={"kind": "both_changed", "relative_path": "House/a.flac"},
            server={"kind": "both_changed", "item_id": "item-1"},
            state=CONFLICT_OPEN,
        )

    # Pending (one) and blocked (one) count for Changes; the done one does not.
    assert changes.count() == 2
    assert conflicts.count() == 1
    # The badge is the open conflicts plus the blocked operations.
    assert activity.badge() == 2


def test_refresh_asks_the_core_again_only_when_a_count_or_the_mode_changed(
    harness: Harness,
) -> None:
    calls: list[int] = []
    context = replace(harness.context, refresh_ui=lambda: calls.append(1))
    view = RemoteActivity(context, harness.store, harness.engine, harness.conflicts, FakeLink())

    view.refresh()
    assert calls == [1]
    view.refresh()
    assert calls == [1]

    with harness.store.transaction() as conn:
        enqueue(conn, kind="upload", track_id="t1", item_id=None)
    view.refresh()
    assert calls == [1, 1]

    # A pending operation that becomes blocked keeps the queue count but moves the badge.
    with harness.store.transaction() as conn:
        conn.execute("UPDATE remote_queue SET state = 'blocked'")
    view.refresh()
    assert calls == [1, 1, 1]

    set_sync_mode(context, MANUAL)
    view.refresh()
    assert calls == [1, 1, 1, 1]


def test_the_foot_says_the_connection_then_the_mode_and_what_waits(harness: Harness) -> None:
    activity = next(item for item in harness.contributions if isinstance(item, PluginActivity))
    assert activity.foot is harness.view.foot
    harness.view.refresh()
    assert harness.view.foot.rows() == [
        {"text": "The server cannot be reached.", "tone": "warning"},
        {"text": "Auto sync", "tone": "muted"},
    ]

    with harness.store.transaction() as conn:
        enqueue(conn, kind="upload", track_id="t1", item_id=None)
    set_sync_mode(harness.context, MANUAL)
    harness.view.refresh()
    assert harness.view.foot.rows()[1] == {
        "text": "Manual sync · 1 to apply",
        "tone": "muted",
    }


@pytest.mark.parametrize(
    ("state", "text", "expected"),
    [
        ("connected", "Connected. Server 0.3.0.", ("Connected. Server 0.3.0.", "secondary")),
        (
            "disconnected",
            "Not connected.",
            ("Not connected.", "muted"),
        ),
        ("error", "The password was refused.", ("The password was refused.", "warning")),
    ],
)
def test_the_connection_line_follows_the_state(
    harness: Harness, state: str, text: str, expected: tuple[str, str]
) -> None:
    link = FakeLink()
    link.state = state
    link.state_text = text
    view = RemoteActivity(harness.context, harness.store, harness.engine, harness.conflicts, link)
    view.refresh()
    first = view.foot.rows()[0]
    assert (first["text"], first["tone"]) == expected
    if state == "disconnected":
        assert view.foot.rows()[1] == {"text": "Connect in Settings > Remote.", "tone": "muted"}


def _many_conflicts(
    harness: Harness,
    count: int,
    *,
    extra_local: dict[str, Any] | None = None,
    state: str = CONFLICT_OPEN,
) -> None:
    with harness.store.transaction() as conn:
        for index in range(count):
            insert_conflict(
                conn,
                track_id=f"x{index:04d}",
                item_id=f"item-{index:04d}",
                local={
                    "kind": "tags_differ",
                    "relative_path": f"A/{index:04d}.flac",
                    **(extra_local or {}),
                },
                server={"kind": "tags_differ", "item_id": f"item-{index:04d}"},
                state=state,
            )


def test_the_count_reads_only_the_conflicts_that_wait(harness: Harness) -> None:
    _many_conflicts(harness, 3)
    _many_conflicts(harness, 2, state="decide_later")
    _many_conflicts(
        harness, 4, state="decide_later", extra_local={"dismissed_at_utc": "2026-11-01"}
    )
    _many_conflicts(harness, 5, state="resolved")
    harness.conflicts.refresh()
    # The SQL count agrees with Conflict.visible: open and decide-later not dismissed.
    assert harness.conflicts.open_count() == 5
    assert len(harness.conflicts.list_rows()) == 5


def test_the_bell_and_the_window_show_fifty_conflicts_then_a_row_for_the_rest(
    harness: Harness,
) -> None:
    _many_conflicts(harness, SHOWN + 7)
    harness.conflicts.refresh()

    waiting = harness.conflicts.model.rows()
    assert len(waiting) == SHOWN + 1
    assert waiting[-1] == {
        "id": MORE_ID,
        "title": "7 more conflicts",
        "subtitle": "Open the list of every conflict",
        "action": "Show all",
    }
    assert harness.conflicts.run_waiting(MORE_ID) == TabRequest(LIST_TAB_KIND, LIST_REF)
    harness.conflicts.dismiss_waiting(MORE_ID)  # a summary row: nothing is dismissed
    assert harness.conflicts.open_count() == SHOWN + 7

    rows = harness.rows(CONFLICTS_ID)
    assert len(rows) == SHOWN + 1
    assert rows[-1] == {"id": MORE_ID, "name": "7 more conflicts…", "icon": "list"}
    activate = _section(harness.contributions, CONFLICTS_ID).activate
    assert activate is not None and activate(MORE_ID) == TabRequest(LIST_TAB_KIND, LIST_REF)
    assert len(harness.conflicts.list_rows()) == SHOWN + 7


def test_the_changes_show_the_problems_first_and_count_the_rest(harness: Harness) -> None:
    with harness.store.transaction() as conn:
        for index in range(SHOWN_CHANGES + 10):
            enqueue(conn, kind="upload", track_id=f"t{index}", item_id=None)
        conn.execute(
            "UPDATE remote_queue SET state = 'failed' WHERE track_id = ?",
            (f"t{SHOWN_CHANGES + 5}",),
        )

    rows = harness.rows(CHANGES_ID)
    assert len(rows) == SHOWN_CHANGES + 1
    assert rows[0]["tone"] == "warning", "a failed operation is listed first"
    assert rows[-1] == {"id": MORE_CHANGES_ID, "name": "10 more changes"}

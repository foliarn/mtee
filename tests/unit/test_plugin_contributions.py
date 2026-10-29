"""The data contributions of plugins: checks, plugin columns, rows and the guard (plan 121.5)."""

from __future__ import annotations

import wave
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject

from mtee.models.plugin_columns import (
    PluginColumnStore,
    RegisteredColumn,
    column_options,
    decorate_rows,
    effective_hidden,
    toggled_columns,
)
from mtee.models.plugin_rows_model import PluginRowsModel
from mtee.models.plugin_ui_model import PluginUiModel
from mtee.models.workspace_rows import sort_rows
from mtee.plugins.api import (
    CellValue,
    Contribution,
    PaneAction,
    PluginActivity,
    SettingsPage,
    SidebarSection,
    TabAction,
    TabKind,
    TrackAction,
    TrackColumn,
    TrackListRow,
)
from mtee.plugins.contributions import check_contributions
from mtee.plugins.loader import DiscoveredPlugin, LoadedPlugin, PluginStatus


def _rows(_ref: str) -> list[TrackListRow]:
    return []


def _kind(name: str = "pl.list") -> TabKind:
    return TabKind(name, str, _rows)


def _run(_ref: str) -> None:
    return None


def _noop() -> None:
    return None


# ----------------------------------------------------------------------------- the checks


def test_valid_contributions_pass(qapp, tmp_path: Path) -> None:
    page = tmp_path / "page.qml"
    page.write_text("import QtQuick\nItem {}\n", encoding="utf-8")
    model = PluginRowsModel()
    check_contributions(
        "pl",
        [
            PluginActivity("main", "Pl", "music", (PaneAction("go", "Go", "repeat", _noop),)),
            SidebarSection("lists", "Lists", "main", model),
            SidebarSection("side", "Side", "playlists", model),
            _kind(),
            TabKind("pl.page", str, page),
            TabAction("a", "pl.list", "A", _run),
            TabAction("b", "playlist", "B", _run),
            TrackColumn("status", "Status", lambda row: None),
            TrackAction("act", "Act", "Pl", lambda rows: None),
            SettingsPage("accounts", "Accounts", page),
        ],
    )


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: [_kind("other.list")], "must be written pl"),
        (lambda: [_kind("pl.List")], "must be written pl"),
        (lambda: [_kind(), _kind()], "declared twice"),
        (lambda: [TabKind("pl.page", str, Path("missing.qml"))], "does not exist"),
        (lambda: [PluginActivity("tasks", "T", "music")], "used by MTEE itself"),
        (lambda: [PluginActivity("Main", "T", "music")], "lowercase snake_case"),
        (lambda: [PluginActivity("main", "", "music")], "no title"),
        (lambda: [SidebarSection("s", "S", "tasks", PluginRowsModel())], "neither Explorer"),
        (lambda: [SidebarSection("s", "S", "playlists", object())], "not a Qt model"),  # type: ignore[arg-type]
        (lambda: [TabAction("a", "pl.unknown", "A", _run)], "neither playlist nor"),
        (lambda: [TabAction("a", "playlist", "A", _run, kind="huge")], "unknown kind"),  # type: ignore[arg-type]
        (lambda: [TrackColumn("c", "C", None)], "not callable"),  # type: ignore[arg-type]
        (lambda: [TrackAction("a", "A", "", lambda rows: None)], "no group"),
    ],
)
def test_a_broken_contribution_is_refused_with_a_reason(
    qapp, build: Callable[[], list[Contribution]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        check_contributions("pl", build())


# --------------------------------------------------------------------------- the columns


def _column(
    column_id: str = "status", visible_for: tuple[str, ...] = (), **kwargs: Any
) -> RegisteredColumn:
    column = TrackColumn(
        column_id,
        "Status",
        kwargs.pop("value_fn", lambda row: CellValue("Local")),
        default_visible_for=visible_for,
        **kwargs,
    )
    return RegisteredColumn(f"pl.{column_id}", "pl", "Pl plugin", column)


def test_a_column_the_layout_never_mentioned_follows_its_default_visibility() -> None:
    column = _column(visible_for=("pl.list",))
    layout = {"order": ["title"], "hidden": []}

    assert effective_hidden(layout, [column], "playlist") == ["pl.status"]
    assert effective_hidden(layout, [column], "pl.list") == []


def test_toggling_a_plugin_column_writes_the_choice_into_the_layout() -> None:
    column = _column(visible_for=("pl.list",))
    layout = {"order": ["title"], "hidden": [], "widths": {}}

    shown = toggled_columns(layout, [column], "playlist", "pl.status")
    assert "pl.status" in shown["order"]
    assert effective_hidden(shown, [column], "playlist") == []
    hidden = toggled_columns(shown, [column], "playlist", "pl.status")
    assert effective_hidden(hidden, [column], "playlist") == ["pl.status"]
    # Hiding a column that starts visible keeps it hidden, even though the kind shows it.
    off = toggled_columns(layout, [column], "pl.list", "pl.status")
    assert effective_hidden(off, [column], "pl.list") == ["pl.status"]


def test_the_picker_lists_the_column_with_its_plugin() -> None:
    assert column_options([_column(width=90)]) == [
        {"key": "pl.status", "label": "Status", "plugin": "Pl plugin", "width": 90}
    ]


def test_cells_are_added_to_the_rows_and_a_failing_column_is_skipped() -> None:
    def fails(_row: object) -> CellValue:
        raise RuntimeError("boom")

    good = _column(
        value_fn=lambda row: (
            CellValue("Missing", "secondary", "Download") if row["id"] == "a" else None
        )
    )
    bad = _column("broken", value_fn=fails)

    rows = decorate_rows([{"id": "a"}, {"id": "b"}], [good, bad])

    assert rows[0]["plugin"] == {"pl.status": {"text": "Missing", "tone": "secondary"}}
    assert rows[0]["rowAction"] == "Download"
    assert rows[0]["rowActionColumn"] == "pl.status"
    assert rows[1]["plugin"] == {}
    assert "rowAction" not in rows[1]
    assert decorate_rows([{"id": "a"}], []) == [{"id": "a"}]


def test_rows_sort_by_the_text_of_a_plugin_column() -> None:
    rows = [
        {"id": "1", "title": "A", "plugin": {"pl.status": {"text": "Missing"}}},
        {"id": "2", "title": "B", "plugin": {"pl.status": {"text": "Local"}}},
        {"id": "3", "title": "C", "plugin": {}},
    ]

    assert [row["id"] for row in sort_rows(rows, "pl.status", True)] == ["2", "1", "3"]
    assert [row["id"] for row in sort_rows(rows, "pl.status", False)] == ["1", "2", "3"]
    assert [row["id"] for row in sort_rows(rows, "nothing.here", True)] == ["1", "2", "3"]


def test_the_layout_of_a_plugin_tab_is_validated_and_saved(qapp) -> None:
    store = PluginColumnStore(None)
    layout = store.preferences("pl.list")
    assert layout["hidden"] == ["bpm", "key"]

    store.resize("pl.list", "pl.status", 5000)
    store.resize("pl.list", "artist", 10)
    widths = store.preferences("pl.list")["widths"]
    assert widths["pl.status"] == 640 and widths["artist"] == 44

    store.move("pl.list", "pl.status", -1, ["pl.status"])
    assert store.preferences("pl.list")["order"][-2:] == ["pl.status", "duration"]
    store.move_relative("pl.list", "pl.status", "title", False, ["pl.status"])
    assert store.preferences("pl.list")["order"][0] == "pl.status"

    saved = store.save("pl.list", {"order": ["x", "title", 3], "hidden": "no", "widths": []})
    assert saved["order"][0] == "title" and "x" not in saved["order"]
    assert saved["hidden"] == ["bpm", "key"]
    assert store.reset("pl.list") == store.preferences("pl.list")


# ----------------------------------------------------------------------------- the rows


def test_the_rows_model_replaces_its_rows_and_reports_once(qapp) -> None:
    model = PluginRowsModel([{"id": "a", "name": "A"}])
    changes: list[int] = []
    model.rowsChanged.connect(lambda: changes.append(model.rowCount()))

    model.replace([{"id": "a", "name": "A"}])
    model.replace([{"id": "b", "name": "B"}, {"id": "c", "name": "C"}])

    assert changes == [2]
    assert model.property("items") == [{"id": "b", "name": "B"}, {"id": "c", "name": "C"}]
    assert model.property("count") == 2


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 80)


def _ui(contributions: Sequence[Contribution]) -> tuple[PluginUiModel, list[str]]:
    record = LoadedPlugin(
        DiscoveredPlugin("pl", Path("."), Path("."), None),
        PluginStatus.RUNNING,
        contributions=tuple(contributions),
    )
    ui = PluginUiModel()
    notices: list[str] = []
    ui.noticeRaised.connect(notices.append)
    ui.register([record])
    return ui, notices


def test_plugin_rows_are_available_only_with_a_readable_local_file(qapp, tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    _wav(audio)
    library = {
        "t1": {"rootId": "r", "status": "readable", "path": str(audio), "bpm": 120, "cover": 3},
        "t2": {"rootId": "r", "status": "readable", "path": str(tmp_path / "gone.wav")},
    }

    def rows(_ref: str) -> list[TrackListRow]:
        return [
            TrackListRow("a", "Have", "Ann", "Alb", 61.2, "t1", {"k": 1}),
            TrackListRow("b", "Gone", track_id="t2"),
            TrackListRow("c", "Unknown", track_id="nope"),
            TrackListRow("d", "None"),
        ]

    ui, _notices = _ui([TabKind("pl.list", lambda ref: f"List {ref}", rows)])

    result = ui.track_rows("pl.list", "x", lambda track_id: library.get(track_id, {}))

    assert [row["available"] for row in result] == [True, False, False, False]
    first = result[0]
    assert (first["id"], first["trackId"], first["title"], first["artist"]) == (
        "a",
        "t1",
        "Have",
        "Ann",
    )
    assert first["bpm"] == 120 and first["seconds"] == 61 and first["duration"] == "1:01"
    assert first["data"] == {"k": 1}
    assert all(row["trackId"] == "" for row in result[1:])
    assert result[3]["duration"] == "" and result[3]["coverUrl"] == ""
    assert ui.tab_title("pl.list", "x") == "List x"


def test_a_plugin_function_that_raises_is_announced_once(qapp) -> None:
    def explodes(_ref: str) -> list[TrackListRow]:
        raise RuntimeError("no data")

    ui, notices = _ui([TabKind("pl.list", str, explodes)])

    assert ui.track_rows("pl.list", "x", lambda _id: {}) == []
    assert ui.track_rows("pl.list", "y", lambda _id: {}) == []
    assert len(notices) == 1
    assert "pl" in notices[0] and "no data" in notices[0]


def test_only_a_running_plugin_contributes(qapp) -> None:
    contribution = TrackColumn("status", "Status", lambda row: None)
    failed = LoadedPlugin(
        DiscoveredPlugin("pl", Path("."), Path("."), None),
        PluginStatus.FAILED,
        "boom",
        contributions=(contribution,),
    )
    disabled = LoadedPlugin(
        DiscoveredPlugin("q", Path("."), Path("."), None), PluginStatus.DISABLED
    )
    ui = PluginUiModel()
    ui.register([failed, disabled])

    assert ui.property("active") is False
    assert ui.property("columnOptions") == []
    assert ui.property("activities") == []
    assert ui.property("settingsPages") == []


def test_track_actions_are_grouped_and_filtered_by_the_selected_rows(qapp) -> None:
    calls: list[str] = []
    ui, _notices = _ui(
        [
            TrackAction(
                "a",
                "Only missing",
                "Pl",
                lambda rows: calls.append("a"),
                enabled_fn=lambda rows: all(r.get("x") for r in rows),
            ),
            TrackAction("b", "Always", "Pl", lambda rows: calls.append("b")),
            TrackAction("c", "Other", "Other", lambda rows: calls.append("c")),
        ]
    )

    both = ui.track_action_items([{"x": 1}])
    assert [(item["header"], item["label"]) for item in both] == [
        (True, "Pl"),
        (False, "Only missing"),
        (False, "Always"),
        (True, "Other"),
        (False, "Other"),
    ]
    assert [item["label"] for item in ui.track_action_items([{"x": 0}])] == [
        "Pl",
        "Always",
        "Other",
        "Other",
    ]
    ui.run_track_action("pl.b", [])
    assert calls == ["b"]


def test_header_buttons_read_their_state_for_the_tab(qapp) -> None:
    state = {"on": False}
    ui, _notices = _ui(
        [
            _kind(),
            TabAction("n", "pl.list", lambda ref: f"Count {ref}", _run, icon="arrow-down"),
            TabAction(
                "t",
                "pl.list",
                "Watch",
                lambda ref: state.update(on=not state["on"]),
                kind="toggle",
                checked=lambda ref: state["on"],
                enabled=lambda ref: ref != "locked",
            ),
            TabAction("g", "playlist", "Push", _run, kind="ghost"),
        ]
    )

    buttons = ui.headerActions("pl.list", "7", 0)
    assert [(b["id"], b["label"], b["kind"], b["checked"], b["enabled"]) for b in buttons] == [
        ("pl.n", "Count 7", "neutral", False, True),
        ("pl.t", "Watch", "toggle", False, True),
    ]
    ui.runHeaderAction("pl.t", "7")
    assert ui.headerActions("pl.list", "locked", 1)[1]["checked"] is True
    assert ui.headerActions("pl.list", "locked", 1)[1]["enabled"] is False
    assert [b["label"] for b in ui.headerActions("playlist", "id", 0)] == ["Push"]
    assert ui.headerActions("folder", "x", 0) == []


def test_plugin_objects_are_owned_by_the_model_not_by_the_qml(qapp) -> None:
    model = PluginRowsModel()
    backend = QObject()
    ui, _notices = _ui(
        [
            SidebarSection("s", "S", "playlists", model),
            TabKind("pl.list", str, _rows, backend=backend),
        ]
    )

    assert model.parent() is ui
    assert backend.parent() is ui
    assert ui.sectionModel("pl.s") is model
    assert [s["title"] for s in ui.sections("playlists")] == ["S"]
    assert ui.sections("explorer") == []


def test_a_saved_plugin_activity_is_kept_until_the_plugins_are_loaded(qapp, tmp_path: Path) -> None:
    from mtee.persistence.database import Database
    from mtee.persistence.workspace_repository import DEFAULT_WORKSPACE, WorkspaceRepository

    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    repository = WorkspaceRepository(database)
    try:
        for saved, expected in (
            ("ui_probe.main", "ui_probe.main"),
            ("Not A.Plugin", "explorer"),
            ("playlists", "playlists"),
        ):
            repository.save(DEFAULT_WORKSPACE | {"activity": saved})
            assert repository.load()["activity"] == expected
    finally:
        database.close()

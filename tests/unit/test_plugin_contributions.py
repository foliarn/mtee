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
    LibraryScanned,
    PaneAction,
    PlaylistMeta,
    PluginActivity,
    PluginDialog,
    SettingsPage,
    SidebarSection,
    TabAction,
    TabKind,
    TabRequest,
    TrackAction,
    TrackColumn,
    TrackListRow,
    WaitingItems,
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


def _bad(value: object) -> Any:
    """A value of the wrong type, for the checks that refuse it (the type checker allows it)."""
    return value


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
        (lambda: [PluginActivity("main", "T", "music", badge=5)], "not callable"),  # type: ignore[arg-type]
        (
            lambda: [
                PluginActivity(
                    "main", "T", "music", (PaneAction("go", "Go", "r", _noop, label=_bad(3)),)
                )
            ],
            "label that is not text",
        ),
        (
            lambda: [
                PluginActivity(
                    "main", "T", "music", (PaneAction("go", "Go", "r", _noop, visible=_bad("x")),)
                )
            ],
            "not callable",
        ),
        (
            lambda: [SidebarSection("s", "S", "playlists", PluginRowsModel(), count=3)],  # type: ignore[arg-type]
            "not callable",
        ),
        (
            lambda: [SidebarSection("s", "S", "playlists", PluginRowsModel(), on_fold="fold")],  # type: ignore[arg-type]
            "not callable",
        ),
        (
            lambda: [SidebarSection("s", "S", "playlists", PluginRowsModel(), expanded="yes")],  # type: ignore[arg-type]
            "neither a bool",
        ),
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


def test_a_header_button_can_say_why_it_is_disabled(qapp) -> None:
    ui, _notices = _ui(
        [
            _kind(),
            TabAction(
                "d",
                "pl.list",
                "Download",
                _run,
                enabled=lambda ref: ref != "off",
                disabled_reason=lambda ref: "Install the downloader first" if ref == "no" else "",
            ),
        ]
    )

    assert [(b["enabled"], b["reason"]) for b in ui.headerActions("pl.list", "yes", 0)] == [
        (True, "")
    ]
    assert [(b["enabled"], b["reason"]) for b in ui.headerActions("pl.list", "no", 0)] == [
        (False, "Install the downloader first")
    ]
    # Disabled without a sentence: grey, no tooltip.
    assert [(b["enabled"], b["reason"]) for b in ui.headerActions("pl.list", "off", 0)] == [
        (False, "")
    ]
    with pytest.raises(ValueError, match="not callable"):
        check_contributions(
            "pl",
            [_kind(), TabAction("d", "pl.list", "D", _run, disabled_reason="no")],  # type: ignore[arg-type]
        )


def test_plugins_add_phrases_to_the_meta_line_of_a_local_playlist(qapp) -> None:
    def raises(_playlist_id: str) -> str:
        raise RuntimeError("no phrase")

    ui, notices = _ui(
        [
            PlaylistMeta(lambda playlist_id: "linked to Pl" if playlist_id == "p1" else ""),
            PlaylistMeta(lambda playlist_id: "twice" if playlist_id == "p1" else ""),
            PlaylistMeta(raises),
        ]
    )

    assert ui.playlistMeta("p1", 0) == "linked to Pl · twice"
    assert ui.playlistMeta("p2", 0) == ""
    assert len(notices) == 1 and "no phrase" in notices[0]
    with pytest.raises(ValueError, match="not callable"):
        check_contributions("pl", [PlaylistMeta("text")])  # type: ignore[arg-type]


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
            ("ui_probe.main", ["ui_probe.main"]),
            ("Not A.Plugin", []),
            ("playlists", ["playlists"]),
        ):
            left = {"open": True, "width": 260, "windows": [saved], "ratio": 0.5}
            docks = {"left": left, "right": DEFAULT_WORKSPACE["docks"]["right"]}
            repository.save(DEFAULT_WORKSPACE | {"docks": docks})
            assert repository.load()["docks"]["left"]["windows"] == expected
    finally:
        database.close()


# ------------------------------------------------------------------ library scan hooks


def test_a_library_scan_hook_must_be_callable(qapp) -> None:
    check_contributions("pl", [LibraryScanned(lambda root: None)])
    with pytest.raises(ValueError, match="not callable"):
        check_contributions("pl", [LibraryScanned(None)])  # type: ignore[arg-type]


def test_a_scan_hook_receives_the_scanned_folder_and_a_failure_is_announced_once(
    tmp_path: Path, qapp
) -> None:
    seen: list[Path] = []

    def explodes(_root: Path) -> None:
        raise RuntimeError("hook bug")

    ui, notices = _ui([LibraryScanned(seen.append), LibraryScanned(explodes)])

    ui.library_scanned(tmp_path / "music")
    ui.library_scanned(tmp_path / "more")

    assert seen == [tmp_path / "music", tmp_path / "more"]  # the next hook runs after a failure
    assert len(notices) == 1 and "hook bug" in notices[0]


def test_only_a_running_plugin_is_told_about_a_scan(tmp_path: Path, qapp) -> None:
    seen: list[Path] = []
    disabled = LoadedPlugin(
        DiscoveredPlugin("q", Path("."), Path("."), None),
        PluginStatus.DISABLED,
        contributions=(LibraryScanned(seen.append),),
    )
    ui = PluginUiModel()
    ui.register([disabled])

    ui.library_scanned(tmp_path)

    assert seen == []


# ------------------------------------------------------------------ waiting items


def _waiting(model: Any, **kwargs: Any) -> WaitingItems:
    values: dict[str, Any] = {
        "section_id": "waiting",
        "title": "Waiting for you",
        "model": model,
        "run": lambda _id: None,
        "dismiss": lambda _id: None,
    }
    values.update(kwargs)
    return WaitingItems(**values)


def test_valid_waiting_items_pass(qapp) -> None:
    check_contributions(
        "pl", [_waiting(PluginRowsModel()), _waiting(PluginRowsModel(), section_id="more")]
    )


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: [_waiting(PluginRowsModel(), section_id="Wait")], "lowercase snake_case"),
        (lambda: [_waiting(PluginRowsModel(), title="")], "no title"),
        (lambda: [_waiting(object())], "not a Qt model"),
        (lambda: [_waiting(PluginRowsModel(), run=None)], "not callable"),
        (lambda: [_waiting(PluginRowsModel(), dismiss=None)], "not callable"),
        (lambda: [_waiting(PluginRowsModel()), _waiting(PluginRowsModel())], "declared twice"),
    ],
)
def test_broken_waiting_items_are_refused_with_a_reason(
    qapp, build: Callable[[], list[Contribution]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        check_contributions("pl", build())


def _item(row_id: str, title: str = "Item") -> dict[str, str]:
    return {"id": row_id, "title": title, "subtitle": "Needs a pick", "action": "Pick"}


def test_waiting_items_are_counted_listed_and_followed_as_the_plugin_changes_them(qapp) -> None:
    first = PluginRowsModel([_item("a"), _item("b")])
    second = PluginRowsModel()
    ui, _notices = _ui(
        [
            _waiting(first),
            _waiting(second, section_id="other", title="Also waiting"),
            _kind("pl.list"),
        ]
    )
    counts: list[int] = []
    ui.waitingChanged.connect(lambda: counts.append(ui.property("waitingCount")))

    assert ui.property("active") is True
    assert ui.property("waitingCount") == 2
    assert ui.property("waitingGroups") == [
        {"key": "pl.waiting", "title": "Waiting for you", "plugin": "pl"},
        {"key": "pl.other", "title": "Also waiting", "plugin": "pl"},
    ]
    assert ui.waitingModel("pl.waiting") is first
    assert ui.waitingModel("pl.nothing") is None
    assert first.parent() is ui  # owned by the model, not by the QML

    second.replace([_item("c")])
    first.replace([_item("a")])
    first.replace([])
    first.replace([])  # nothing changed: nothing is announced
    second.replace([])

    assert counts == [3, 2, 1, 0]
    assert ui.property("waitingCount") == 0


def test_a_waiting_item_runs_opens_the_tab_it_names_and_is_dismissed(qapp) -> None:
    model = PluginRowsModel([_item("a"), _item("b")])
    calls: list[str] = []

    def run(item_id: str) -> TabRequest | None:
        calls.append(f"run {item_id}")
        return TabRequest("pl.list", item_id) if item_id == "a" else None

    def dismiss(item_id: str) -> None:
        calls.append(f"dismiss {item_id}")
        model.replace([row for row in model.rows() if row["id"] != item_id])

    ui, _notices = _ui([_waiting(model, run=run, dismiss=dismiss), _kind("pl.list")])
    tabs: list[tuple[str, str]] = []
    ui.tabRequested.connect(lambda kind, ref: tabs.append((kind, ref)))

    ui.runWaiting("pl.waiting", "a")
    ui.runWaiting("pl.waiting", "b")  # the plugin names no tab
    ui.runWaiting("pl.unknown", "a")  # a group that does not exist is ignored
    ui.dismissWaiting("pl.waiting", "a")
    ui.dismissWaiting("pl.unknown", "b")

    assert calls == ["run a", "run b", "dismiss a"]
    assert tabs == [("pl.list", "a")]
    assert ui.property("waitingCount") == 1


def test_a_waiting_function_that_raises_is_announced_once(qapp) -> None:
    def explodes(_item_id: str) -> None:
        raise RuntimeError("no answer")

    ui, notices = _ui([_waiting(PluginRowsModel([_item("a")]), run=explodes, dismiss=explodes)])

    ui.runWaiting("pl.waiting", "a")
    ui.runWaiting("pl.waiting", "a")
    ui.dismissWaiting("pl.waiting", "a")

    assert len(notices) == 2  # one for the answer, one for the dismissal
    assert all("pl" in notice and "no answer" in notice for notice in notices)


def test_only_a_running_plugin_has_waiting_items(qapp) -> None:
    disabled = LoadedPlugin(
        DiscoveredPlugin("q", Path("."), Path("."), None),
        PluginStatus.DISABLED,
        contributions=(_waiting(PluginRowsModel([_item("a")])),),
    )
    ui = PluginUiModel()
    ui.register([disabled])

    assert ui.property("active") is False
    assert ui.property("waitingGroups") == []
    assert ui.property("waitingCount") == 0


# ------------------------------------------------------------------------ the dialogs


def test_a_dialog_needs_an_identifier_and_an_existing_qml_file(qapp, tmp_path: Path) -> None:
    content = tmp_path / "dialog.qml"
    content.write_text("import QtQuick\nItem {}\n", encoding="utf-8")
    check_contributions("pl", [PluginDialog("note", content)])
    with pytest.raises(ValueError, match="does not exist"):
        check_contributions("pl", [PluginDialog("note", tmp_path / "missing.qml")])
    with pytest.raises(ValueError, match="lowercase snake_case"):
        check_contributions("pl", [PluginDialog("Note", content)])
    with pytest.raises(ValueError, match="declared twice"):
        check_contributions("pl", [PluginDialog("note", content), PluginDialog("note", content)])


def test_a_dialog_width_is_480_by_default_and_320_to_640_otherwise(tmp_path: Path) -> None:
    content = tmp_path / "dialog.qml"
    content.write_text("import QtQuick\nItem {}\n", encoding="utf-8")
    assert PluginDialog("note", content).width == 480
    for width in (320, 640):
        check_contributions("pl", [PluginDialog("note", content, width=width)])
    for width in (319, 641, 700, 480.0, True):
        with pytest.raises(ValueError, match="must be a whole number of pixels from 320 to 640"):
            check_contributions("pl", [PluginDialog("note", content, width=width)])  # type: ignore[arg-type]


def test_a_dialog_request_reaches_the_window_only_for_a_known_dialog(qapp, tmp_path: Path) -> None:
    content = tmp_path / "dialog.qml"
    content.write_text("import QtQuick\nItem {}\n", encoding="utf-8")
    backend = QObject()
    running = LoadedPlugin(
        DiscoveredPlugin("pl", Path("."), Path("."), None),
        PluginStatus.RUNNING,
        contributions=(PluginDialog("note", content, backend=backend),),
    )
    ui = PluginUiModel()
    ui.register([running])
    asked: list[tuple[str, str]] = []
    ui.dialogRequested.connect(lambda key, ref: asked.append((key, ref)))

    ui.open_dialog("pl.note", "ref one")
    ui.open_dialog("pl.other", "ignored")

    assert asked == [("pl.note", "ref one")]
    assert ui.dialogQml("pl.note").endswith("dialog.qml")
    assert ui.dialogQml("pl.other") == ""
    assert ui.dialogBackend("pl.note") is backend
    assert backend.parent() is ui  # owned by the model, never by the QML


def test_rows_say_which_list_they_belong_to() -> None:
    seen: list[tuple[object, object]] = []

    def value(row: Any) -> CellValue:
        seen.append((row["tabKind"], row["tabRef"]))
        return CellValue("Local")

    rows = decorate_rows([{"id": "a"}], [_column(value_fn=value)], "playlist", "p-1")

    assert seen == [("playlist", "p-1")]
    assert rows[0]["tabKind"] == "playlist" and rows[0]["tabRef"] == "p-1"


# ------------------------------------------------- the sidebar fields (counts, text, fold)


def test_the_optional_sidebar_fields_default_to_the_old_behaviour() -> None:
    action = PaneAction("go", "Go", "repeat", _noop)
    section = SidebarSection("s", "S", "playlists", PluginRowsModel())
    activity = PluginActivity("main", "Pl", "music")

    assert action.label == "" and action.visible is None
    assert section.on_fold is None and section.count is None and section.expanded is True
    assert activity.badge is None


def test_the_optional_sidebar_fields_are_accepted_when_valid(qapp) -> None:
    model = PluginRowsModel()
    check_contributions(
        "pl",
        [
            PluginActivity(
                "main",
                "Pl",
                "music",
                (PaneAction("text", "Text", "check", _noop, label="Apply", visible=lambda: True),),
                badge=lambda: 2,
            ),
            SidebarSection(
                "lists",
                "Lists",
                "main",
                model,
                on_fold=lambda row_id, expanded: None,
                count=lambda: 3,
                expanded=lambda: False,
            ),
            SidebarSection("side", "Side", "main", model, expanded=False),
        ],
    )


def test_the_counts_badges_and_visibilities_are_read_on_registration_and_refresh(qapp) -> None:
    state = {"count": 1, "shown": True}
    ui, _ = _ui(
        [
            PluginActivity(
                "main",
                "Pl",
                "music",
                (
                    PaneAction(
                        "apply",
                        "Apply",
                        "check",
                        _noop,
                        label="Apply",
                        visible=lambda: state["shown"],
                    ),
                ),
                badge=lambda: state["count"],
            ),
            SidebarSection(
                "lists",
                "Lists",
                "main",
                PluginRowsModel(),
                count=lambda: state["count"],
                actions=(PaneAction("sync", "Sync", "repeat", _noop, visible=lambda: False),),
            ),
        ]
    )

    assert ui.activityBadge("pl.main", ui.revision) == 1
    assert ui.sectionCount("pl.lists", ui.revision) == 1
    assert ui.actionShown("activity:pl.main", "apply", ui.revision) is True
    assert ui.actionShown("section:pl.lists", "sync", ui.revision) is False

    state.update(count=0, shown=False)
    # Nothing is read again until the plugin calls refresh_ui.
    assert ui.activityBadge("pl.main", ui.revision) == 1
    ui.refresh()
    assert ui.activityBadge("pl.main", ui.revision) == 0
    assert ui.sectionCount("pl.lists", ui.revision) == 0
    assert ui.actionShown("activity:pl.main", "apply", ui.revision) is False


def test_a_button_without_visibility_is_shown_and_a_failing_one_is_hidden(qapp) -> None:
    def explodes() -> bool:
        raise RuntimeError("no data")

    ui, notices = _ui(
        [
            PluginActivity(
                "main",
                "Pl",
                "music",
                (
                    PaneAction("plain", "Plain", "repeat", _noop),
                    PaneAction("broken", "Broken", "repeat", _noop, visible=explodes),
                ),
                badge=lambda: int(1 / 0),  # a failing count is 0
            ),
        ]
    )

    assert ui.actionShown("activity:pl.main", "plain", ui.revision) is True
    assert ui.actionShown("activity:pl.main", "broken", ui.revision) is False
    assert ui.activityBadge("pl.main", ui.revision) == 0
    assert len(notices) == 2 and all("pl" in notice for notice in notices)


def test_the_label_of_a_pane_action_is_read_by_the_activity_info(qapp) -> None:
    ui, _ = _ui(
        [
            PluginActivity(
                "main",
                "Pl",
                "music",
                (PaneAction("apply", "Apply", "check", _noop, label="Apply"),),
            ),
        ]
    )

    info = ui.activityInfo("pl.main")
    assert info["actions"] == [{"id": "apply", "tip": "Apply", "icon": "check", "label": "Apply"}]


def test_a_group_name_click_calls_activate_and_a_chevron_calls_on_fold(qapp) -> None:
    opened: list[str] = []
    folded: list[tuple[str, bool]] = []

    def activate(row_id: str) -> TabRequest | None:
        opened.append(row_id)
        return TabRequest("pl.list", row_id)

    ui, _ = _ui(
        [
            _kind(),
            SidebarSection(
                "lists",
                "Lists",
                "main",
                PluginRowsModel(),
                activate=activate,
                on_fold=lambda row_id, expanded: folded.append((row_id, expanded)),
            ),
            PluginActivity("main", "Pl", "music"),
        ]
    )

    ui.activateRow("pl.lists", "group")
    ui.foldRow("pl.lists", "group", False)
    ui.foldRow("pl.lists", "group", True)
    assert opened == ["group"]
    assert folded == [("group", False), ("group", True)]


def test_a_section_starts_by_its_expanded_value_and_a_failing_one_starts_expanded(qapp) -> None:
    def explodes() -> bool:
        raise RuntimeError("no library")

    ui, notices = _ui(
        [
            PluginActivity("main", "Pl", "music"),
            SidebarSection("a", "A", "main", PluginRowsModel(), expanded=False),
            SidebarSection("b", "B", "main", PluginRowsModel(), expanded=lambda: False),
            SidebarSection("c", "C", "main", PluginRowsModel(), expanded=explodes),
            SidebarSection("d", "D", "main", PluginRowsModel()),
        ]
    )

    assert ui.sectionStartsExpanded("pl.a") is False
    assert ui.sectionStartsExpanded("pl.b") is False
    assert ui.sectionStartsExpanded("pl.c") is True
    assert ui.sectionStartsExpanded("pl.d") is True
    assert ui.sectionStartsExpanded("pl.missing") is True
    assert len(notices) == 1

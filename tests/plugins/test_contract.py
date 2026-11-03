"""The contract tests every plugin passes (docs/plugins.md, section 8).

They run against the sample plugin (``tests/plugins/sample``) and against any other plugin you
point them at. To run them on a plugin that lives elsewhere, give the folder that holds its
package (the folder passed to ``--plugin-dir``)::

    MTEE_CONTRACT_PLUGIN_DIRS=path/to/plugins uv run pytest tests/plugins/test_contract.py

Every plugin package with a valid manifest in those folders (separate several with the
operating system's path separator) is tested next to the sample. A plugin test module may also
define its own ``pytest_generate_tests`` that parametrizes ``plugin`` with a ``ContractPlugin``
and import the ``test_*`` functions from here.

The plugin runs against permissive fakes of the core services, so its factory and its
contributions are checked without a window. What a plugin shows in the real window is checked
by the UI tests (``test_sample_ui.py`` for the sample).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import mtee.plugins
from mtee.models.plugin_ui_model import PluginUiModel
from mtee.persistence.database import Database, discover_migrations
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import (
    DeleteChoices,
    LibraryTrack,
    PaneAction,
    PluginActivity,
    PluginContext,
    PluginManifest,
    StartupTask,
    StatusItem,
    TabKind,
    TrackAvailability,
    TrackSource,
)
from mtee.plugins.loader import (
    LoadedPlugin,
    PluginManager,
    PluginPreferences,
    PluginStatus,
    discover,
)

CONTRACT_DIRS_ENVIRONMENT = "MTEE_CONTRACT_PLUGIN_DIRS"
_HERE = Path(__file__).parent


@dataclass(frozen=True)
class ContractPlugin:
    """A plugin under test: its id and the plugin folder that holds its package."""

    plugin_id: str
    folder: Path

    @property
    def package_dir(self) -> Path:
        return self.folder / self.plugin_id


SAMPLE = ContractPlugin("sample", _HERE)
FAILING = ContractPlugin("sample_failing", _HERE)


def contract_plugins() -> list[ContractPlugin]:
    """Return the sample plugin and the plugins found in ``MTEE_CONTRACT_PLUGIN_DIRS``.

    The failing sample is a tool of the tests, not a plugin under test; it is left out.
    """
    plugins = [SAMPLE]
    for entry in os.environ.get(CONTRACT_DIRS_ENVIRONMENT, "").split(os.pathsep):
        if not entry.strip():
            continue
        for found in discover([Path(entry)]):
            if found.is_valid and found.plugin_id not in (SAMPLE.plugin_id, FAILING.plugin_id):
                plugins.append(ContractPlugin(found.plugin_id, found.folder))
    return plugins


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "plugin" in metafunc.fixturenames:
        plugins = contract_plugins()
        metafunc.parametrize("plugin", plugins, ids=[item.plugin_id for item in plugins])


# ----------------------------------------------------------------------------- the harness


class _DictSettings:
    """The plugin settings of a test: a plain dictionary."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def get(self, key: str, default: str | None = None) -> str | None:
        value = self.values.get(key, default)
        return value if isinstance(value, str) or value is None else default

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def get_json(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set_json(self, key: str, value: Any) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class Harness:
    """A plugin manager over a temporary database, with contexts built from fakes.

    The library, playlists, jobs and files services are permissive mocks: a factory may call
    them while it starts. ``database`` is real, so migrations and tables are real.
    """

    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "mtee.sqlite3")
        self.database.migrate()
        self.preferences = PluginPreferences(SettingsRepository(self.database))
        self.notices: list[str] = []
        self.manager = PluginManager(self.preferences, notify=self.notices.append)
        self.library = MagicMock()
        self.playlists = MagicMock()
        self.files = MagicMock()
        self.status_bar = MagicMock()
        self.track_sources = MagicMock()
        self.track_sources.list.return_value = []  # no track of its own: every track is local
        self.gui_calls: list[Callable[[], None]] = []

    def run_gui_calls(self) -> None:
        """Run what the plugin queued with ``run_on_gui``, as the graphical thread would."""
        queued, self.gui_calls = self.gui_calls, []
        for call in queued:
            call()

    def context(self, manifest: PluginManifest) -> PluginContext:
        return PluginContext(
            plugin_id=manifest.plugin_id,
            database=self.database,
            library=self.library,
            playlists=self.playlists,
            jobs=MagicMock(),
            files=self.files,
            settings=_DictSettings(),
            base_dir=self.base / "plugin-data" / manifest.plugin_id,
            notify=self.notices.append,
            log=logging.getLogger(f"mtee.plugins.{manifest.plugin_id}"),
            run_on_gui=self.gui_calls.append,
            track_sources=self.track_sources,
            status_item=self.status_bar,
        )

    def stage(self, *plugins: ContractPlugin) -> Path:
        """Copy the packages of ``plugins`` into a fresh plugin folder and return it."""
        folder = self.base / f"plugins_{len(list(self.base.glob('plugins_*')))}"
        folder.mkdir()
        for plugin in plugins:
            shutil.copytree(
                plugin.package_dir,
                folder / plugin.plugin_id,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        return folder

    def start(self, folder: Path, *enabled: str) -> dict[str, LoadedPlugin]:
        """Load the plugins of ``folder`` with ``enabled`` switched on; return the records."""
        for plugin_id in enabled:
            self.preferences.set_enabled(plugin_id, True)
        records = self.manager.load_enabled(self.context, [folder])
        return {record.plugin_id: record for record in records}

    def close(self) -> None:
        self.manager.unload_all()
        self.database.close()


@pytest.fixture
def harness(qapp, tmp_path: Path) -> Iterator[Harness]:
    created = Harness(tmp_path)
    yield created
    created.close()


def _imported(plugin_id: str) -> bool:
    return f"mtee.plugins.{plugin_id}" in sys.modules


def _tables(database: Database) -> set[str]:
    rows = database.connection().execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {str(row["name"]) for row in rows}


def _core_history(database: Database) -> list[tuple[int, str]]:
    rows = database.connection().execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    )
    return [(int(row[0]), str(row[1])) for row in rows]


def _plugin_history(database: Database, plugin_id: str) -> list[tuple[int, str]]:
    rows = database.connection().execute(
        "SELECT version, name FROM plugin_migrations WHERE plugin_id = ? ORDER BY version",
        (plugin_id,),
    )
    return [(int(row[0]), str(row[1])) for row in rows]


def surface(ui: PluginUiModel, tab_kinds: list[str]) -> dict[str, Any]:
    """Return what the core would draw for the plugins registered in ``ui``.

    The keys are the places the interface reads: activity buttons, sections of the Explorer
    and Playlists sidebars and of each plugin activity, Settings pages, column picker entries,
    the groups of the Tasks page ("Waiting for you") and the plugin tab kinds among
    ``tab_kinds``. An empty value means nothing is shown.
    """
    activities = ui.property("activities")
    sections = {
        activity: ui.sections(activity)
        for activity in ("explorer", "playlists", *(item["id"] for item in activities))
    }
    return {
        "activities": activities,
        "sections": {key: value for key, value in sections.items() if value},
        "settings pages": ui.property("settingsPages"),
        "columns": ui.property("columnOptions"),
        "waiting groups": ui.property("waitingGroups"),
        "tab kinds": [kind for kind in tab_kinds if ui.is_plugin_kind(kind)],
    }


# ----------------------------------------------------------------------------- the contract


def test_it_loads_and_unloads_cleanly(harness: Harness, plugin: ContractPlugin) -> None:
    folder = harness.stage(plugin)

    record = harness.start(folder, plugin.plugin_id)[plugin.plugin_id]

    assert record.status is PluginStatus.RUNNING, record.error
    assert record.error == ""
    assert record.service is not None
    assert record.contributions  # it adds something; the core checked every contribution
    assert _imported(plugin.plugin_id)
    assert harness.notices == []
    assert str(folder) in mtee.plugins.__path__

    harness.manager.unload_all()

    assert record.status is PluginStatus.DISABLED
    assert record.service is None
    assert record.contributions == ()
    assert not _imported(plugin.plugin_id)
    assert str(folder) not in mtee.plugins.__path__
    harness.manager.unload_all()  # unloading twice is harmless

    again = harness.manager.load_enabled(harness.context, [folder])
    assert {item.plugin_id: item.status for item in again}[plugin.plugin_id] is (
        PluginStatus.RUNNING
    )


def test_a_load_failure_disables_only_that_plugin(harness: Harness, plugin: ContractPlugin) -> None:
    folder = harness.stage(plugin, FAILING)

    records = harness.start(folder, plugin.plugin_id, FAILING.plugin_id)

    assert records[plugin.plugin_id].status is PluginStatus.RUNNING
    failed = records[FAILING.plugin_id]
    assert failed.status is PluginStatus.FAILED
    assert failed.error == "RuntimeError: The sample plugin was made to fail."
    assert failed.service is None and failed.contributions == ()
    assert not _imported(FAILING.plugin_id)
    # One notice names the plugin that failed; the other plugin is not mentioned.
    assert len(harness.notices) == 1
    assert "Sample plugin (fails)" in harness.notices[0]


_BROKEN = """
class Service:
    def contributions(self):
        return [object()]

    def unload(self):
        pass


def create(context):
    return Service()
"""


def test_a_broken_contribution_disables_only_that_plugin(
    harness: Harness, plugin: ContractPlugin
) -> None:
    folder = harness.stage(plugin)
    broken = folder / "broken_one"
    broken.mkdir()
    (broken / "__init__.py").write_text(textwrap.dedent(_BROKEN), encoding="utf-8")
    (broken / "manifest.py").write_text(
        textwrap.dedent(
            """
            from mtee.plugins.api import PluginManifest

            MANIFEST = PluginManifest(
                plugin_id="broken_one", title="Broken one", description="", version="1",
                api_version=1, factory="mtee.plugins.broken_one:create",
            )
            """
        ),
        encoding="utf-8",
    )

    records = harness.start(folder, plugin.plugin_id, "broken_one")

    assert records[plugin.plugin_id].status is PluginStatus.RUNNING
    assert records["broken_one"].status is PluginStatus.FAILED
    assert "not a Contribution" in records["broken_one"].error
    assert len(harness.notices) == 1 and "Broken one" in harness.notices[0]


def _migrations(plugin: ContractPlugin) -> list[Any]:
    directory = plugin.package_dir / "migrations"
    if not directory.is_dir():
        pytest.skip(f"{plugin.plugin_id} has no migrations")
    return discover_migrations(directory)


def _check_applied(database: Database, plugin: ContractPlugin, migrations: list[Any]) -> None:
    core_before = _core_history(database)
    tables_before = _tables(database)

    applied = database.migrate_plugin(plugin.plugin_id, migrations)

    assert [item.version for item in applied] == [item.version for item in migrations]
    assert _plugin_history(database, plugin.plugin_id) == [
        (item.version, item.name) for item in migrations
    ]
    # Table names start with the plugin id, so two plugins never collide.
    created = _tables(database) - tables_before
    assert created, "the migrations create no table"
    assert all(name.startswith(f"{plugin.plugin_id}_") for name in created), sorted(created)
    # The core history is left as it was, and a second run has nothing to apply.
    assert _core_history(database) == core_before
    assert database.migrate_plugin(plugin.plugin_id, migrations) == []


def test_its_migrations_apply_on_an_empty_database(tmp_path: Path, plugin: ContractPlugin) -> None:
    migrations = _migrations(plugin)
    database = Database(tmp_path / "empty.sqlite3")
    database.migrate()
    try:
        _check_applied(database, plugin, migrations)
    finally:
        database.close()


def test_its_migrations_apply_on_a_copy_of_a_current_database(
    tmp_path: Path, plugin: ContractPlugin
) -> None:
    migrations = _migrations(plugin)
    source = Database(tmp_path / "current.sqlite3")
    source.migrate()
    version = source.schema_version()
    SettingsRepository(source).set("contract.marker", "kept")
    source.close()
    copy = tmp_path / "copy.sqlite3"
    shutil.copy2(tmp_path / "current.sqlite3", copy)

    database = Database(copy)
    try:
        database.migrate()  # a current database has nothing left to apply
        assert database.schema_version() == version
        _check_applied(database, plugin, migrations)
        assert database.schema_version() == version
        assert SettingsRepository(database).get("contract.marker") == "kept"
    finally:
        database.close()


def _record_of(harness: Harness, folder: Path, plugin_id: str, *, enabled: bool) -> LoadedPlugin:
    if not enabled:
        harness.preferences.set_enabled(plugin_id, False)
    return harness.start(folder, *([plugin_id] if enabled else []))[plugin_id]


def test_its_ui_entries_are_hidden_when_it_is_disabled(
    harness: Harness, plugin: ContractPlugin
) -> None:
    folder = harness.stage(plugin)
    running = _record_of(harness, folder, plugin.plugin_id, enabled=True)
    assert running.status is PluginStatus.RUNNING, running.error
    kinds = [item.kind for item in running.contributions if isinstance(item, TabKind)]
    shown = PluginUiModel()
    shown.register([running])
    assert shown.property("active") is True
    assert any(shown_value for shown_value in surface(shown, kinds).values())

    # Switched off: the next start lists the plugin, imports nothing, and draws nothing.
    harness.manager.unload_all()
    assert not _imported(plugin.plugin_id)
    disabled = _record_of(harness, folder, plugin.plugin_id, enabled=False)
    assert disabled.status is PluginStatus.DISABLED
    assert disabled.contributions == ()
    assert not _imported(plugin.plugin_id)
    hidden = PluginUiModel()
    hidden.register([disabled])
    assert hidden.property("active") is False
    assert not any(surface(hidden, kinds).values())
    assert harness.notices == []


def test_its_library_scan_hooks_take_the_scanned_folder_and_fail_nothing(
    harness: Harness, plugin: ContractPlugin, tmp_path: Path
) -> None:
    folder = harness.stage(plugin)
    running = _record_of(harness, folder, plugin.plugin_id, enabled=True)
    assert running.status is PluginStatus.RUNNING, running.error
    shown = PluginUiModel()
    notices: list[str] = []
    shown.noticeRaised.connect(notices.append)
    shown.register([running])

    shown.library_scanned(tmp_path / "music")  # a plugin without a hook is simply not called
    harness.run_gui_calls()

    assert notices == []
    assert harness.notices == []


def test_its_waiting_items_are_complete_and_hidden_with_the_plugin(
    harness: Harness, plugin: ContractPlugin
) -> None:
    folder = harness.stage(plugin)
    running = _record_of(harness, folder, plugin.plugin_id, enabled=True)
    assert running.status is PluginStatus.RUNNING, running.error
    shown = PluginUiModel()
    shown.register([running])

    for group in shown.property("waitingGroups"):
        assert group["title"].strip()
        model = shown.waitingModel(group["key"])
        assert model is not None
        for row in range(model.rowCount()):
            item = model.data(model.index(row, 0))
            if isinstance(item, dict):  # a PluginRowsModel: the fields the Tasks page reads
                assert item.get("id") and item.get("title"), item
    assert shown.property("waitingCount") == sum(
        shown.waitingModel(group["key"]).rowCount() for group in shown.property("waitingGroups")
    )
    harness.manager.unload_all()
    disabled = _record_of(harness, folder, plugin.plugin_id, enabled=False)
    hidden = PluginUiModel()
    hidden.register([disabled])
    assert hidden.property("waitingGroups") == [] and hidden.property("waitingCount") == 0


_TRIPWIRE = """
from pathlib import Path as _Path

_Path({marker!r}).write_text("imported", encoding="utf-8")
"""


def _stage_with_tripwire(harness: Harness, plugin: ContractPlugin, api_version: int) -> Path:
    """Stage ``plugin`` with ``api_version`` in its manifest and a marker file written on import."""
    folder = harness.stage(plugin)
    package = folder / plugin.plugin_id
    manifest = package / "manifest.py"
    text = manifest.read_text(encoding="utf-8")
    changed = re.sub(r"api_version\s*=\s*\d+", f"api_version={api_version}", text)
    assert changed != text or f"api_version={api_version}" in text, "no api_version to change"
    manifest.write_text(changed, encoding="utf-8")
    marker = harness.base / f"imported_{api_version}.txt"
    # The factory module is the package or a module inside it; both run the package first.
    init = package / "__init__.py"
    init.write_text(
        init.read_text(encoding="utf-8") + "\n" + _TRIPWIRE.format(marker=str(marker)),
        encoding="utf-8",
    )
    return folder


def test_a_refused_manifest_never_imports_the_factory_module(
    harness: Harness, plugin: ContractPlugin
) -> None:
    # Control: with a supported api_version the same package is imported and the marker written.
    accepted = _stage_with_tripwire(harness, plugin, 1)
    record = harness.start(accepted, plugin.plugin_id)[plugin.plugin_id]
    assert record.status is PluginStatus.RUNNING, record.error
    assert (harness.base / "imported_1.txt").is_file()
    harness.manager.unload_all()

    # An api_version this MTEE does not support: refused before any import.
    refused = _stage_with_tripwire(harness, plugin, 99)
    record = harness.start(refused, plugin.plugin_id)[plugin.plugin_id]
    assert record.status is PluginStatus.FAILED
    assert "plugin interface 99" in record.error
    assert not (harness.base / "imported_99.txt").exists()
    assert not _imported(plugin.plugin_id)
    assert record.service is None and record.contributions == ()


def test_contract_plugins_know_their_folder() -> None:
    """The helper that parametrizes the tests lists the sample and what the environment adds."""
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv(CONTRACT_DIRS_ENVIRONMENT, raising=False)
        assert contract_plugins() == [SAMPLE]
        patch.setenv(CONTRACT_DIRS_ENVIRONMENT, str(_HERE))
        listed = [item.plugin_id for item in contract_plugins()]
    assert listed == ["sample"]  # the sample is listed once; the failing sample is left out


# ------------------------------------------------------- the sample and the optional capabilities


def _sample_events() -> list[str]:
    module = sys.modules[f"mtee.plugins.{SAMPLE.plugin_id}"]
    return module.EVENTS


def _pane_action(record: LoadedPlugin, action_id: str) -> PaneAction:
    for item in record.contributions:
        if isinstance(item, PluginActivity):
            for action in item.actions:
                if action.action_id == action_id:
                    return action
    raise AssertionError(f"the sample has no pane action {action_id}")


def test_the_sample_queues_work_for_the_graphical_thread_with_run_on_gui(
    harness: Harness,
) -> None:
    folder = harness.stage(SAMPLE)
    record = harness.start(folder, SAMPLE.plugin_id)[SAMPLE.plugin_id]
    startup = next(item for item in record.contributions if isinstance(item, StartupTask))
    events = _sample_events()
    events.clear()

    startup.run(MagicMock())  # the startup job, here on the calling thread

    assert events == ["startup"]  # the last step waits for the graphical thread
    assert len(harness.gui_calls) == 1
    harness.run_gui_calls()
    assert events == ["startup", "gui"]


def test_the_sample_hears_a_finished_scan_only_while_it_runs(
    harness: Harness, tmp_path: Path
) -> None:
    folder = harness.stage(SAMPLE)
    running = harness.start(folder, SAMPLE.plugin_id)[SAMPLE.plugin_id]
    events = _sample_events()
    events.clear()
    shown = PluginUiModel()
    shown.register([running])

    shown.library_scanned(tmp_path / "music")

    assert events == ["scanned music"]
    # Switched off: the next start registers no hook, so nothing is called.
    harness.manager.unload_all()
    disabled = _record_of(harness, folder, SAMPLE.plugin_id, enabled=False)
    events.clear()
    none = PluginUiModel()
    none.register([disabled])
    none.library_scanned(tmp_path / "music")
    assert events == []


def test_the_sample_imports_a_file_and_asks_for_a_playlist_name_through_the_context(
    harness: Harness, tmp_path: Path
) -> None:
    folder = harness.stage(SAMPLE)
    record = harness.start(folder, SAMPLE.plugin_id)[SAMPLE.plugin_id]
    library_folder = tmp_path / "music"
    library_folder.mkdir()
    track = library_folder / "first.wav"
    track.write_bytes(b"audio")
    harness.library.track_ids.return_value = ["t1", "t2"]
    harness.library.tracks.return_value = [
        LibraryTrack("t1", track, "First", ("Ann",), "", 1_000_000, True)
    ]
    harness.files.import_file.side_effect = lambda source, target: target / source.name
    harness.playlists.create.return_value = "p1"
    harness.playlists.name.side_effect = lambda identity: (
        "Sample playlist" if identity == "p1" else None
    )
    harness.playlists.exists.side_effect = lambda identity: identity == "p1"
    events = _sample_events()
    events.clear()

    _pane_action(record, "import").run()
    _pane_action(record, "playlist").run()

    source, target = harness.files.import_file.call_args.args
    assert source == harness.base / "plugin-data" / SAMPLE.plugin_id / "incoming" / "imported.wav"
    assert target == library_folder / "Imported"
    harness.library.rescan.assert_called_once_with(library_folder / "Imported")
    assert events == ["imported imported.wav", "playlist Sample playlist True None False"]


def test_the_sample_lists_what_waits_for_the_user_and_answers_it(harness: Harness) -> None:
    folder = harness.stage(SAMPLE)
    record = harness.start(folder, SAMPLE.plugin_id)[SAMPLE.plugin_id]
    shown = PluginUiModel()
    shown.register([record])
    tabs: list[tuple[str, str]] = []
    shown.tabRequested.connect(lambda kind, ref: tabs.append((kind, ref)))
    events = _sample_events()
    events.clear()

    assert shown.property("waitingGroups") == [
        {"key": "sample.waiting", "title": "Waiting for you", "plugin": "Sample plugin"}
    ]
    assert shown.property("waitingCount") == 2
    shown.runWaiting("sample.waiting", "w1")
    shown.dismissWaiting("sample.waiting", "w1")

    assert tabs == [("sample.list", "missing")]
    assert events == ["pick w1", "dismiss w1"]
    assert shown.property("waitingCount") == 1
    shown.dismissWaiting("sample.waiting", "w2")
    assert shown.property("waitingCount") == 0  # an empty group is not drawn


def test_the_sample_declares_each_optional_capability_once(harness: Harness) -> None:
    """The sample uses the track source, availability, status item and delete choices (125)."""
    folder = harness.stage(SAMPLE)
    record = harness.start(folder, SAMPLE.plugin_id)[SAMPLE.plugin_id]
    assert record.status is PluginStatus.RUNNING, record.error
    for kind in (TrackSource, TrackAvailability, StatusItem, DeleteChoices):
        assert sum(isinstance(item, kind) for item in record.contributions) == 1, kind.__name__
    # The status item shows its first text as the plugin starts.
    harness.status_bar.update.assert_called_once_with("Sample: ready")
    # The delete choice is offered for any selection; pressing it is tested in test_delete_choices.
    choices = next(item for item in record.contributions if isinstance(item, DeleteChoices))
    assert [choice.choice_id for choice in choices.offer(["t1"])] == ["log_only"]
    # Availability: a track the plugin does not provide is local, so nothing is reported remote.
    availability = next(
        item for item in record.contributions if isinstance(item, TrackAvailability)
    )
    assert availability.status(["t1", "t2"]) == {}
    _sample_events().clear()

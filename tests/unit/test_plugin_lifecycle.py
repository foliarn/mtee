"""Plugin lifecycle: load, register, unload, and the isolation of a failing plugin."""

from __future__ import annotations

import logging
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

import mtee.plugins
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import PluginContext, PluginManifest
from mtee.plugins.loader import PluginManager, PluginPreferences, PluginStatus

_HEADER = """
from mtee.plugins.api import Contribution, PluginManifest

MANIFEST = PluginManifest(
    plugin_id={plugin_id!r},
    title={title!r},
    description="A sample plugin.",
    version="1.0.0",
    api_version=1,
    factory="mtee.plugins.{plugin_id}:create",
)
"""

_CLEAN_SERVICE = """
from mtee.plugins.api import Contribution


def _record(context, event):
    with (context.data_dir / "events.txt").open("a", encoding="utf-8") as events:
        events.write(event + "\\n")


class Service:
    def __init__(self, context):
        self.context = context

    def contributions(self):
        return [Contribution()]

    def unload(self):
        _record(self.context, "unload")


def create(context):
    _record(context, "create")
    return Service(context)
"""


def _plugin(
    folder: Path,
    plugin_id: str,
    init: str = _CLEAN_SERVICE,
    *,
    title: str | None = None,
    migrations: dict[str, str] | None = None,
) -> Path:
    package = folder / plugin_id
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(textwrap.dedent(init), encoding="utf-8")
    manifest = _HEADER.format(plugin_id=plugin_id, title=title or plugin_id.title())
    (package / "manifest.py").write_text(manifest, encoding="utf-8")
    if migrations:
        (package / "migrations").mkdir()
        for name, sql in migrations.items():
            (package / "migrations" / name).write_text(sql, encoding="utf-8")
    return package


class _Harness:
    """A manager over a temporary database, with contexts built from fakes."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "mtee.sqlite3")
        self.database.migrate()
        self.preferences = PluginPreferences(SettingsRepository(self.database))
        self.notices: list[str] = []
        self.manager = PluginManager(self.preferences, notify=self.notices.append)
        self.built: list[str] = []

    def context(self, manifest: PluginManifest) -> PluginContext:
        self.built.append(manifest.plugin_id)
        unused = cast(Any, None)
        return PluginContext(
            plugin_id=manifest.plugin_id,
            database=self.database,
            library=unused,
            playlists=unused,
            jobs=unused,
            files=unused,
            settings=unused,
            base_dir=self.base / "plugins" / manifest.plugin_id,
            notify=self.notices.append,
            log=logging.getLogger(f"mtee.plugins.{manifest.plugin_id}"),
        )

    def start(self, folder: Path, *enabled: str) -> dict[str, Any]:
        self.preferences.add_folders([folder])
        for plugin_id in enabled:
            self.preferences.set_enabled(plugin_id, True)
        return {record.plugin_id: record for record in self.manager.load_enabled(self.context)}

    def events(self, plugin_id: str) -> list[str]:
        path = self.base / "plugins" / plugin_id / "events.txt"
        return path.read_text(encoding="utf-8").split() if path.is_file() else []


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[_Harness]:
    before = list(mtee.plugins.__path__)
    created = _Harness(tmp_path)
    yield created
    created.manager.unload_all()
    created.database.close()
    mtee.plugins.__path__[:] = before
    for name in [key for key in sys.modules if key.startswith("mtee.plugins.")]:
        if name.split(".")[2] not in {"api", "loader", "registry", "context", "conversion"}:
            del sys.modules[name]


def test_a_plugin_loads_registers_and_unloads_cleanly(harness: _Harness, tmp_path: Path) -> None:
    folder = tmp_path / "plugins_dir"
    _plugin(folder, "alpha")

    records = harness.start(folder, "alpha")

    alpha = records["alpha"]
    assert alpha.status is PluginStatus.RUNNING
    assert alpha.error == ""
    assert len(alpha.contributions) == 1
    assert harness.events("alpha") == ["create"]
    assert harness.notices == []
    assert str(folder) in mtee.plugins.__path__

    harness.manager.unload_all()

    assert harness.events("alpha") == ["create", "unload"]
    assert alpha.status is PluginStatus.DISABLED
    assert alpha.service is None
    assert alpha.contributions == ()
    assert "mtee.plugins.alpha" not in sys.modules
    assert str(folder) not in mtee.plugins.__path__
    harness.manager.unload_all()
    assert harness.events("alpha") == ["create", "unload"]


def test_a_plugin_can_be_loaded_again_after_it_was_unloaded(
    harness: _Harness, tmp_path: Path
) -> None:
    _plugin(tmp_path / "plugins_dir", "alpha")
    harness.start(tmp_path / "plugins_dir", "alpha")
    harness.manager.unload_all()

    records = {r.plugin_id: r for r in harness.manager.load_enabled(harness.context)}

    assert records["alpha"].status is PluginStatus.RUNNING
    assert harness.events("alpha") == ["create", "unload", "create"]


def test_a_plugin_that_is_not_enabled_is_listed_but_never_imported(
    harness: _Harness, tmp_path: Path
) -> None:
    _plugin(tmp_path / "plugins_dir", "alpha", init="raise RuntimeError('imported')")

    records = harness.start(tmp_path / "plugins_dir")

    assert records["alpha"].status is PluginStatus.DISABLED
    assert harness.built == []
    assert "mtee.plugins.alpha" not in sys.modules
    assert harness.notices == []


def test_a_factory_that_raises_disables_that_plugin_only(harness: _Harness, tmp_path: Path) -> None:
    folder = tmp_path / "plugins_dir"
    _plugin(folder, "alpha")
    _plugin(
        folder,
        "broken",
        init="def create(context):\n    raise RuntimeError('cannot reach the service')\n",
        title="Broken one",
    )
    _plugin(folder, "gamma")

    records = harness.start(folder, "alpha", "broken", "gamma")

    assert records["alpha"].status is PluginStatus.RUNNING
    assert records["gamma"].status is PluginStatus.RUNNING
    broken = records["broken"]
    assert broken.status is PluginStatus.FAILED
    assert broken.error == "RuntimeError: cannot reach the service"
    assert broken.service is None
    assert "mtee.plugins.broken" not in sys.modules
    assert harness.notices == [
        "The plugin Broken one could not start and is disabled: "
        "RuntimeError: cannot reach the service"
    ]


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("return [object()]", "Contribution 1 is a object, not a Contribution"),
        ("return 'a sidebar'", "must return a list"),
        ("return None", "must return a list"),
        ("raise ValueError('no contributions')", "ValueError: no contributions"),
    ],
)
def test_a_broken_contribution_fails_the_plugin_and_releases_it(
    harness: _Harness, tmp_path: Path, body: str, reason: str
) -> None:
    service = _CLEAN_SERVICE.replace("return [Contribution()]", body)
    _plugin(tmp_path / "plugins_dir", "alpha", init=service)

    records = harness.start(tmp_path / "plugins_dir", "alpha")

    assert records["alpha"].status is PluginStatus.FAILED
    assert reason in records["alpha"].error
    assert records["alpha"].contributions == ()
    # The service that was built is unloaded, so it releases what it opened.
    assert harness.events("alpha") == ["create", "unload"]
    assert len(harness.notices) == 1
    assert "Alpha" in harness.notices[0]


@pytest.mark.parametrize(
    "init",
    [
        "def create(context):\n    return object()\n",
        "create = 3\n",
        "def other(context):\n    return None\n",
    ],
)
def test_a_factory_that_is_missing_or_returns_no_service_fails_the_plugin(
    harness: _Harness, tmp_path: Path, init: str
) -> None:
    _plugin(tmp_path / "plugins_dir", "alpha", init=init)

    records = harness.start(tmp_path / "plugins_dir", "alpha")

    assert records["alpha"].status is PluginStatus.FAILED
    assert records["alpha"].error


def test_several_failures_are_announced_in_one_notice(harness: _Harness, tmp_path: Path) -> None:
    folder = tmp_path / "plugins_dir"
    failing = "def create(context):\n    raise RuntimeError('no')\n"
    _plugin(folder, "one", init=failing)
    _plugin(folder, "two", init=failing)
    _plugin(folder, "fine")

    records = harness.start(folder, "one", "two", "fine")

    assert records["fine"].status is PluginStatus.RUNNING
    assert harness.notices == [
        "2 plugins could not start and are disabled: One, Two. See Settings > Plugins."
    ]


def test_a_refused_manifest_is_failed_and_its_package_is_not_imported(
    harness: _Harness, tmp_path: Path
) -> None:
    folder = tmp_path / "plugins_dir"
    package = _plugin(folder, "future", init="raise RuntimeError('imported')")
    manifest = (package / "manifest.py").read_text(encoding="utf-8")
    (package / "manifest.py").write_text(manifest.replace("api_version=1", "api_version=7"))

    records = harness.start(folder)

    assert records["future"].status is PluginStatus.FAILED
    assert "interface 7" in records["future"].error
    assert "mtee.plugins.future" not in sys.modules
    assert harness.notices == []  # not enabled: listed with its reason, no notice

    harness.preferences.set_enabled("future", True)
    harness.manager.load_enabled(harness.context)
    assert len(harness.notices) == 1
    assert "future" in harness.notices[0].lower()
    assert harness.built == []


def test_the_migrations_of_a_plugin_apply_before_its_factory_runs(
    harness: _Harness, tmp_path: Path
) -> None:
    init = _CLEAN_SERVICE.replace(
        "def create(context):\n",
        "def create(context):\n"
        "    context.database.connection().execute('SELECT * FROM alpha_items')\n",
    )
    _plugin(
        tmp_path / "plugins_dir",
        "alpha",
        init=init,
        migrations={"001_items.sql": "CREATE TABLE alpha_items (id INTEGER PRIMARY KEY);"},
    )

    records = harness.start(tmp_path / "plugins_dir", "alpha")

    assert records["alpha"].status is PluginStatus.RUNNING
    rows = harness.database.connection().execute(
        "SELECT plugin_id, version, name FROM plugin_migrations"
    )
    assert [tuple(row) for row in rows] == [("alpha", 1, "items")]


def test_a_failing_migration_disables_the_plugin_and_never_runs_its_factory(
    harness: _Harness, tmp_path: Path
) -> None:
    _plugin(
        tmp_path / "plugins_dir",
        "alpha",
        migrations={"001_items.sql": "CREATE TABLE alpha_items (id INTEGER);\nSELECT * FROM nope;"},
    )

    records = harness.start(tmp_path / "plugins_dir", "alpha")

    assert records["alpha"].status is PluginStatus.FAILED
    assert "001_items.sql" in records["alpha"].error
    assert harness.events("alpha") == []
    tables = {
        row[0] for row in harness.database.connection().execute("SELECT name FROM sqlite_master")
    }
    assert "alpha_items" not in tables
    assert harness.database.connection().execute("SELECT * FROM plugin_migrations").fetchall() == []
    assert len(harness.notices) == 1


def test_a_context_that_cannot_be_built_fails_the_plugin(harness: _Harness, tmp_path: Path) -> None:
    _plugin(tmp_path / "plugins_dir", "alpha")
    harness.preferences.add_folders([tmp_path / "plugins_dir"])
    harness.preferences.set_enabled("alpha", True)

    def broken(_manifest: PluginManifest) -> PluginContext:
        raise OSError("no data directory")

    records = harness.manager.load_enabled(broken)

    assert records[0].status is PluginStatus.FAILED
    assert records[0].error == "OSError: no data directory"


def test_a_plugin_that_fails_to_unload_does_not_stop_the_others(
    harness: _Harness, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    folder = tmp_path / "plugins_dir"
    _plugin(folder, "alpha")
    stubborn = _CLEAN_SERVICE.replace(
        '        _record(self.context, "unload")', "        raise RuntimeError('stuck')"
    )
    _plugin(folder, "beta", init=stubborn)
    harness.start(folder, "alpha", "beta")

    with caplog.at_level(logging.ERROR):
        harness.manager.unload_all()

    assert harness.events("alpha") == ["create", "unload"]
    assert "did not unload cleanly" in caplog.text
    assert all(r.status is not PluginStatus.RUNNING for r in harness.manager.plugins)


def test_an_enabled_plugin_that_is_no_longer_in_a_folder_is_ignored(
    harness: _Harness, tmp_path: Path
) -> None:
    folder = tmp_path / "plugins_dir"
    folder.mkdir()
    harness.preferences.set_enabled("ghost", True)

    records = harness.start(folder)

    assert records == {}
    assert harness.notices == []
    assert harness.preferences.is_enabled("ghost")


def test_a_saved_folder_that_is_gone_is_reported_and_skipped(
    harness: _Harness, tmp_path: Path
) -> None:
    present = tmp_path / "present"
    _plugin(present, "alpha")
    gone = tmp_path / "gone"
    harness.preferences.add_folders([gone, present])
    harness.preferences.set_enabled("alpha", True)

    records = harness.manager.load_enabled(harness.context)

    assert [record.plugin_id for record in records] == ["alpha"]
    assert harness.manager.missing_folders == [gone.resolve()]


def test_the_data_directory_is_created_on_demand(harness: _Harness, tmp_path: Path) -> None:
    manifest = PluginManifest("alpha", "Alpha", "", "1", 1, "mtee.plugins.alpha:create")
    context = harness.context(manifest)

    assert not context.base_dir.exists()
    assert context.data_dir == tmp_path / "plugins" / "alpha"
    assert context.base_dir.is_dir()

"""Shared libraries of the plugins: one copy per library, and the import finder (plan 123.2).

Each test writes two plugin folders that bundle the same top-level module ``fakelib``. The plugins
are loaded by the real ``PluginManager``, so the finder is installed before their factories run.
"""

from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import mtee.plugins
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import API_VERSION, PluginContext
from mtee.plugins.libraries import (
    LibraryFinder,
    LibraryUser,
    install_finder,
    plan_libraries,
    uninstall_finder,
)
from mtee.plugins.loader import PluginManager, PluginPreferences, PluginStatus
from mtee.plugins.package import BundledLibrary, PluginDescription

_FACTORY = """\
import fakelib
import fakelib.sub

LOADED = {{"version": fakelib.VERSION, "file": fakelib.__file__, "sub": fakelib.sub.__file__}}


class Service:
    def contributions(self):
        return []

    def unload(self):
        pass


def create(context):
    RECORDS[{plugin_id!r}] = LOADED
    return Service()


RECORDS = {{}}
"""


def _plugin(
    root: Path,
    plugin_id: str,
    *,
    library_version: str,
    accepts: str,
) -> Path:
    """Write a plugin folder that bundles ``fakelib`` at ``library_version``."""
    folder = root / plugin_id
    package = folder / plugin_id
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(_FACTORY.format(plugin_id=plugin_id), encoding="utf-8")
    (package / "manifest.py").write_text(
        "from mtee.plugins.api import PluginManifest\n\n"
        "MANIFEST = PluginManifest(\n"
        f"    plugin_id={plugin_id!r},\n"
        f"    title={plugin_id!r},\n"
        '    description="A sample plugin.",\n'
        '    version="1.0.0",\n'
        f"    api_version={API_VERSION},\n"
        f"    factory={f'mtee.plugins.{plugin_id}:create'!r},\n"
        ")\n",
        encoding="utf-8",
    )
    lib = folder / "libs" / "fakelib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").write_text(f"VERSION = {library_version!r}\n", encoding="utf-8")
    (lib / "sub.py").write_text("NAME = 'sub'\n", encoding="utf-8")
    description = PluginDescription(
        id=plugin_id,
        title=f"Sample {plugin_id}",
        description="A sample plugin.",
        version="1.0.0",
        api_version=API_VERSION,
        author="",
        homepage="",
        licence="",
        uses_network=False,
        python="3.12",
        platform="win_amd64",
        mtee=">=0.1,<0.2",
        libraries=(BundledLibrary("fakelib", library_version, accepts, "MIT"),),
        top_level_modules={"fakelib": "fakelib"},
    )
    (folder / "plugin.json").write_text(description.to_json(), encoding="utf-8")
    return folder


def _context(tmp_path: Path, plugin_id: str) -> PluginContext:
    return PluginContext(
        plugin_id=plugin_id,
        database=MagicMock(),
        library=MagicMock(),
        playlists=MagicMock(),
        jobs=MagicMock(),
        files=MagicMock(),
        settings=MagicMock(),
        base_dir=tmp_path / "plugin-data" / plugin_id,
        notify=lambda text: None,
        log=logging.getLogger(f"mtee.plugins.{plugin_id}"),
    )


@pytest.fixture
def clean_imports() -> Iterator[None]:
    """Forget the test plugins, the fake library and the finder after each test."""
    before_path = list(mtee.plugins.__path__)
    before_meta = list(sys.meta_path)
    yield
    uninstall_finder()
    sys.meta_path[:] = before_meta
    mtee.plugins.__path__[:] = before_path
    for name in [key for key in sys.modules if key.split(".")[0] == "fakelib"]:
        del sys.modules[name]
    for name in [
        key for key in sys.modules if key.startswith(("mtee.plugins.alpha", "mtee.plugins.beta"))
    ]:
        del sys.modules[name]


@pytest.fixture
def manager(tmp_path: Path) -> Iterator[PluginManager]:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    preferences = PluginPreferences(SettingsRepository(database))
    preferences.set_enabled("alpha", True)
    preferences.set_enabled("beta", True)
    created = PluginManager(preferences)
    yield created
    created.unload_all()
    database.close()


def _loaded(manager: PluginManager) -> dict[str, Any]:
    return {record.plugin_id: record for record in manager.plugins}


def test_two_plugins_sharing_a_library_get_the_highest_version_both_accept(
    tmp_path: Path, clean_imports: None, manager: PluginManager
) -> None:
    folder = tmp_path / "folders"
    alpha = _plugin(folder, "alpha", library_version="1.0", accepts=">=1.0")
    beta = _plugin(folder, "beta", library_version="1.2", accepts=">=1.0")

    manager.load_enabled(lambda found: _context(tmp_path, found.plugin_id), [alpha, beta])

    records = _loaded(manager)
    assert records["alpha"].status is PluginStatus.RUNNING, records["alpha"].error
    assert records["beta"].status is PluginStatus.RUNNING, records["beta"].error
    imported = sys.modules["fakelib"]
    assert imported.VERSION == "1.2"
    assert imported.__file__ is not None and str(beta / "libs" / "fakelib") in imported.__file__
    assert str(alpha / "libs") not in " ".join(sys.path)
    sub = sys.modules["fakelib.sub"]
    assert sub.__file__ is not None and str(beta / "libs" / "fakelib") in sub.__file__


def test_incompatible_ranges_refuse_the_later_plugin_by_identifier(
    tmp_path: Path, clean_imports: None, manager: PluginManager
) -> None:
    folder = tmp_path / "folders"
    alpha = _plugin(folder, "alpha", library_version="1.0", accepts="==1.0")
    beta = _plugin(folder, "beta", library_version="1.2", accepts=">=1.2")

    manager.load_enabled(lambda found: _context(tmp_path, found.plugin_id), [alpha, beta])

    records = _loaded(manager)
    assert records["alpha"].status is PluginStatus.RUNNING, records["alpha"].error
    assert records["beta"].status is PluginStatus.FAILED
    assert records["beta"].error == (
        "Sample alpha and Sample beta need different versions of fakelib "
        "(==1.0 and >=1.2). Sample beta was not started."
    )
    assert "mtee.plugins.beta" not in sys.modules


def test_a_plugin_that_is_not_enabled_does_not_take_part_in_the_choice(
    tmp_path: Path, clean_imports: None
) -> None:
    folder = tmp_path / "folders"
    alpha = _plugin(folder, "alpha", library_version="1.0", accepts="==1.0")
    beta = _plugin(folder, "beta", library_version="1.2", accepts=">=1.2")
    database = Database(tmp_path / "other.sqlite3")
    database.migrate()
    preferences = PluginPreferences(SettingsRepository(database))
    preferences.set_enabled("alpha", True)
    manager = PluginManager(preferences)

    manager.load_enabled(lambda found: _context(tmp_path, found.plugin_id), [alpha, beta])

    records = _loaded(manager)
    assert records["alpha"].status is PluginStatus.RUNNING, records["alpha"].error
    assert records["beta"].status is PluginStatus.DISABLED
    manager.unload_all()
    database.close()


def test_the_finder_serves_only_the_top_level_names_of_chosen_libraries(
    tmp_path: Path, clean_imports: None
) -> None:
    folder = _plugin(tmp_path / "folders", "alpha", library_version="1.0", accepts=">=1.0")
    libs = folder / "libs"

    install_finder({"fakelib": libs})

    finders = [finder for finder in sys.meta_path if isinstance(finder, LibraryFinder)]
    assert len(finders) == 1
    assert finders[0].find_spec("fakelib.sub") is None
    assert finders[0].find_spec("other") is None
    assert finders[0].find_spec("fakelib") is not None
    uninstall_finder()
    assert not [finder for finder in sys.meta_path if isinstance(finder, LibraryFinder)]


def test_planning_keeps_a_library_of_one_plugin_as_it_is(tmp_path: Path) -> None:
    folder = _plugin(tmp_path / "folders", "alpha", library_version="1.0", accepts="==1.0")
    description = PluginDescription.from_json((folder / "plugin.json").read_text("utf-8"))

    plan = plan_libraries([LibraryUser("alpha", description, folder / "libs")])

    assert plan.refused == {}
    assert plan.locations == {"fakelib": folder / "libs"}


def test_a_plugin_is_imported_from_its_own_copy_when_it_is_the_only_one(
    tmp_path: Path, clean_imports: None, manager: PluginManager
) -> None:
    alpha = _plugin(tmp_path / "folders", "alpha", library_version="1.0", accepts="==1.0")
    importlib.invalidate_caches()

    manager.load_enabled(lambda found: _context(tmp_path, found.plugin_id), [alpha])

    assert _loaded(manager)["alpha"].status is PluginStatus.RUNNING
    assert sys.modules["fakelib"].VERSION == "1.0"


def test_a_bundled_module_never_shadows_one_mtee_already_has(
    tmp_path: Path, clean_imports: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A plugin bundling ``json`` (stdlib) keeps the stdlib; its unique module is served (123.7)."""
    libs = tmp_path / "libs"
    (libs / "json").mkdir(parents=True)
    (libs / "json" / "__init__.py").write_text("SHADOW = True\n", encoding="utf-8")
    (libs / "fakelib_unique").mkdir(parents=True)
    (libs / "fakelib_unique" / "__init__.py").write_text("VALUE = 'served'\n", encoding="utf-8")
    caplog.set_level(logging.INFO, logger="mtee.plugins.libraries")

    install_finder({"json": libs, "fakelib_unique": libs})
    try:
        finders = [finder for finder in sys.meta_path if isinstance(finder, LibraryFinder)]
        assert len(finders) == 1
        assert "json" not in finders[0].locations
        assert "fakelib_unique" in finders[0].locations
        json_module = importlib.import_module("json")
        unique = importlib.import_module("fakelib_unique")
    finally:
        uninstall_finder()
        sys.modules.pop("fakelib_unique", None)

    assert not hasattr(json_module, "SHADOW")
    assert json_module.__file__ is not None and str(libs) not in json_module.__file__
    assert unique.VALUE == "served"
    assert unique.__file__ is not None and str(libs / "fakelib_unique") in unique.__file__
    assert "Plugin library module json is not used: MTEE already provides it." in caplog.text
    assert "fakelib_unique is not used" not in caplog.text

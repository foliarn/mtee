"""Plugin folders: discovery by manifest, refused manifests and saved preferences."""

from __future__ import annotations

import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

import mtee.plugins
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import API_VERSION, PluginManifest
from mtee.plugins.loader import (
    PluginPreferences,
    add_to_package_path,
    discover,
    remove_from_package_path,
    split_existing_folders,
)


def _write_plugin(
    folder: Path,
    plugin_id: str,
    *,
    manifest_id: str | None = None,
    api_version: int = API_VERSION,
    factory: str | None = None,
    init: str = "",
    manifest_body: str | None = None,
) -> Path:
    """Write a plugin package whose ``__init__`` can be made to fail when imported."""
    package = folder / plugin_id
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(init, encoding="utf-8")
    declared = manifest_id or plugin_id
    factory = factory or f"mtee.plugins.{declared}:create"
    body = manifest_body or textwrap.dedent(
        f"""
        from mtee.plugins.api import PluginManifest

        MANIFEST = PluginManifest(
            plugin_id={declared!r},
            title="Sample {declared}",
            description="A sample plugin.",
            version="1.0.0",
            api_version={api_version},
            factory={factory!r},
            uses_network=True,
        )
        """
    )
    (package / "manifest.py").write_text(body, encoding="utf-8")
    return package


@pytest.fixture
def isolated_plugin_path() -> Iterator[None]:
    """Restore the import path of ``mtee.plugins`` after a test that extends it."""
    before = list(mtee.plugins.__path__)
    yield
    mtee.plugins.__path__[:] = before


def test_discovery_reads_the_manifest_of_each_package(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "alpha")
    _write_plugin(tmp_path, "beta")
    (tmp_path / "not_a_plugin").mkdir()
    (tmp_path / "loose_file.txt").write_text("x", encoding="utf-8")

    found = discover([tmp_path])

    assert [plugin.plugin_id for plugin in found] == ["alpha", "beta"]
    assert all(plugin.is_valid for plugin in found)
    manifest = found[0].manifest
    assert manifest == PluginManifest(
        "alpha", "Sample alpha", "A sample plugin.", "1.0.0", 1, "mtee.plugins.alpha:create", True
    )
    assert found[0].package_dir == tmp_path / "alpha"
    assert found[0].folder == tmp_path


def test_discovery_imports_only_the_manifest(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "gamma", init='raise RuntimeError("the package was imported")')

    found = discover([tmp_path])

    assert [plugin.is_valid for plugin in found] == [True]
    assert "mtee.plugins.gamma" not in sys.modules
    assert not [name for name in sys.modules if name.startswith("_mtee_plugin_manifest")]


def test_a_folder_that_is_missing_is_reported_and_skipped(tmp_path: Path) -> None:
    present = tmp_path / "present"
    _write_plugin(present, "alpha")
    gone = tmp_path / "gone"

    existing, missing = split_existing_folders([gone, present])

    assert existing == [present]
    assert missing == [gone]
    assert [plugin.plugin_id for plugin in discover([gone, present])] == ["alpha"]


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("Bad-Name", "snake_case"),
        ("CamelCase", "snake_case"),
        ("api", "used by MTEE itself"),
        ("registry", "used by MTEE itself"),
        ("conversion", "used by MTEE itself"),
    ],
)
def test_an_unusable_folder_name_is_refused_without_running_its_manifest(
    tmp_path: Path, name: str, reason: str
) -> None:
    marker = tmp_path / "ran"
    _write_plugin(
        tmp_path / "plugins",
        name,
        manifest_body=f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n",
    )

    (plugin,) = discover([tmp_path / "plugins"])

    assert not plugin.is_valid
    assert plugin.manifest is None
    assert reason in plugin.error
    assert not marker.exists()


def test_a_manifest_with_an_unknown_api_version_is_refused(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "future", api_version=99)

    (plugin,) = discover([tmp_path])

    assert not plugin.is_valid
    assert "interface 99" in plugin.error
    assert plugin.manifest is not None


def test_a_manifest_id_that_differs_from_the_folder_is_refused(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "alpha", manifest_id="other")

    (plugin,) = discover([tmp_path])

    assert not plugin.is_valid
    assert "differs from the folder name" in plugin.error


@pytest.mark.parametrize(
    "factory",
    ["no_separator", "mtee.plugins.alpha:", "mtee.plugins.beta:create", "os:system"],
)
def test_a_factory_outside_the_plugin_package_is_refused(tmp_path: Path, factory: str) -> None:
    _write_plugin(tmp_path, "alpha", factory=factory)

    (plugin,) = discover([tmp_path])

    assert not plugin.is_valid
    assert "factory" in plugin.error.lower()


def test_a_factory_in_a_submodule_of_the_plugin_is_accepted(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "alpha", factory="mtee.plugins.alpha.service:build")

    (plugin,) = discover([tmp_path])

    assert plugin.is_valid


def test_a_manifest_that_fails_to_load_is_refused_with_its_error(tmp_path: Path) -> None:
    _write_plugin(tmp_path, "alpha", manifest_body="raise ValueError('broken manifest')\n")
    _write_plugin(tmp_path, "beta", manifest_body="MANIFEST = 3\n")
    _write_plugin(tmp_path, "gamma", manifest_body="this is not python\n")

    plugins = {plugin.plugin_id: plugin for plugin in discover([tmp_path])}

    assert "broken manifest" in plugins["alpha"].error
    assert "PluginManifest" in plugins["beta"].error
    assert plugins["gamma"].error.startswith("The manifest cannot be loaded")
    assert not any(plugin.is_valid for plugin in plugins.values())


def test_a_package_without_init_is_refused(tmp_path: Path) -> None:
    package = _write_plugin(tmp_path, "alpha")
    (package / "__init__.py").unlink()

    (plugin,) = discover([tmp_path])

    assert not plugin.is_valid
    assert "__init__.py" in plugin.error


def test_a_duplicated_identifier_keeps_the_first_plugin_only(tmp_path: Path) -> None:
    _write_plugin(tmp_path / "one", "alpha")
    _write_plugin(tmp_path / "two", "alpha")

    first, second = discover([tmp_path / "one", tmp_path / "two"])

    assert first.is_valid
    assert not second.is_valid
    assert "already provides alpha" in second.error


def test_the_package_path_is_extended_and_restored(
    tmp_path: Path, isolated_plugin_path: None
) -> None:
    before = list(mtee.plugins.__path__)

    add_to_package_path(tmp_path)
    add_to_package_path(tmp_path)

    assert mtee.plugins.__path__ == [*before, str(tmp_path)]
    remove_from_package_path(tmp_path)
    assert mtee.plugins.__path__ == before


def test_a_plugin_is_imported_from_a_folder_added_to_the_package_path(
    tmp_path: Path, isolated_plugin_path: None
) -> None:
    import importlib

    _write_plugin(tmp_path, "importable", init="VALUE = 42\n")
    add_to_package_path(tmp_path)
    try:
        module = importlib.import_module("mtee.plugins.importable")
        assert module.VALUE == 42
    finally:
        sys.modules.pop("mtee.plugins.importable", None)


def test_preferences_save_folders_and_the_enabled_list(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    preferences = PluginPreferences(SettingsRepository(database))
    first = tmp_path / "one"
    second = tmp_path / "two"

    assert preferences.folders() == []
    assert preferences.enabled() == []
    assert preferences.add_folders([first]) == [first.resolve()]
    assert preferences.add_folders([first, second]) == [first.resolve(), second.resolve()]
    preferences.set_enabled("alpha", True)
    preferences.set_enabled("alpha", True)
    preferences.set_enabled("beta", True)
    preferences.set_enabled("alpha", False)

    again = PluginPreferences(SettingsRepository(database))
    assert again.folders() == [first.resolve(), second.resolve()]
    assert again.enabled() == ["beta"]
    assert again.is_enabled("beta")
    assert not again.is_enabled("alpha")
    again.remove_folder(first)
    assert again.folders() == [second.resolve()]
    database.close()


def test_preferences_ignore_a_stored_value_of_the_wrong_shape(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    settings = SettingsRepository(database)
    settings.set("plugins.folders", "not json")
    settings.set_json("plugins.enabled", {"alpha": True})

    preferences = PluginPreferences(settings)

    assert preferences.folders() == []
    assert preferences.enabled() == []
    database.close()


def test_reading_the_preferences_writes_nothing(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    settings = SettingsRepository(database)
    preferences = PluginPreferences(settings)

    preferences.folders()
    preferences.enabled()
    preferences.add_folders([])

    assert not any(key.startswith("plugins.") for key in settings.all())
    database.close()

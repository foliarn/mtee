"""Installing, updating and removing plugins from package files (plan 123.2).

Packages are built in a temporary folder. The trash is a fake that moves folders into a temporary
"bin" folder: no test reaches the real Recycle Bin, and the data folder is temporary too.
"""

from __future__ import annotations

import re
import shutil
import stat
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest

from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins import installer
from mtee.plugins.api import API_VERSION
from mtee.plugins.installer import (
    InstalledPlugin,
    InstallRefusedError,
    PackageInfo,
    clean_staging,
    inspect,
    install,
    installed,
    plugin_data_folder,
    plugins_folder,
    uninstall,
)
from mtee.plugins.loader import PluginPreferences
from mtee.plugins.package import BundledLibrary, PluginDescription

MTEE_VERSION = "0.1.0"
SHIPPED_REQUESTS = {"requests": "2.31.0"}


class FakeTrash:
    """Moves each folder it is given into a bin folder, and records the paths."""

    def __init__(self, bin_dir: Path) -> None:
        self.bin_dir = bin_dir
        self.sent: list[Path] = []

    def recycle_folder(self, path: Path) -> Path:
        self.sent.append(path)
        target = self.bin_dir / f"{len(self.sent)}-{path.name}"
        shutil.move(str(path), str(target))
        return target


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


@pytest.fixture
def trash(tmp_path: Path) -> FakeTrash:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    return FakeTrash(bin_dir)


@pytest.fixture
def preferences(tmp_path: Path) -> Iterator[PluginPreferences]:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    yield PluginPreferences(SettingsRepository(database))
    database.close()


def _description(
    plugin_id: str = "alpha",
    *,
    version: str = "1.0.0",
    api_version: int = API_VERSION,
    mtee: str = ">=0.1,<0.2",
    platform: str = "any",
    python: str = "3.12",
    title: str | None = None,
    libraries: Sequence[BundledLibrary] = (),
) -> PluginDescription:
    return PluginDescription(
        id=plugin_id,
        title=title or f"Sample {plugin_id}",
        description="A sample plugin.",
        version=version,
        api_version=api_version,
        author="",
        homepage="",
        licence="",
        uses_network=False,
        python=python,
        platform=platform,
        mtee=mtee,
        libraries=tuple(libraries),
        top_level_modules={},
    )


def _manifest(plugin_id: str, version: str, api_version: int) -> str:
    factory = f"mtee.plugins.{plugin_id}:create"
    return (
        "from mtee.plugins.api import PluginManifest\n\n"
        "MANIFEST = PluginManifest(\n"
        f"    plugin_id={plugin_id!r},\n"
        f"    title={plugin_id!r},\n"
        '    description="A sample plugin.",\n'
        f"    version={version!r},\n"
        f"    api_version={api_version},\n"
        f"    factory={factory!r},\n"
        ")\n"
    )


def _package(
    tmp_path: Path,
    plugin_id: str = "alpha",
    *,
    description: PluginDescription | None = None,
    name: str | None = None,
    manifest_version: str | None = None,
    libs: Mapping[str, str] | None = None,
    entries: Sequence[tuple[str, bytes, int]] = (),
    skip: Sequence[str] = (),
) -> Path:
    """Write a package file of ``plugin_id`` and return its path.

    ``libs`` maps a path inside the package to its text; ``entries`` adds raw zip entries with
    their attributes; ``skip`` leaves out the named entries.
    """
    description = description or _description(plugin_id)
    plugin_id = description.id
    folder = tmp_path / "packages"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name or plugin_id}-{description.version}.mteeplugin"
    files: dict[str, bytes] = {
        "plugin.json": description.to_json().encode("utf-8"),
        f"{plugin_id}/__init__.py": b"VALUE = 1\n",
        f"{plugin_id}/manifest.py": _manifest(
            plugin_id, manifest_version or description.version, description.api_version
        ).encode("utf-8"),
    }
    for inside, text in (libs or {}).items():
        files[inside] = text.encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for inside, data in files.items():
            if inside not in skip:
                archive.writestr(inside, data)
        for inside, data, attributes in entries:
            info = zipfile.ZipInfo(inside)
            info.external_attr = attributes
            archive.writestr(info, data)
    return path


def _inspect(
    package: Path,
    installed_plugins: Sequence[InstalledPlugin] = (),
    libraries: Mapping[str, str] | None = None,
) -> PackageInfo:
    return inspect(
        package,
        installed=installed_plugins,
        mtee_version=MTEE_VERSION,
        mtee_libraries=libraries or {},
    )


def _install(
    package: Path,
    data_dir: Path,
    trash: FakeTrash,
    preferences: PluginPreferences,
) -> InstalledPlugin:
    return install(
        package,
        data_dir=data_dir,
        trash=trash,
        preferences=preferences,
        mtee_version=MTEE_VERSION,
        mtee_libraries={},
    )


def _installed_entry(
    plugin_id: str, data_dir: Path, description: PluginDescription
) -> InstalledPlugin:
    return InstalledPlugin(plugin_id, plugins_folder(data_dir) / plugin_id, description)


def test_a_fresh_install_lands_in_the_plugins_folder_and_is_switched_on(
    tmp_path: Path, data_dir: Path, trash: FakeTrash, preferences: PluginPreferences
) -> None:
    package = _package(tmp_path)

    plugin = _install(package, data_dir, trash, preferences)

    assert plugin.folder == plugins_folder(data_dir) / "alpha"
    assert (plugin.folder / "plugin.json").is_file()
    assert (plugin.folder / "alpha" / "manifest.py").is_file()
    assert preferences.is_enabled("alpha")
    assert trash.sent == []
    assert not (plugins_folder(data_dir) / ".staging").exists()


def test_inspect_describes_the_package_and_its_size(tmp_path: Path) -> None:
    package = _package(tmp_path)

    info = _inspect(package)

    assert info.description == _description()
    assert info.size == package.stat().st_size
    assert info.replaces is False
    assert info.installed_version is None


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        ("../escape.txt", "outside its folder"),
        ("/absolute.txt", "outside its folder"),
        ("C:/drive.txt", "outside its folder"),
        ("alpha/../../escape.txt", "outside its folder"),
    ],
)
def test_an_entry_outside_the_package_is_refused(tmp_path: Path, entry: str, reason: str) -> None:
    package = _package(tmp_path, entries=[(entry, b"x", 0)])

    with pytest.raises(InstallRefusedError, match=re.escape(reason)):
        _inspect(package)


def test_a_link_is_refused(tmp_path: Path) -> None:
    link_attributes = (stat.S_IFLNK | 0o777) << 16
    package = _package(tmp_path, entries=[("alpha/link", b"target", link_attributes)])

    with pytest.raises(InstallRefusedError, match="holds a link"):
        _inspect(package)


def test_a_package_that_unpacks_to_more_than_the_limit_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installer, "MAX_UNPACKED_BYTES", 10)
    package = _package(tmp_path, libs={"libs/big/__init__.py": "x" * 100})

    with pytest.raises(InstallRefusedError, match="more than 500 MB"):
        _inspect(package)


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path) -> None:
    package = tmp_path / "broken-1.0.0.mteeplugin"
    package.write_bytes(b"not a zip")

    with pytest.raises(InstallRefusedError, match="is not a plugin package that can be read"):
        _inspect(package)


def test_a_package_without_plugin_json_is_refused(tmp_path: Path) -> None:
    package = _package(tmp_path, skip=["plugin.json"])

    with pytest.raises(InstallRefusedError, match=re.escape("no plugin.json")):
        _inspect(package)


def test_an_invalid_plugin_json_is_refused_with_its_reason(tmp_path: Path) -> None:
    package = _package(tmp_path, skip=["plugin.json"])
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("plugin.json", "{")

    with pytest.raises(InstallRefusedError, match="not valid JSON"):
        _inspect(package)


@pytest.mark.parametrize(
    ("description", "reason"),
    [
        (_description(api_version=99), "plugin interface 99"),
        (_description(python="3.11"), "built for Python 3.11"),
        (_description(platform="linux_x86_64"), "cannot load"),
        (_description(mtee=">=0.2,<0.3"), "built for MTEE >=0.2,<0.3"),
        (_description("Bad-Name"), "not lowercase snake_case"),
        (_description("api"), "used by MTEE itself"),
    ],
)
def test_a_package_that_does_not_fit_this_mtee_is_refused(
    tmp_path: Path, description: PluginDescription, reason: str
) -> None:
    package = _package(tmp_path, description=description, name=description.id)

    with pytest.raises(InstallRefusedError, match=re.escape(reason)):
        _inspect(package)


def test_a_package_without_its_manifest_is_refused(tmp_path: Path) -> None:
    package = _package(tmp_path, skip=["alpha/manifest.py"])

    with pytest.raises(InstallRefusedError, match=re.escape("no alpha/manifest.py")):
        _inspect(package)


def test_a_library_mtee_ships_is_refused_by_name(tmp_path: Path) -> None:
    requests = BundledLibrary("requests", "2.31.0", "==2.31.0", "Apache-2.0")
    package = _package(tmp_path, description=_description(libraries=[requests]))

    with pytest.raises(InstallRefusedError) as refused:
        _inspect(package, libraries=SHIPPED_REQUESTS)

    assert str(refused.value) == (
        "Sample alpha bundles requests, which MTEE already provides. Rebuild the package."
    )


def test_a_real_version_conflict_with_an_installed_plugin_is_refused_in_one_sentence(
    tmp_path: Path,
) -> None:
    spotify_requests = BundledLibrary("requests", "2.31.0", "==2.31.0", "Apache-2.0")
    loudness_requests = BundledLibrary("requests", "2.32.0", ">=2.32", "Apache-2.0")
    loudness = _description("loudness", title="Loudness report", libraries=[loudness_requests])
    installed_plugins = [_installed_entry("loudness", tmp_path, loudness)]
    package = _package(
        tmp_path,
        description=_description("spotify", title="Spotify", libraries=[spotify_requests]),
    )

    with pytest.raises(InstallRefusedError) as refused:
        _inspect(package, installed_plugins)

    assert str(refused.value) == (
        "Spotify and Loudness report need different versions of requests "
        "(==2.31.0 and >=2.32). Spotify was not installed."
    )


def test_a_shared_library_at_a_version_both_plugins_accept_is_allowed(tmp_path: Path) -> None:
    other = _description(
        "loudness",
        libraries=[BundledLibrary("requests", "2.32.0", ">=2.32", "Apache-2.0")],
    )
    installed_plugins = [_installed_entry("loudness", tmp_path, other)]
    package = _package(
        tmp_path,
        description=_description(
            "spotify",
            libraries=[BundledLibrary("requests", "2.32.0", ">=2.31", "Apache-2.0")],
        ),
    )

    info = _inspect(package, installed_plugins)

    assert info.description.id == "spotify"


def test_a_plugin_of_the_same_id_is_replaced_and_its_old_version_is_not_a_conflict(
    tmp_path: Path,
) -> None:
    old = _description(
        libraries=[BundledLibrary("requests", "2.31.0", "==2.31.0", "Apache-2.0")],
    )
    installed_plugins = [_installed_entry("alpha", tmp_path, old)]
    package = _package(
        tmp_path,
        description=_description(
            version="2.0.0",
            libraries=[BundledLibrary("requests", "2.32.0", ">=2.32", "Apache-2.0")],
        ),
    )

    info = _inspect(package, installed_plugins)

    assert info.replaces is True
    assert info.installed_version == "1.0.0"


def test_a_plugin_json_that_disagrees_with_the_manifest_is_refused_by_the_check_after_extraction(
    tmp_path: Path, data_dir: Path, trash: FakeTrash, preferences: PluginPreferences
) -> None:
    package = _package(
        tmp_path, description=_description(version="2.0.0"), manifest_version="1.0.0"
    )

    with pytest.raises(InstallRefusedError, match=re.escape("says version 2.0.0")):
        _install(package, data_dir, trash, preferences)

    assert not (plugins_folder(data_dir) / "alpha").exists()
    assert not (plugins_folder(data_dir) / ".staging").exists()
    assert not preferences.is_enabled("alpha")


def test_an_update_sends_the_old_folder_to_the_bin_and_keeps_the_switch(
    tmp_path: Path, data_dir: Path, trash: FakeTrash, preferences: PluginPreferences
) -> None:
    _install(_package(tmp_path), data_dir, trash, preferences)
    newer = _package(tmp_path, description=_description(version="2.0.0"))

    plugin = _install(newer, data_dir, trash, preferences)

    old_folder = plugins_folder(data_dir) / "alpha"
    assert trash.sent == [old_folder]
    assert (trash.bin_dir / "1-alpha").is_dir()
    assert '"version": "1.0.0"' in (trash.bin_dir / "1-alpha" / "plugin.json").read_text("utf-8")
    assert '"version": "2.0.0"' in (plugin.folder / "plugin.json").read_text("utf-8")
    assert preferences.is_enabled("alpha")


def test_an_update_of_a_plugin_switched_off_keeps_it_off(
    tmp_path: Path, data_dir: Path, trash: FakeTrash, preferences: PluginPreferences
) -> None:
    _install(_package(tmp_path), data_dir, trash, preferences)
    preferences.set_enabled("alpha", False)

    _install(
        _package(tmp_path, description=_description(version="2.0.0")), data_dir, trash, preferences
    )

    assert not preferences.is_enabled("alpha")


def test_uninstall_sends_the_folder_to_the_bin_and_keeps_the_data_and_the_tables(
    tmp_path: Path, data_dir: Path, trash: FakeTrash, preferences: PluginPreferences
) -> None:
    _install(_package(tmp_path), data_dir, trash, preferences)
    data = plugin_data_folder(data_dir, "alpha")
    data.mkdir(parents=True)
    (data / "state.txt").write_text("kept", encoding="utf-8")

    uninstall("alpha", data_dir=data_dir, trash=trash, preferences=preferences)

    assert trash.sent == [plugins_folder(data_dir) / "alpha"]
    assert not (plugins_folder(data_dir) / "alpha").exists()
    assert (data / "state.txt").read_text(encoding="utf-8") == "kept"
    assert not preferences.is_enabled("alpha")


@pytest.mark.parametrize("plugin_id", ["missing", "../alpha", "Bad-Name"])
def test_uninstall_refuses_an_id_that_is_not_installed(
    data_dir: Path, trash: FakeTrash, preferences: PluginPreferences, plugin_id: str
) -> None:
    with pytest.raises(InstallRefusedError, match="is not installed"):
        uninstall(plugin_id, data_dir=data_dir, trash=trash, preferences=preferences)
    assert trash.sent == []


def test_a_folder_unpacked_by_hand_is_listed_as_installed(tmp_path: Path, data_dir: Path) -> None:
    package = _package(tmp_path, "handmade")
    target = plugins_folder(data_dir) / "handmade"
    target.mkdir(parents=True)
    with zipfile.ZipFile(package) as archive:
        archive.extractall(target)

    plugins = installed(data_dir)

    assert [plugin.plugin_id for plugin in plugins] == ["handmade"]
    assert plugins[0].description.title == "Sample handmade"


def test_a_folder_without_a_readable_plugin_json_is_not_listed(data_dir: Path) -> None:
    broken = plugins_folder(data_dir) / "broken"
    broken.mkdir(parents=True)
    (broken / "plugin.json").write_text("{", encoding="utf-8")
    (plugins_folder(data_dir) / "empty").mkdir()

    assert installed(data_dir) == []


def test_a_leftover_staging_folder_is_sent_to_the_bin_at_start(
    data_dir: Path, trash: FakeTrash
) -> None:
    staging = plugins_folder(data_dir) / ".staging"
    (staging / "alpha").mkdir(parents=True)
    (staging / "alpha" / "partial.txt").write_text("half", encoding="utf-8")

    cleaned = clean_staging(data_dir, trash)

    assert cleaned is True
    assert trash.sent == [staging]
    assert not staging.exists()


def test_clean_staging_does_nothing_without_a_leftover(data_dir: Path, trash: FakeTrash) -> None:
    assert clean_staging(data_dir, trash) is False
    assert trash.sent == []

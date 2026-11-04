"""The Plugins view model: installed plugins, statuses, installs, the Marketplace (plan 123.6).

No test reaches the internet or the real Recycle Bin, and the data folder is temporary. Jobs run
at once in a fake job service, except one test that uses the real job service. The plugin list
of each start is read by the real loader from the temporary plugins folder; only the running
state is set by hand, since no plugin code is needed to show it.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import urllib.error
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QUrl

from mtee.models.plugins_view_model import PluginsViewModel
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import API_VERSION
from mtee.plugins.installer import plugin_folders, plugins_folder
from mtee.plugins.loader import (
    DiscoveredPlugin,
    LoadedPlugin,
    PluginPreferences,
    PluginStatus,
    discover,
)
from mtee.plugins.package import PluginDescription
from mtee.services.jobs import JobService

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
MTEE_VERSION = "0.1.0"


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


class FakeContext:
    """What a job task receives: a flag that is never set, and a record of the progress."""

    def __init__(self) -> None:
        self.progress: list[float] = []

    @property
    def is_cancelled(self) -> bool:
        return False

    def report_progress(self, value: float) -> None:
        self.progress.append(value)

    def raise_if_cancelled(self) -> None:
        """Nothing is cancelled in these tests."""


class FakeJobs:
    """Runs each job at once and keeps its label; a failed job keeps its error."""

    def __init__(self) -> None:
        self.labels: list[str] = []
        self.failures: list[tuple[str, BaseException]] = []

    def submit(self, task: Any, *, label: str = "", visible: bool = True) -> None:
        del visible
        self.labels.append(label)
        try:
            task(FakeContext())
        except Exception as error:
            self.failures.append((label, error))


class FakeManager:
    """Stands in for the plugin manager: only its list of loaded plugins is read."""

    def __init__(self, plugins: list[LoadedPlugin]) -> None:
        self.plugins = plugins


class FakeOpener:
    """Stands in for urlopen: the plugin list and the package files, by address."""

    def __init__(self, answers: dict[str, bytes], *, error: BaseException | None = None) -> None:
        self.answers = answers
        self.error = error
        self.urls: list[str] = []

    def __call__(self, request: Any, timeout: float = 0) -> Any:
        del timeout
        self.urls.append(request.full_url)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.answers[request.full_url])


class Harness:
    """The data folder, the settings and the fakes of one test; ``start`` builds the view."""

    def __init__(self, tmp_path: Path, *, opener: FakeOpener | None = None) -> None:
        self.tmp = tmp_path
        self.data_dir = tmp_path / "data"
        self.data_dir.mkdir()
        self.database = Database(tmp_path / "mtee.sqlite3")
        self.database.migrate()
        self.settings = SettingsRepository(self.database)
        self.preferences = PluginPreferences(self.settings)
        self.trash = FakeTrash(tmp_path / "bin")
        (tmp_path / "bin").mkdir()
        self.jobs = FakeJobs()
        self.opener = opener
        self.restarts: list[str] = []
        self.quits: list[str] = []
        self.revealed: list[Path] = []

    def start(self) -> PluginsViewModel:
        """Build the view as the application does at start: the plugins folder is read."""
        enabled = set(self.preferences.enabled())
        records: list[LoadedPlugin] = []
        for found in discover(plugin_folders(self.data_dir)):
            status = PluginStatus.DISABLED
            if found.is_valid and found.plugin_id in enabled:
                status = PluginStatus.RUNNING
            records.append(LoadedPlugin(found, status, found.error))
        return self.view(FakeManager(records))

    def view(self, manager: FakeManager) -> PluginsViewModel:
        def restart() -> None:
            self.restarts.append("restart")

        return PluginsViewModel(
            manager=cast(Any, manager),
            preferences=self.preferences,
            settings=self.settings,
            data_dir=self.data_dir,
            jobs=cast(JobService, self.jobs),
            trash=self.trash,
            reveal=self.revealed.append,
            restart=restart,
            quit_app=lambda: self.quits.append("quit"),
            opener=cast(Any, self.opener),
            mtee_libraries={},
            mtee_version=MTEE_VERSION,
            clock=lambda: NOW,
        )

    def close(self) -> None:
        self.database.close()


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    harness = Harness(tmp_path)
    yield harness
    harness.close()


def _package(
    folder: Path, plugin_id: str = "alpha", version: str = "1.0.0", *, readme: str = ""
) -> Path:
    """Write a package file of ``plugin_id`` into ``folder`` and return its path."""
    folder.mkdir(parents=True, exist_ok=True)
    description = PluginDescription(
        id=plugin_id,
        title=f"Sample {plugin_id}",
        description="A sample plugin.",
        version=version,
        api_version=API_VERSION,
        author="Tester",
        homepage="",
        licence="GPL-3.0-or-later",
        uses_network=False,
        python="3.12",
        platform="any",
        mtee=">=0.1,<0.2",
        libraries=(),
        top_level_modules={},
    )
    manifest = (
        "from mtee.plugins.api import PluginManifest\n\n"
        "MANIFEST = PluginManifest(\n"
        f"    plugin_id={plugin_id!r},\n"
        f"    title={description.title!r},\n"
        '    description="A sample plugin.",\n'
        f"    version={version!r},\n"
        f"    api_version={API_VERSION},\n"
        f"    factory='mtee.plugins.{plugin_id}:create',\n"
        ")\n"
    )
    path = folder / f"{plugin_id}-{version}.mteeplugin"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("plugin.json", description.to_json())
        archive.writestr(f"{plugin_id}/__init__.py", "VALUE = 1\n")
        archive.writestr(f"{plugin_id}/manifest.py", manifest)
        if readme:
            archive.writestr("README.md", readme)
    return path


def _url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def _index(entries: list[dict[str, Any]]) -> bytes:
    return json.dumps({"schema": 1, "plugins": entries}).encode("utf-8")


def _entry(package: Path, plugin_id: str = "alpha", version: str = "1.0.0") -> dict[str, Any]:
    data = package.read_bytes()
    return {
        "id": plugin_id,
        "title": f"Sample {plugin_id}",
        "description": "A sample plugin.",
        "author": "Tester",
        "homepage": "",
        "licence": "GPL-3.0-or-later",
        "uses_network": False,
        "versions": [
            {
                "version": version,
                "api_version": API_VERSION,
                "python": "3.12",
                "platform": "any",
                "url": (
                    "https://github.com/foliarn/mtee-plugins/releases/download/"
                    f"{plugin_id}-{version}/{plugin_id}-{version}.mteeplugin"
                ),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "released": "2026-10-30",
            }
        ],
    }


def _install_on_disk(harness: Harness, package: Path, *, enabled: bool = True) -> None:
    """Install a package before the start, as an earlier session would have."""
    from mtee.plugins.installer import install

    plugin_id = package.name.split("-")[0]
    install(
        package,
        data_dir=harness.data_dir,
        trash=harness.trash,
        preferences=harness.preferences,
        mtee_version=MTEE_VERSION,
        mtee_libraries={},
    )
    harness.settings.set(f"plugin-source.{plugin_id}", "file")
    if not enabled:
        harness.preferences.set_enabled(plugin_id, False)


def _row(rows: list[dict[str, Any]], plugin_id: str) -> dict[str, Any]:
    return next(row for row in rows if row["id"] == plugin_id)


def test_the_installed_list_shows_the_state_of_each_plugin(harness: Harness) -> None:
    _install_on_disk(harness, _package(harness.tmp / "p1", "alpha", readme="# Alpha"))
    _install_on_disk(harness, _package(harness.tmp / "p2", "beta"), enabled=False)
    broken = harness.data_dir / "plugins" / "gamma"
    broken.mkdir(parents=True)
    (broken / "gamma").mkdir()
    (broken / "gamma" / "__init__.py").write_text("", encoding="utf-8")
    (broken / "gamma" / "manifest.py").write_text("raise RuntimeError('x')\n", encoding="utf-8")

    view = harness.start()

    rows = view.property("installed")
    alpha = _row(rows, "alpha")
    assert alpha["status"] == "running" and alpha["statusText"] == "Running"
    assert alpha["enabled"] is True and alpha["letter"] == "S"
    assert alpha["author"] == "Tester" and alpha["readme"] == "# Alpha"
    assert alpha["installedFrom"] == "file" and alpha["librariesCount"] == 0
    beta = _row(rows, "beta")
    assert beta["status"] == "disabled" and beta["statusText"] == "Disabled"
    assert beta["enabled"] is False
    gamma = _row(rows, "gamma")
    assert gamma["status"] == "failed" and gamma["statusText"] == "Failed"
    assert gamma["error"]
    assert view.property("restartNeeded") is False
    assert view.property("restartText") == ""


def test_a_new_install_waits_for_a_restart_and_is_counted(harness: Harness) -> None:
    view = harness.start()
    view.chooseFile(_url(_package(harness.tmp / "pkg")))
    view.confirmInstall()

    alpha = _row(view.property("installed"), "alpha")
    assert alpha["status"] == "restart" and alpha["statusText"] == "Restart needed"
    assert view.property("restartNeeded") is True
    assert view.property("restartText") == "1 plugin needs a restart"
    assert "Installing Sample alpha 1.0.0" in harness.jobs.labels


def test_search_filters_both_lists_by_title_description_and_author(harness: Harness) -> None:
    _install_on_disk(harness, _package(harness.tmp / "p1", "alpha"))
    _install_on_disk(harness, _package(harness.tmp / "p2", "beta"))
    view = harness.start()
    view.setProperty("search", "SAMPLE")
    assert [row["id"] for row in view.property("installed")] == ["alpha", "beta"]
    view.setProperty("search", "tester")  # the author is searched too
    assert len(view.property("installed")) == 2
    view.setProperty("search", "nothing like this")
    assert view.property("installed") == []
    view.setProperty("search", "")
    assert len(view.property("installed")) == 2


def test_a_package_file_is_checked_and_waits_for_the_warning(harness: Harness) -> None:
    package = _package(harness.tmp / "pkg")
    view = harness.start()

    view.chooseFile(_url(package))

    pending = view.property("pendingInstall")
    assert pending["title"] == "Sample alpha" and pending["version"] == "1.0.0"
    assert pending["author"] == "Tester" and pending["source"] == "file"
    assert pending["sourceText"] == "Local file: alpha-1.0.0.mteeplugin"
    assert pending["usesNetwork"] is False and pending["librariesCount"] == 0
    assert pending["sizeText"].endswith("KB")
    assert view.property("installed") == []  # nothing is installed before the confirmation
    view.confirmInstall()
    assert view.property("pendingInstall") == {}
    assert _row(view.property("installed"), "alpha")["installedFrom"] == "file"
    assert (harness.data_dir / "plugins" / "alpha" / "plugin.json").is_file()


def test_a_bad_package_is_refused_with_one_sentence(harness: Harness) -> None:
    bad = harness.tmp / "bad-1.0.0.mteeplugin"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("alpha/__init__.py", "")
    view = harness.start()

    view.chooseFile(_url(bad))

    refusal = view.property("refusal")
    assert refusal == {
        "title": "bad-1.0.0 was not installed",
        "text": "The package has no plugin.json.",
    }
    assert view.property("pendingInstall") == {}
    view.dismissRefusal()
    assert view.property("refusal") == {}


def test_uninstall_sends_the_folder_to_the_bin_and_keeps_the_data(harness: Harness) -> None:
    _install_on_disk(harness, _package(harness.tmp / "pkg"))
    view = harness.start()
    data = harness.data_dir / "plugin-data" / "alpha"
    data.mkdir(parents=True)

    view.uninstall("alpha")

    assert [path.name for path in harness.trash.sent] == ["alpha"]
    assert view.property("installed") == []
    assert view.property("restartNeeded") is True
    assert view.property("restartText") == "1 plugin needs a restart"
    assert data.is_dir()


def test_switching_a_plugin_saves_the_choice_and_asks_for_a_restart(harness: Harness) -> None:
    _install_on_disk(harness, _package(harness.tmp / "pkg"), enabled=False)
    view = harness.start()
    assert view.property("restartNeeded") is False

    view.setEnabled("alpha", True)

    assert harness.preferences.is_enabled("alpha") is True
    assert _row(view.property("installed"), "alpha")["status"] == "restart"
    assert view.property("restartNeeded") is True


def test_the_marketplace_is_read_once_and_lists_the_compatible_plugins(harness: Harness) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    harness.opener = FakeOpener({_index_url(): _index([_entry(package)])})
    view = harness.start()
    assert view.property("marketplaceState") == "idle"

    view.marketplaceRequested()
    view.marketplaceRequested()

    assert view.property("marketplaceState") == "ready"
    assert len(harness.opener.urls) == 1
    listed = view.property("marketplace")
    assert listed[0]["id"] == "alpha" and listed[0]["state"] == "install"
    assert listed[0]["version"] == "1.0.0" and listed[0]["installedVersion"] == ""
    assert view.property("lastCheckedText") == "Last checked just now"


def test_an_empty_plugin_list_is_ready_with_no_plugin(harness: Harness) -> None:
    harness.opener = FakeOpener({_index_url(): _index([])})
    view = harness.start()

    view.checkMarketplace()

    assert view.property("marketplaceState") == "ready"
    assert view.property("marketplace") == []


def test_a_failed_read_of_the_list_is_one_sentence_and_keeps_the_installed(
    harness: Harness,
) -> None:
    _install_on_disk(harness, _package(harness.tmp / "pkg"))
    harness.opener = FakeOpener({}, error=urllib.error.URLError("offline"))
    view = harness.start()

    view.checkMarketplace()

    assert view.property("marketplaceState") == "failed"
    assert view.property("marketplaceError").startswith("The plugin list could not be read")
    assert len(view.property("installed")) == 1
    assert len(harness.jobs.failures) == 1


def test_install_from_the_marketplace_downloads_then_asks_for_the_warning(
    harness: Harness,
) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    url = (
        "https://github.com/foliarn/mtee-plugins/releases/download/alpha-1.0.0/"
        "alpha-1.0.0.mteeplugin"
    )
    harness.opener = FakeOpener(
        {_index_url(): _index([_entry(package)]), url: package.read_bytes()}
    )
    view = harness.start()
    view.checkMarketplace()

    view.install("alpha")

    assert "Downloading Sample alpha 1.0.0" in harness.jobs.labels
    pending = view.property("pendingInstall")
    assert pending["source"] == "marketplace"
    assert pending["sourceText"].startswith("Downloaded from the official MTEE plugin list")
    downloads = plugins_folder(harness.data_dir) / ".downloads"
    assert len(list(downloads.iterdir())) == 1

    view.confirmInstall()

    assert _row(view.property("installed"), "alpha")["installedFrom"] == "marketplace"
    assert list(downloads.iterdir()) == []
    assert _row(view.property("marketplace"), "alpha")["state"] == "installed"


def test_a_download_that_does_not_match_the_list_is_refused(harness: Harness) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    entry = _entry(package)
    entry["versions"][0]["sha256"] = "0" * 64
    url = entry["versions"][0]["url"]
    harness.opener = FakeOpener({_index_url(): _index([entry]), url: package.read_bytes()})
    view = harness.start()
    view.checkMarketplace()

    view.install("alpha")

    refusal = view.property("refusal")
    assert refusal["title"] == "Sample alpha 1.0.0 was not installed"
    assert "checksum" in refusal["text"]
    assert view.property("pendingInstall") == {}
    assert list((plugins_folder(harness.data_dir) / ".downloads").glob("*.mteeplugin")) == []


def test_an_update_is_offered_for_a_newer_compatible_version(harness: Harness) -> None:
    _install_on_disk(harness, _package(harness.tmp / "old", "alpha", "1.0.0"))
    newer = _package(harness.tmp / "new", "alpha", "1.1.0")
    url = _entry(newer, "alpha", "1.1.0")["versions"][0]["url"]
    harness.opener = FakeOpener(
        {_index_url(): _index([_entry(newer, "alpha", "1.1.0")]), url: newer.read_bytes()}
    )
    view = harness.start()
    view.checkMarketplace()

    assert _row(view.property("installed"), "alpha")["updateVersion"] == "1.1.0"
    listed = _row(view.property("marketplace"), "alpha")
    assert listed["state"] == "update" and listed["version"] == "1.1.0"
    assert listed["installedVersion"] == "1.0.0"

    view.update("alpha")
    view.confirmInstall()

    assert _row(view.property("installed"), "alpha")["version"] == "1.1.0"
    assert _row(view.property("installed"), "alpha")["status"] == "restart"
    assert view.property("restartNeeded") is True


def test_open_detail_opens_a_plugin_tab_and_detail_returns_the_row(
    qapp: Any, tmp_path: Path
) -> None:
    from mtee.models.workspace_model import WorkspaceModel
    from mtee.persistence.library_repository import LibraryRepository
    from mtee.persistence.workspace_repository import WorkspaceRepository

    harness = Harness(tmp_path)
    try:
        _install_on_disk(harness, _package(tmp_path / "pkg", "alpha", readme="# Hi"))
        jobs = JobService(qapp, max_thread_count=1)
        workspace = WorkspaceModel(
            library=LibraryRepository(harness.database),
            session=WorkspaceRepository(harness.database),
            jobs=jobs,
        )
        view = harness.start()
        workspace.attach_plugins_view(view)
        assert workspace.pluginsView is not None

        view.openDetail("alpha")

        assert cast(Any, workspace).activeTabId == "plugin:alpha"
        assert cast(Any, view.detail("alpha"))["readme"] == "# Hi"
        assert view.detail("missing") == {}
        jobs.shutdown(1_000)
    finally:
        harness.close()


def test_a_real_job_updates_the_model_on_the_gui_thread(qapp: Any, tmp_path: Path) -> None:
    harness = Harness(tmp_path, opener=FakeOpener({_index_url(): _index([])}))
    try:
        jobs = JobService(qapp, max_thread_count=1)
        view = harness.view(FakeManager([]))
        view._jobs = jobs  # the real job service runs the index read in a worker thread
        view.checkMarketplace()
        for _ in range(200):
            jobs.wait_for_done(50)
            qapp.processEvents()
            if view.property("marketplaceState") == "ready":
                break
        assert view.property("marketplaceState") == "ready"
        jobs.shutdown(1_000)
    finally:
        harness.close()


def test_restart_starts_the_new_process_and_quits_through_the_normal_path(
    harness: Harness,
) -> None:
    view = harness.start()

    view.restartNow()

    assert harness.restarts == ["restart"]
    assert harness.quits == ["quit"]


def test_a_restart_that_cannot_start_keeps_the_application_open(harness: Harness) -> None:
    view = harness.start()

    def fail() -> None:
        raise OSError("no such file")

    view._restart = fail  # the process cannot start: the application keeps running
    notices: list[str] = []
    view.noticeRaised.connect(notices.append)
    view.restartNow()

    assert harness.quits == []
    assert notices == ["MTEE could not restart: no such file"]


def test_the_plugins_folder_is_created_and_opened(harness: Harness) -> None:
    view = harness.start()

    view.openPluginsFolder()

    folder = plugins_folder(harness.data_dir)
    assert folder.is_dir()
    assert harness.revealed == [folder]


def test_a_plugin_that_was_loaded_unchanged_is_not_asked_to_restart(harness: Harness) -> None:
    _install_on_disk(harness, _package(harness.tmp / "pkg"))
    view = harness.start()
    assert view.property("restartNeeded") is False
    assert _row(view.property("installed"), "alpha")["status"] == "running"


def test_a_plugin_loaded_from_the_folder_list_starts_in_its_recorded_state(
    harness: Harness,
) -> None:
    _install_on_disk(harness, _package(harness.tmp / "pkg"))
    folder = plugins_folder(harness.data_dir) / "alpha"
    found = discover([folder])[0]
    assert isinstance(found, DiscoveredPlugin) and found.is_valid
    manager = FakeManager([LoadedPlugin(found, PluginStatus.FAILED, "Could not start.")])
    view = harness.view(manager)
    row = _row(view.property("installed"), "alpha")
    assert row["status"] == "failed" and row["error"] == "Could not start."


def _index_url() -> str:
    return "https://raw.githubusercontent.com/foliarn/mtee-plugins/main/index.json"


def test_the_last_check_reads_in_minutes_then_hours(harness: Harness) -> None:
    harness.opener = FakeOpener({_index_url(): _index([])})
    view = harness.start()
    view.checkMarketplace()  # checked at NOW
    assert view.property("lastCheckedText") == "Last checked just now"
    view._clock = lambda: NOW + timedelta(minutes=2)
    assert view.property("lastCheckedText") == "Last checked 2 min ago"
    view._clock = lambda: NOW + timedelta(hours=3)
    assert view.property("lastCheckedText") == "Last checked 3 h ago"


def test_cancelling_a_chosen_file_leaves_the_file_alone(harness: Harness) -> None:
    package = _package(harness.tmp / "pkg")
    view = harness.start()
    view.chooseFile(_url(package))
    view.cancelInstall()
    assert package.is_file()
    assert view.property("pendingInstall") == {}

"""Track availability (plan 125.3): the contribution, the one provider, the call back.

The providers here are small packages written into a temporary plugin folder and loaded by the
real ``PluginManager``; the sample plugin is loaded the same way. Only temporary data is used.
"""

from __future__ import annotations

import shutil
import textwrap
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.api import Availability, PluginContext, PluginManifest, TrackAvailability
from mtee.plugins.availability_registry import TrackAvailabilityRegistry
from mtee.plugins.context import PluginHost
from mtee.plugins.contributions import check_contributions
from mtee.plugins.loader import PluginManager, PluginPreferences, PluginStatus

_HERE = Path(__file__).parent
_MANIFEST = PluginManifest("probe", "Probe", "", "1.0.0", 1, "mtee.plugins.probe:create")


def _status(track_ids: Sequence[str]) -> Mapping[str, Availability]:
    return {}


# --- the contribution ---------------------------------------------------------------------


def test_the_contribution_is_checked() -> None:
    check_contributions("p", [TrackAvailability(_status)])
    with pytest.raises(ValueError, match="needs a function that is not callable"):
        check_contributions("p", [TrackAvailability("nope")])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at most once"):
        check_contributions("p", [TrackAvailability(_status), TrackAvailability(_status)])


# --- one provider in total ----------------------------------------------------------------


def _write_provider(folder: Path, plugin_id: str, title: str) -> None:
    """Write a plugin package whose only contribution is a TrackAvailability."""
    package = folder / plugin_id
    package.mkdir(parents=True)
    (package / "manifest.py").write_text(
        textwrap.dedent(
            f"""
            from mtee.plugins.api import PluginManifest

            MANIFEST = PluginManifest(
                {plugin_id!r}, {title!r}, "", "1.0.0", 1, "mtee.plugins.{plugin_id}:create"
            )
            """
        ),
        encoding="utf-8",
    )
    (package / "__init__.py").write_text(
        textwrap.dedent(
            """
            from mtee.plugins.api import TrackAvailability


            def _status(track_ids):
                return {track_id: "remote" for track_id in track_ids}


            class Service:
                def contributions(self):
                    return [TrackAvailability(_status)]

                def unload(self):
                    pass


            def create(context):
                return Service()
            """
        ),
        encoding="utf-8",
    )


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    created = Database(tmp_path / "data" / "mtee.sqlite3")
    created.migrate()
    yield created
    created.close()


def _no_context(manifest: PluginManifest) -> PluginContext:
    """The providers above need no context: their factory ignores it."""
    return cast(PluginContext, None)


def test_a_second_plugin_with_availability_is_refused_with_a_reason(
    database: Database, tmp_path: Path
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    _write_provider(folder, "alpha_avail", "Alpha availability")
    _write_provider(folder, "beta_avail", "Beta availability")
    preferences = PluginPreferences(SettingsRepository(database))
    preferences.set_enabled("alpha_avail", True)
    preferences.set_enabled("beta_avail", True)
    notices: list[str] = []
    manager = PluginManager(preferences, notify=notices.append)
    try:
        records = {
            record.plugin_id: record for record in manager.load_enabled(_no_context, [folder])
        }
        alpha, beta = records["alpha_avail"], records["beta_avail"]
        assert alpha.status is PluginStatus.RUNNING
        assert any(isinstance(item, TrackAvailability) for item in alpha.contributions)
        assert beta.status is PluginStatus.FAILED
        assert beta.contributions == ()
        assert "already provided by Alpha availability" in beta.error
        # The one notice names the refused plugin and the one that keeps the contribution.
        assert any("Beta availability" in n and "Alpha availability" in n for n in notices)

        registry = TrackAvailabilityRegistry()
        registry.register(manager.plugins)
        assert registry.provided is True
        # The first plugin keeps answering; the refused one is never asked.
        assert registry.remote_ids(["t1"]) == frozenset({"t1"})
    finally:
        manager.unload_all()


# --- the call back from a plugin ----------------------------------------------------------


def _host(database: Database, base: Path) -> PluginHost:
    settings = SettingsRepository(database)
    return PluginHost(
        data_dir=base / "data",
        database=database,
        settings=settings,
        library=cast(Any, MagicMock()),
        playlists=cast(Any, MagicMock()),
        jobs=cast(Any, MagicMock()),
        file_moves=cast(Any, MagicMock()),
        recycle=cast(Any, MagicMock()),
        roots=cast(Any, MagicMock()),
        refresh_playlists=lambda: None,
        source_tracks=SourceTrackRepository(database),
    )


def test_availability_changed_from_a_worker_thread_reaches_the_gui_thread(
    qapp, database: Database, tmp_path: Path
) -> None:
    host = _host(database, tmp_path)
    context = host.context_for(_MANIFEST)
    gui_thread = threading.get_ident()
    seen: list[tuple[object, int]] = []
    host.availabilityChanged.connect(lambda ids: seen.append((ids, threading.get_ident())))

    worker = threading.Thread(target=lambda: context.availability_changed(["a", "b"]))
    worker.start()
    worker.join(10)
    context.availability_changed()  # every track, from the graphical thread

    deadline = time.monotonic() + 5
    while len(seen) < 2 and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert seen == [(["a", "b"], gui_thread), (None, gui_thread)]


def test_a_context_built_without_the_hook_ignores_the_call() -> None:
    context = PluginContext(
        plugin_id="x",
        database=None,  # type: ignore[arg-type]
        library=None,  # type: ignore[arg-type]
        playlists=None,  # type: ignore[arg-type]
        jobs=None,  # type: ignore[arg-type]
        files=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        base_dir=Path("."),
        notify=lambda text: None,
        log=None,  # type: ignore[arg-type]
    )
    context.availability_changed(["a"])
    context.availability_changed()


# --- the registry, with the sample plugin loaded for real ---------------------------------


def test_the_sample_plugin_marks_its_served_track_as_remote(
    qapp, database: Database, tmp_path: Path
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    shutil.copytree(
        _HERE / "sample", folder / "sample", ignore=shutil.ignore_patterns("__pycache__")
    )
    preferences = PluginPreferences(SettingsRepository(database))
    preferences.set_enabled("sample", True)
    host = _host(database, tmp_path)
    manager = PluginManager(preferences, notify=lambda text: None)
    host.attach_plugin_manager(manager)
    try:
        record = manager.load_enabled(host.context_for, [folder])[0]
        assert record.error == "", record.error
        service = record.service
        assert service is not None
        identities = service.provide_tracks(b"not really audio", 3_000_000)  # type: ignore[attr-defined]
        served = identities["sample-url-track"]
        broken = identities["sample-broken-track"]

        registry = TrackAvailabilityRegistry()
        registry.register(manager.plugins)
        assert registry.provided is True
        assert registry.remote_ids([served, broken, "not-a-track"]) == frozenset({served})
        assert registry.remote_ids([]) == frozenset()
    finally:
        manager.unload_all()


# --- the registry on its own --------------------------------------------------------------


class _Record:
    """Stands for a LoadedPlugin: the registry reads three attributes."""

    def __init__(self, plugin_id: str, status: PluginStatus, contributions: Sequence[Any]) -> None:
        self.plugin_id = plugin_id
        self.title = plugin_id.title()
        self.status = status
        self.contributions = tuple(contributions)


def _registry_with(
    status_fn: Any, status: PluginStatus = PluginStatus.RUNNING
) -> TrackAvailabilityRegistry:
    registry = TrackAvailabilityRegistry()
    registry.register(cast(Any, [_Record("probe", status, [TrackAvailability(status_fn)])]))
    return registry


def test_the_registry_reports_remote_tracks_and_counts_the_rest_as_local() -> None:
    def status(track_ids: Sequence[str]) -> Any:
        return {"a": "remote", "b": "synced", "c": "local", "d": "unknown-value", "z": "remote"}

    registry = _registry_with(status)
    assert registry.remote_ids(["a", "b", "c", "d", "e", ""]) == frozenset({"a"})


def test_the_registry_asks_nothing_without_a_running_provider() -> None:
    asked: list[Sequence[str]] = []

    def status(track_ids: Sequence[str]) -> Mapping[str, Availability]:
        asked.append(track_ids)
        return {}

    stopped = _registry_with(status, PluginStatus.DISABLED)
    assert stopped.provided is False
    assert stopped.remote_ids(["a"]) == frozenset()
    assert asked == []


def test_a_provider_that_fails_or_answers_oddly_leaves_every_track_local() -> None:
    def raises(track_ids: Sequence[str]) -> Mapping[str, Availability]:
        raise RuntimeError("no connection")

    def odd(track_ids: Sequence[str]) -> Any:
        return ["a"]

    assert _registry_with(raises).remote_ids(["a"]) == frozenset()
    assert _registry_with(odd).remote_ids(["a"]) == frozenset()

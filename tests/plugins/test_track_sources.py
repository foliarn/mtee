"""Track sources (plan 125.2): what a plugin gets on its context and how the core calls it back.

The sample plugin is loaded for real through ``PluginManager`` over a temporary library, and its
audio server answers on 127.0.0.1. Only temporary data is used.
"""

from __future__ import annotations

import shutil
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from mtee.domain.source_tracks import PlayableSource, SourceTrack
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.api import (
    CapabilityUnavailableError,
    PluginContext,
    PluginManifest,
    TrackSource,
)
from mtee.plugins.context import PluginHost
from mtee.plugins.contributions import check_contributions
from mtee.plugins.loader import PluginManager, PluginPreferences
from mtee.plugins.source_registry import TrackSourceRegistry
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.playlist_service import PlaylistService
from mtee.services.track_sources import SourceOpenError

_HERE = Path(__file__).parent
_MANIFEST = PluginManifest("sample", "Sample plugin", "", "1.0.0", 1, "mtee.plugins.sample:create")
_OTHER = PluginManifest("other", "Other", "", "1.0.0", 1, "mtee.plugins.other:create")


class _Roots:
    def addRoot(self, selected: str) -> str:  # noqa: N802
        return "root-new"

    def rescanRoot(self, root_id: str) -> str:  # noqa: N802
        return root_id


class _Trash:
    def request_recycle(self, raw_track_ids: list) -> None:
        del raw_track_ids


class _Setup:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.settings = SettingsRepository(self.database)
        self.library = LibraryRepository(self.database)
        self.jobs = JobService(max_thread_count=2)
        self.changed: list[tuple[str, ...]] = []
        self.host = PluginHost(
            data_dir=base / "data",
            database=self.database,
            settings=self.settings,
            library=self.library,
            playlists=PlaylistService(PlaylistsRepository(self.database), self.library),
            jobs=self.jobs,
            file_moves=FileMoveService(self.database, self.library, FileAccessCoordinator()),
            recycle=_Trash(),
            roots=_Roots(),
            refresh_playlists=lambda: None,
            source_tracks=SourceTrackRepository(self.database),
            source_tracks_changed=lambda ids: self.changed.append(tuple(ids)),
        )

    def context(self, manifest: PluginManifest = _MANIFEST) -> PluginContext:
        return self.host.context_for(manifest)

    def close(self) -> None:
        self.jobs.shutdown(2_000)
        self.database.close()


@pytest.fixture
def setup(qapp, tmp_path: Path) -> Iterator[_Setup]:
    created = _Setup(tmp_path)
    yield created
    created.close()


def _in_worker[T](call: Callable[[], T]) -> T:
    outcome: list[Any] = []

    def work() -> None:
        try:
            outcome.append((True, call()))
        except BaseException as error:  # handed back to the test thread
            outcome.append((False, error))

    thread = threading.Thread(target=work)
    thread.start()
    thread.join(20)
    ok, value = outcome[0]
    if not ok:
        raise value
    return value


def _track(key: str, title: str = "Song") -> SourceTrack:
    return SourceTrack(key, title, artists=("Ann",), album="Album", duration_us=2_000_000)


# --- the capability -----------------------------------------------------------------------


def test_upsert_remove_and_list_are_idempotent_from_a_job_thread(setup: _Setup, qapp) -> None:
    sources = setup.context().track_sources

    first = _in_worker(lambda: sources.upsert([_track("a"), _track("b")]))
    again = _in_worker(lambda: sources.upsert([_track("b"), _track("a")]))
    assert first == again and sorted(first) == ["a", "b"]
    qapp.processEvents()
    assert len(setup.changed) == 1  # the second call changed nothing, so it announced nothing
    assert sorted(setup.changed[0]) == sorted(first.values())

    assert _in_worker(lambda: sources.remove(["a", "unknown"])) == 1
    assert _in_worker(lambda: sources.remove(["a"])) == 0
    listed = {entry.source_key: entry for entry in _in_worker(sources.list)}
    assert listed["a"].available is False and listed["b"].available is True
    assert [e.source_key for e in sources.list(available_only=True)] == ["b"]
    qapp.processEvents()
    assert setup.changed[-1] == (first["a"],)


def test_a_plugin_reaches_only_its_own_keys(setup: _Setup) -> None:
    mine = setup.context().track_sources
    theirs = setup.context(_OTHER).track_sources
    one = mine.upsert([_track("same")])
    two = theirs.upsert([_track("same", "Other song")])
    assert one["same"] != two["same"]
    assert mine.remove(["same"]) == 1
    assert [e.available for e in theirs.list()] == [True]  # untouched
    assert [e.track.title for e in mine.list()] == ["Song"]


def test_wrong_arguments_are_refused_with_a_clear_error(setup: _Setup) -> None:
    sources = setup.context().track_sources
    with pytest.raises(TypeError):
        sources.upsert(["not a SourceTrack"])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        sources.remove("a")  # type: ignore[arg-type]


def test_a_context_built_without_the_capability_raises_a_readable_error() -> None:
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
    with pytest.raises(CapabilityUnavailableError):
        context.track_sources.upsert([_track("a")])
    with pytest.raises(CapabilityUnavailableError):
        context.track_sources.list()


# --- the contribution and the registry ----------------------------------------------------


def _open_ok(key: str) -> PlayableSource:
    return PlayableSource(url="http://127.0.0.1:1/" + key)


def test_the_contribution_is_checked() -> None:
    check_contributions("p", [TrackSource(_open_ok)])
    check_contributions("p", [TrackSource(_open_ok, lambda key: None)])
    with pytest.raises(ValueError, match="at most one"):
        check_contributions("p", [TrackSource(_open_ok), TrackSource(_open_ok)])
    with pytest.raises(ValueError, match="not callable"):
        check_contributions("p", [TrackSource("nope")])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not callable"):
        check_contributions("p", [TrackSource(_open_ok, "nope")])  # type: ignore[arg-type]


class _Record:
    """Stands for a LoadedPlugin: the registry reads four attributes."""

    def __init__(self, plugin_id: str, status: Any, contributions: Sequence[Any] = ()) -> None:
        self.plugin_id = plugin_id
        self.title = plugin_id.title()
        self.status = status
        self.contributions = tuple(contributions)


def _registry(**sources: TrackSource) -> TrackSourceRegistry:
    from mtee.plugins.loader import PluginStatus

    registry = TrackSourceRegistry()
    records = [
        *(_Record(name, PluginStatus.RUNNING, [source]) for name, source in sources.items()),
        _Record("stopped", PluginStatus.DISABLED),
    ]
    registry.register(cast(Any, records))
    return registry


def test_the_registry_opens_a_track_and_names_the_plugin_when_it_cannot() -> None:
    def broken(key: str) -> PlayableSource:
        raise ConnectionError("no route")

    def wrong(key: str) -> PlayableSource:
        return "http://example.test/a"  # type: ignore[return-value]

    registry = _registry(
        good=TrackSource(_open_ok), bad=TrackSource(broken), odd=TrackSource(wrong)
    )
    assert registry.open("good", "k").url == "http://127.0.0.1:1/k"
    assert registry.running_plugin_ids == {"good", "bad", "odd"}
    with pytest.raises(SourceOpenError, match=r"^Bad could not open this track: no route$"):
        registry.open("bad", "k")
    with pytest.raises(SourceOpenError, match="Odd could not open this track: it did not return"):
        registry.open("odd", "k")
    with pytest.raises(SourceOpenError, match="Stopped is not running"):
        registry.open("stopped", "k")
    assert registry.plugin_title("stopped") == "Stopped"
    assert registry.plugin_title("unknown") == "unknown"


def test_the_registry_gives_a_cover_or_nothing() -> None:
    def cover(key: str) -> bytes | None:
        if key == "boom":
            raise OSError("down")
        return b"png" if key == "yes" else None

    registry = _registry(p=TrackSource(_open_ok, cover), q=TrackSource(_open_ok))
    assert registry.cover("p", "yes") == b"png"
    assert registry.cover("p", "no") is None
    assert registry.cover("p", "boom") is None  # a failing plugin gives no cover, no crash
    assert registry.cover("q", "yes") is None  # no cover function
    assert registry.cover("stopped", "yes") is None


# --- the sample plugin, loaded for real ---------------------------------------------------


def test_the_sample_plugin_provides_a_track_that_only_opens_with_its_token(
    setup: _Setup, qapp, tmp_path: Path
) -> None:
    folder = tmp_path / "plugins"
    folder.mkdir()
    shutil.copytree(
        _HERE / "sample", folder / "sample", ignore=shutil.ignore_patterns("__pycache__")
    )
    preferences = PluginPreferences(setup.settings)
    preferences.set_enabled("sample", True)
    manager = PluginManager(preferences, notify=lambda text: None)
    try:
        record = manager.load_enabled(setup.host.context_for, [folder])[0]
        assert record.error == "", record.error
        service = record.service
        assert service is not None
        identities = _in_worker(lambda: service.provide_tracks(b"not really audio", 3_000_000))  # type: ignore[attr-defined]

        registry = TrackSourceRegistry()
        registry.register(manager.plugins)
        setup.library.set_running_source_plugins(registry.running_plugin_ids, {"sample": "Sample"})
        row = setup.library.track(identities["sample-url-track"])
        assert row["title"] == "Served over HTTP" and row["status"] == "readable"
        assert row["albumArtist"] == "Sample artist"

        source = _in_worker(lambda: registry.open("sample", "sample-url-track"))
        assert source.url and source.headers == {"Authorization": "Bearer sample-token"}
        server = service.audio_server  # type: ignore[attr-defined]
        assert server is not None

        request = urllib.request.Request(source.url, headers=dict(source.headers))
        with urllib.request.urlopen(request, timeout=10) as answer:
            assert answer.status == 200 and answer.read() == b"not really audio"
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(source.url, timeout=10)  # no header
        assert refused.value.code == 401
        assert [seen.authorization for seen in server.requests] == ["Bearer sample-token", None]

        with pytest.raises(SourceOpenError, match="Sample plugin could not open this track"):
            registry.open("sample", "sample-broken-track")
        assert (
            registry.cover(
                "sample",
                "sample-url-track",
            )
            is not None
        )
        assert registry.cover("sample", "sample-broken-track") is None
    finally:
        manager.unload_all()

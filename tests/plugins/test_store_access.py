"""Store access for sync (plan 125.6): the capabilities a plugin gets on its context.

Each call runs through ``PluginHost`` over a temporary library, as a plugin would use it. The
sample plugin exercises all of them once (``sync_probe``). Only temporary data is used.
"""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.data_privacy_model import DataPrivacyModel
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.credit_override_repository import CreditOverrideRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.plugins.api import (
    CapabilityUnavailableError,
    CreditCorrection,
    PlayLogEvent,
    PluginContext,
    PluginManifest,
    SettingNotSyncedError,
    StaleRevisionError,
    TrackAnalysisData,
    TrackLoudnessData,
)
from mtee.plugins.context import PluginHost
from mtee.plugins.loader import PluginManager, PluginPreferences
from mtee.plugins.synced_settings import SYNCED_SETTING_KEYS
from mtee.services.data_privacy import BackupValidationError, RestoreLayout, read_pending_restore
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.playlist_service import PlaylistService

_MANIFEST = PluginManifest("sample", "Sample", "", "1.0.0", 1, "mtee.plugins.sample:create")
_HERE = Path(__file__).parent
DEVICE = str(uuid4())
OTHER = str(uuid4())
START = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


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
        self.music = base / "music"
        self.music.mkdir()
        root = self.library.add_root(self.music)
        generation = self.library.begin_scan(str(root["id"]))
        self.ids: list[str] = []
        for index, (title, artists) in enumerate(
            [("First", ("Ann & Bob", "Cy")), ("Second", ("Ann",)), ("Third", ())]
        ):
            path = self.music / f"track{index}.wav"
            path.write_bytes(b"audio" + bytes([index]))
            self.ids.append(
                self.library.upsert_location(
                    str(root["id"]),
                    path.name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(
                        title=(title,),
                        artist=artists,
                        technical=TechnicalInfo(duration_us=3_000_000),
                    ),
                    generation,
                )
            )
        self.library.finish_scan(str(root["id"]), generation, complete=True)
        self.playlists = PlaylistService(PlaylistsRepository(self.database), self.library)
        self.play_log = PlayLogRepository(self.database)
        self.analysis = AnalysisRepository(self.database)
        self.overrides = CreditOverrideRepository(self.database)
        self.jobs = JobService(max_thread_count=2)
        self.refreshed_plays = 0
        self.applied: list[tuple[str, ...]] = []
        self.proposed: list[Path] = []
        self.host = PluginHost(
            data_dir=base / "data",
            database=self.database,
            settings=self.settings,
            library=self.library,
            playlists=self.playlists,
            jobs=self.jobs,
            file_moves=FileMoveService(self.database, self.library, FileAccessCoordinator()),
            recycle=_Trash(),
            roots=_Roots(),
            refresh_playlists=lambda: None,
            play_log=self.play_log,
            device_id=DEVICE,
            analysis=self.analysis,
            credit_overrides=self.overrides,
            play_log_changed=self._plays_changed,
            settings_applied=lambda keys: self.applied.append(tuple(keys)),
            restore_proposed=self.proposed.append,
        )

    def _plays_changed(self) -> None:
        self.refreshed_plays += 1

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
    """Run ``call`` on another thread, as a plugin job would, and return or raise its result."""
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


def _drain(qapp, condition: Callable[[], bool] = lambda: True, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def _remote(event_id: str, minutes: int, device: str = OTHER) -> PlayLogEvent:
    started = START + timedelta(minutes=minutes)
    return PlayLogEvent(
        event_id=event_id,
        device_id=device,
        track_id="far-track",
        started_at=started,
        ended_at=started + timedelta(seconds=30),
        heard_ms=30_000,
        counted=True,
        title="Far",
    )


# ------------------------------------------------------------------ the defaults


def test_a_context_built_without_the_capabilities_refuses_each_call_readably(
    setup: _Setup,
) -> None:
    bare = PluginContext(
        plugin_id="sample",
        database=setup.database,
        library=None,  # type: ignore[arg-type]
        playlists=None,  # type: ignore[arg-type]
        jobs=None,  # type: ignore[arg-type]
        files=None,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        base_dir=setup.base,
        notify=print,
        log=None,  # type: ignore[arg-type]
    )

    with pytest.raises(CapabilityUnavailableError):
        bare.play_log.events_since(None, 1)
    with pytest.raises(CapabilityUnavailableError):
        bare.track_data.read("x")
    with pytest.raises(CapabilityUnavailableError):
        bare.synced_settings.read()
    with pytest.raises(CapabilityUnavailableError):
        bare.database_snapshot.snapshot(setup.base / "x.db")
    assert bare.synced_settings.keys == frozenset()


def test_a_host_without_the_play_log_or_track_data_gives_unavailable_capabilities(
    qapp, tmp_path: Path
) -> None:
    created = _Setup(tmp_path)
    try:
        host = PluginHost(
            data_dir=tmp_path / "data",
            database=created.database,
            settings=created.settings,
            library=created.library,
            playlists=created.playlists,
            jobs=created.jobs,
            file_moves=FileMoveService(created.database, created.library, FileAccessCoordinator()),
            recycle=_Trash(),
            roots=_Roots(),
            refresh_playlists=lambda: None,
        )
        context = host.context_for(_MANIFEST)

        with pytest.raises(CapabilityUnavailableError):
            context.play_log.append_remote([])
        with pytest.raises(CapabilityUnavailableError):
            context.track_data.read(created.ids[0])
        assert context.synced_settings.keys == SYNCED_SETTING_KEYS  # always provided
    finally:
        created.close()


# ------------------------------------------------------------------ play log


def test_the_play_log_is_read_by_cursor_and_names_this_device(setup: _Setup) -> None:
    log = setup.context().play_log
    setup.play_log.insert_remote_events([_remote("e1", 1), _remote("e2", 2), _remote("e3", 3)])

    page, cursor = _in_worker(lambda: log.events_since(None, 2))
    rest, last = _in_worker(lambda: log.events_since(cursor, 2))

    assert log.device_id == DEVICE
    assert [event.event_id for event in page] == ["e1", "e2"]
    assert [event.event_id for event in rest] == ["e3"]
    assert _in_worker(lambda: log.events_since(last, 2)) == ([], last)


def test_a_batch_from_another_device_is_stored_once_with_its_own_device_id(
    setup: _Setup, qapp
) -> None:
    log = setup.context().play_log
    batch = [_remote("e1", 1), _remote("e2", 2, device="phone-7")]

    first = _in_worker(lambda: log.append_remote(batch))
    again = _in_worker(lambda: log.append_remote(batch))

    assert (first, again) == (2, 0)
    events, _ = log.events_since(None, 10)
    assert [(event.event_id, event.device_id) for event in events] == [
        ("e1", OTHER),
        ("e2", "phone-7"),
    ]
    assert _drain(qapp, lambda: setup.refreshed_plays >= 1)
    qapp.processEvents()
    assert setup.refreshed_plays == 1  # the statistics were told once, not for the repeat
    with pytest.raises(ValueError):
        log.append_remote([_remote("", 3)])
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        setup.database.connection().execute("UPDATE play_events SET heard_ms = 0")


# ------------------------------------------------------------------ playlists


def test_a_playlist_is_read_with_its_revision_and_refuses_a_stale_replace(
    setup: _Setup, qapp
) -> None:
    playlists = setup.context().playlists
    first, second, third = setup.ids
    identity = playlists.create("Synced", [first, second])

    snapshot = playlists.read(identity)
    assert snapshot is not None and snapshot.revision == 1 and snapshot.name == "Synced"
    assert [entry.track_id for entry in snapshot.entries] == [first, second]
    assert playlists.revision(identity) == 1
    assert playlists.read("missing") is None and playlists.revision("missing") is None

    setup.playlists.add(
        identity, [third], confirm_unknown=True
    )  # the interface path changes the playlist
    assert playlists.revision(identity) == 2
    with pytest.raises(StaleRevisionError) as refused:
        playlists.replace_entries(identity, [first], expected_revision=snapshot.revision)
    assert (refused.value.expected, refused.value.actual) == (1, 2)
    assert [entry.track_id for entry in playlists.entries(identity)] == [first, second, third]

    fresh = playlists.read(identity)
    assert fresh is not None
    assert playlists.replace_entries(identity, [third], expected_revision=fresh.revision) == 3
    assert [entry.track_id for entry in playlists.entries(identity)] == [third]
    assert playlists.replace_entries(identity, [first]) == 4  # unconditional, as before


def test_the_revision_rises_for_changes_by_the_plugin_too(setup: _Setup) -> None:
    playlists = setup.context().playlists
    identity = playlists.create("Synced", [setup.ids[0]])
    before = playlists.revision(identity)

    playlists.replace_entries(identity, [setup.ids[1]])

    assert before is not None and playlists.revision(identity) == before + 1


# ------------------------------------------------------------------ track data


def test_track_data_round_trips_and_keeps_the_layers_apart(setup: _Setup) -> None:
    data = setup.context().track_data
    track = setup.ids[0]
    tags_before = setup.library.source_record(track)
    audio_before = (setup.music / "track0.wav").read_bytes()
    assert data.read(track).analysis is None and data.read(track).corrections == ()

    data.write_analysis(
        track,
        TrackAnalysisData(
            bpm=174.0,
            key_tonic=9,
            key_minor=True,
            key_user_edited=True,
            source_duration_us=3_000_000,
            algorithm_version=1,
            analyzed_at_utc="2026-09-01T10:00:00+00:00",
        ),
    )
    only_analysis = data.read(track)
    assert only_analysis.loudness is None  # writing the analysis wrote no loudness
    data.write_loudness(track, TrackLoudnessData(-8.0, -0.5, loudness_version=1))
    data.write_corrections(track, [CreditCorrection("Ann & Bob", "one_artist")])

    read = data.read(track)
    assert read.analysis == TrackAnalysisData(
        bpm=174.0,
        key_tonic=9,
        key_minor=True,
        key_user_edited=True,
        source_duration_us=3_000_000,
        algorithm_version=1,
        analyzed_at_utc="2026-09-01T10:00:00+00:00",
    )
    assert read.loudness is not None
    assert (read.loudness.integrated_lufs, read.loudness.sample_peak_dbfs) == (-8.0, -0.5)
    assert [(c.credit_text, c.mode) for c in read.corrections] == [("Ann & Bob", "one_artist")]
    # Each layer sits in its own store and the audio file and its tags were not touched.
    stored = setup.analysis.get(track)
    assert stored is not None and stored.bpm == 174.0 and stored.integrated_lufs == -8.0
    assert setup.overrides.modes() == {"ann & bob": ("Ann & Bob", "one_artist")}
    assert (setup.music / "track0.wav").read_bytes() == audio_before
    after = setup.library.source_record(track)
    assert after is not None and tags_before is not None
    assert after.snapshot == tags_before.snapshot and after.revision == tags_before.revision
    # A track that does not hold the credit gets no correction for it.
    assert data.read(setup.ids[2]).corrections == ()


def test_a_correction_applies_to_a_credit_segment_of_the_track(setup: _Setup) -> None:
    data = setup.context().track_data

    data.write_corrections(setup.ids[0], [CreditCorrection("cy", "split")])

    assert [c.credit_text for c in data.read(setup.ids[0]).corrections] == ["cy"]


def test_track_data_refuses_what_it_cannot_store(setup: _Setup) -> None:
    data = setup.context().track_data
    track = setup.ids[0]

    with pytest.raises(LookupError):
        data.write_analysis("missing", TrackAnalysisData(bpm=120.0))
    with pytest.raises(LookupError):
        data.write_corrections("missing", [])
    with pytest.raises(ValueError, match="both key_tonic and key_minor"):
        data.write_analysis(track, TrackAnalysisData(key_tonic=3))
    with pytest.raises(ValueError):
        data.write_analysis(track, TrackAnalysisData(key_tonic=12, key_minor=False))
    with pytest.raises(ValueError, match="bpm"):
        data.write_analysis(track, TrackAnalysisData(bpm=float("nan")))
    with pytest.raises(ValueError):
        data.write_analysis(track, TrackAnalysisData(analyzed_at_utc="yesterday"))
    with pytest.raises(ValueError, match="finite"):
        data.write_loudness(track, TrackLoudnessData(float("inf"), 0.0, 1))
    with pytest.raises(ValueError, match="Unknown credit override mode"):
        data.write_corrections(track, [CreditCorrection("Cy", "merge")])
    with pytest.raises(ValueError, match="not an artist credit"):
        data.write_corrections(track, [CreditCorrection("Somebody else", "split")])
    assert setup.overrides.modes() == {}
    assert setup.analysis.get(track) is None


def test_a_local_edit_of_the_tempo_wins_over_a_written_analysis(setup: _Setup) -> None:
    data = setup.context().track_data
    track = setup.ids[1]
    data.write_analysis(track, TrackAnalysisData(bpm=100.0, bpm_user_edited=True))

    data.write_analysis(track, TrackAnalysisData(bpm=140.0, key_tonic=0, key_minor=False))

    read = data.read(track).analysis
    assert read is not None and read.bpm == 100.0 and read.bpm_user_edited
    assert (read.key_tonic, read.key_minor) == (0, False)


# ------------------------------------------------------------------ synced settings


def test_only_allowed_settings_are_read_and_written(setup: _Setup, qapp) -> None:
    synced = setup.context().synced_settings
    setup.settings.set("audio/device", "Speakers")
    setup.settings.set("profile/display_name", "Axel")

    assert synced.keys == SYNCED_SETTING_KEYS
    assert synced.read() == {"profile/display_name": "Axel"}  # the audio device never shows

    _in_worker(
        lambda: synced.write(
            {
                "playback/normalization": '{"level": "loud", "enabled": true}',
                "profile/display_name": "  Axel R  ",
            }
        )
    )

    assert setup.settings.get("profile/display_name") == "Axel R"
    assert setup.settings.get_json("playback/normalization") == {"enabled": True, "level": "loud"}
    assert _drain(qapp, lambda: bool(setup.applied))
    assert set(setup.applied[0]) == {"playback/normalization", "profile/display_name"}


@pytest.mark.parametrize(
    "key",
    [
        "audio/device",
        "player.volume",
        "plugins.sample.token",
        "play_log.device_id",
        "analysis/settings",
        "workspace/state",
        "",
    ],
)
def test_a_key_outside_the_allow_list_is_refused_and_nothing_is_stored(
    setup: _Setup, key: str
) -> None:
    synced = setup.context().synced_settings

    with pytest.raises(SettingNotSyncedError):
        synced.write({"profile/display_name": "Kept out", key: "x"})

    assert setup.settings.get(key) is None
    assert setup.settings.get("profile/display_name") is None  # the allowed key was not stored


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("profile/display_name", "   "),
        ("playback/normalization", "not json"),
        ("playback/normalization", '{"level": "deafening"}'),
        ("playback/normalization", '{"enabled": "yes"}'),
        ("playback/normalization", '["quiet"]'),
        ("playlists/columns", '{"widths": {"title": "wide"}}'),
        ("playlists/columns", '{"order": "title"}'),
        ("plugins.enabled", '{"a": 1}'),
        ("plugins.enabled", '["ok", ""]'),
    ],
)
def test_a_value_the_setting_cannot_hold_is_refused(setup: _Setup, key: str, value: str) -> None:
    with pytest.raises(ValueError):
        setup.context().synced_settings.write({key: value})

    assert setup.settings.get(key) is None


def test_the_allow_list_has_no_path_device_or_geometry() -> None:
    assert {
        "playback/normalization",
        "profile/display_name",
        "playlists/columns",
        "plugins.enabled",
    } == SYNCED_SETTING_KEYS


def test_a_plugin_hears_changes_of_others_but_not_its_own_writes(setup: _Setup, qapp) -> None:
    synced = setup.context().synced_settings
    heard: list[tuple[tuple[str, ...], bool]] = []
    main = threading.current_thread()
    cancel = synced.subscribe(
        lambda keys: heard.append((tuple(keys), threading.current_thread() is main))
    )

    synced.write({"profile/display_name": "Mine"})  # its own write
    setup.settings.set_json("playback/normalization", {"enabled": False, "level": "quiet"})
    _in_worker(lambda: setup.settings.set("audio/device", "Not synced"))
    _in_worker(lambda: setup.settings.set("profile/display_name", "Changed by the person"))

    assert heard == []  # queued for the graphical thread, nothing ran in the writer's thread
    assert _drain(qapp, lambda: len(heard) >= 2)
    qapp.processEvents()
    assert heard == [
        (("playback/normalization",), True),
        (("profile/display_name",), True),
    ]

    cancel()
    setup.settings.set("profile/display_name", "After cancel")
    qapp.processEvents()
    assert len(heard) == 2


# ------------------------------------------------------------------ snapshot and restore


def _counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("tracks", "playlists", "playlist_entries", "play_events", "settings")
        }


def test_a_snapshot_is_a_consistent_copy_that_opens_with_the_same_counts(
    setup: _Setup,
) -> None:
    context = setup.context()
    setup.playlists.create_playlist("Mine", setup.ids[:2])
    setup.play_log.insert_remote_events([_remote("e1", 1), _remote("e2", 2)])
    setup.settings.set("profile/display_name", "Snap")
    target = context.base_dir / "snapshots" / "library.db"

    written = _in_worker(lambda: context.database_snapshot.snapshot(target))

    assert written == target.resolve() and target.is_file()
    live = {
        table: int(
            setup.database.connection().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        )
        for table in ("tracks", "playlists", "playlist_entries", "play_events", "settings")
    }
    assert _counts(written) == live
    assert live["tracks"] == 3 and live["playlists"] == 1 and live["play_events"] == 2
    with sqlite3.connect(written) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert copy.execute("PRAGMA user_version").fetchone()[0] == setup.database.schema_version()
    assert not list(target.parent.glob("*-wal"))  # one file, no sidecar


def test_a_snapshot_stays_in_the_plugin_folder_and_never_replaces_a_file(
    setup: _Setup,
) -> None:
    database_snapshot = setup.context().database_snapshot
    inside = setup.context().base_dir / "one.db"

    _in_worker(lambda: database_snapshot.snapshot(inside))
    with pytest.raises(FileExistsError):
        _in_worker(lambda: database_snapshot.snapshot(inside))
    for outside in (
        setup.base / "elsewhere.db",
        setup.context().base_dir / ".." / "other-plugin" / "x.db",
        setup.context().base_dir.parent / "sample_extra" / "x.db",
    ):
        with pytest.raises(ValueError, match="own folder"):
            _in_worker(lambda target=outside: database_snapshot.snapshot(target))
        assert not outside.exists()


def test_snapshot_and_restore_must_not_run_on_the_graphical_thread(setup: _Setup) -> None:
    database_snapshot = setup.context().database_snapshot

    with pytest.raises(RuntimeError, match=r"context.jobs"):
        database_snapshot.snapshot(setup.context().base_dir / "gui.db")
    with pytest.raises(RuntimeError, match=r"context.jobs"):
        database_snapshot.request_restore(setup.base / "any.db")
    assert not (setup.context().base_dir / "gui.db").exists()


def test_a_snapshot_can_be_made_by_a_plugin_job(setup: _Setup) -> None:
    context = setup.context()
    made: list[Path] = []
    done = threading.Event()

    def work(_job: Any) -> None:
        made.append(context.database_snapshot.snapshot(context.base_dir / "job.db"))
        done.set()

    context.jobs.submit(work, label="Snapshot", visible=False)

    assert done.wait(10) and made[0].is_file()


def test_a_restore_goes_to_the_confirmation_of_settings_and_never_replaces_the_database(
    setup: _Setup, qapp, tmp_path: Path
) -> None:
    context = setup.context()
    notices: list[str] = []
    setup.host.noticeRaised.connect(notices.append)
    backup = _in_worker(lambda: context.database_snapshot.snapshot(context.base_dir / "b.db"))

    _in_worker(lambda: context.database_snapshot.request_restore(backup))

    assert setup.proposed == []  # queued for the graphical thread
    assert _drain(qapp, lambda: bool(setup.proposed))
    assert setup.proposed == [backup]
    assert any("offers a database backup" in notice for notice in notices)
    # The offer reaches the page model; only its confirmation schedules the restore.
    model = DataPrivacyModel(
        setup.database,
        RestoreLayout(tmp_path / "data"),
        setup.play_log,
        setup.jobs,
    )
    asked: list[bool] = []
    model.restoreProposed.connect(lambda: asked.append(True))
    model.propose_restore(setup.proposed[0])
    assert asked == [True]
    assert read_pending_restore(RestoreLayout(tmp_path / "data")) is None  # nothing scheduled
    url = model.takeProposedRestore()
    assert url.startswith("file:///") and url.endswith("b.db")
    assert model.takeProposedRestore() == ""  # offered once


def test_a_file_that_is_not_a_usable_backup_is_refused_before_the_page_hears_of_it(
    setup: _Setup, qapp
) -> None:
    context = setup.context()
    junk = context.base_dir / "junk.db"
    junk.parent.mkdir(parents=True)
    junk.write_bytes(b"not a database at all, just text")

    with pytest.raises(BackupValidationError):
        _in_worker(lambda: context.database_snapshot.request_restore(junk))
    with pytest.raises(BackupValidationError, match="does not exist"):
        _in_worker(lambda: context.database_snapshot.request_restore(context.base_dir / "no.db"))
    with pytest.raises(BackupValidationError, match="currently in use"):
        _in_worker(lambda: context.database_snapshot.request_restore(setup.database.path))

    qapp.processEvents()
    assert setup.proposed == []


def test_a_host_that_cannot_offer_a_restore_says_so(qapp, tmp_path: Path) -> None:
    created = _Setup(tmp_path)
    try:
        host = PluginHost(
            data_dir=tmp_path / "data",
            database=created.database,
            settings=created.settings,
            library=created.library,
            playlists=created.playlists,
            jobs=created.jobs,
            file_moves=FileMoveService(created.database, created.library, FileAccessCoordinator()),
            recycle=_Trash(),
            roots=_Roots(),
            refresh_playlists=lambda: None,
        )
        context = host.context_for(_MANIFEST)
        backup = _in_worker(lambda: context.database_snapshot.snapshot(context.base_dir / "b.db"))

        with pytest.raises(CapabilityUnavailableError):
            _in_worker(lambda: context.database_snapshot.request_restore(backup))
    finally:
        created.close()


# ------------------------------------------------------------------ the sample plugin


def test_the_sample_plugin_uses_every_capability(setup: _Setup, qapp, tmp_path: Path) -> None:
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

        lines = _in_worker(service.sync_probe)  # type: ignore[attr-defined]

        assert lines[0] == "play log 0 own, cursor None, appended 1 then 0"
        assert lines[1] == "playlist revision 1 to 2"
        assert lines[2] == "track data had analysis False"
        assert lines[3].startswith("synced settings 4 keys")
        assert lines[4].startswith("snapshot sample-")
        track = setup.analysis.get(setup.ids[0])
        assert track is not None and track.bpm == 128.0 and track.integrated_lufs == -9.5
        assert setup.settings.get("profile/display_name") == "Sample listener"
        assert (
            _counts(setup.base / "data" / "plugin-data" / "sample" / "snapshots" / "sample-0.db")[
                "play_events"
            ]
            == 1
        )
    finally:
        manager.unload_all()

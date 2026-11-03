"""Two devices with the core records, for the records tests (plan 126.7).

Each device is a plugin context over its own temporary database, with the play log, the playlists,
the track data and the synced settings of the core. The library the core answers the playlists and
the track data with is a stub (every track id exists), and the files are the fakes of
``helpers.FakeFiles``. Tracks are listed in the database's ``tracks`` table, as a scan would, so the
foreign keys of the core hold; a test never writes the plugin's own tables.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from mtee.plugins.remote.manifest import MANIFEST  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.store import RemoteStore  # pyright: ignore[reportMissingImports]
from tests.plugins.remote.conftest import PLUGIN_DIR
from tests.plugins.remote.helpers import FakeFiles, FakeLibrary, FakeTrackSources

from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.credit_override_repository import CreditOverrideRepository
from mtee.persistence.database import Database, discover_migrations
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.api import PluginContext
from mtee.plugins.context import PluginHost
from mtee.services.jobs import JobService
from mtee.services.playlist_service import PlaylistService

ARTIST = "Tester"


class CoreLibraryStub:
    """What the core's library answers the playlist service and the track data.

    Every track id exists. ``titles`` gives the title of a track; a track without one is named by
    its id. Every track has the artist ``Tester``, so a correction of that credit is accepted.
    """

    def __init__(self) -> None:
        self.titles: dict[str, str] = {}

    def track(self, track_id: str) -> dict[str, Any]:
        return {
            "id": track_id,
            "title": self.titles.get(track_id, track_id),
            "artist": ARTIST,
            "album": "",
            "path": f"/not-a-file/{track_id}",
            "rootId": "",
            "status": "readable",
            "filename": track_id,
        }

    def snapshot_of(self, track_id: str) -> SimpleNamespace:
        del track_id
        return SimpleNamespace(artist=(ARTIST,))

    def source_record(self, track_id: str) -> None:
        del track_id
        return None

    def artist_credit_rows(self) -> list[tuple[str, tuple[str, ...]]]:
        """Every registered track, with the artist it is credited with (as the core lists them)."""
        return [(track_id, (ARTIST,)) for track_id in self.titles]


@dataclasses.dataclass
class SyncDevice:
    """One computer of the test: its context, its link table, its folder and its client."""

    context: PluginContext
    stub: CoreLibraryStub
    store: RemoteStore
    library: FakeLibrary
    local: Path
    client: Any
    root_id: str
    core_device_id: str


def make_sync_context(
    folder: Path, library: FakeLibrary, core_device_id: str
) -> tuple[PluginContext, CoreLibraryStub]:
    """A plugin context with every core record of sync, over a temporary database in ``folder``."""
    database = Database(folder / "mtee.sqlite3")
    database.migrate()
    database.migrate_plugin("remote", discover_migrations(PLUGIN_DIR / "remote" / "migrations"))
    stub = CoreLibraryStub()
    host = PluginHost(
        data_dir=folder,
        database=database,
        settings=SettingsRepository(database),
        library=cast(Any, stub),
        playlists=cast(Any, PlaylistService(PlaylistsRepository(database), cast(Any, stub))),
        jobs=JobService(),
        file_moves=MagicMock(),
        recycle=MagicMock(),
        roots=MagicMock(),
        refresh_playlists=lambda: None,
        play_log=PlayLogRepository(database),
        device_id=core_device_id,
        analysis=AnalysisRepository(database),
        credit_overrides=CreditOverrideRepository(database),
        source_tracks=SourceTrackRepository(database),
    )
    context = host.context_for(MANIFEST)
    sources = _sources_of(context, library)
    context = dataclasses.replace(
        context,
        library=cast(Any, library),
        files=cast(Any, FakeFiles(library, folder / "recycle", sources)),
        track_sources=cast(Any, sources),
        base_dir=folder / "plugin-data" / "remote",
        run_on_gui=lambda call: call(),
    )
    return context, stub


def _sources_of(context: PluginContext, library: FakeLibrary) -> FakeTrackSources:
    return FakeTrackSources(context.track_sources, library, context.database)


def register_track(device: SyncDevice, track_id: str, title: str) -> None:
    """List a track in the core database, as a scan would (the foreign keys of the core need it)."""
    device.stub.titles[track_id] = title
    device.context.database.connection().execute(
        "INSERT OR IGNORE INTO tracks(track_id) VALUES (?)", (track_id,)
    )


def record_play(device: SyncDevice, track_id: str, seconds: int = 90) -> str:
    """Append a counted listening of ``track_id`` to the device's play log; return its event id."""
    started = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=5)
    event_id = str(uuid.uuid4())
    event = PlayEvent(
        event_id=event_id,
        track=PlayedTrack(
            track_id=track_id,
            path=f"/not-a-file/{track_id}",
            artist=ARTIST,
            title=device.stub.titles.get(track_id, track_id),
            album="",
            duration_us=180_000_000,
        ),
        started_at=started,
        ended_at=started + timedelta(seconds=seconds),
        heard_ms=seconds * 1000,
        counted=True,
    )
    PlayLogRepository(device.context.database).insert_events(
        [event], device.context.play_log.device_id
    )
    return event_id


def journal_kinds(client: Any) -> list[str]:
    """The kinds of every entry of the caller's journal on the server, oldest first."""
    kinds: list[str] = []
    since = 0
    while True:
        page = client.changes(since=since, limit=500)
        kinds.extend(str(change["kind"]) for change in page.changes)
        since = page.next
        if not page.more:
            return kinds


def local_playlist_of(store: RemoteStore, server_playlist_id: str) -> str | None:
    """The local playlist linked to a server playlist, or None."""
    row = (
        store.connection()
        .execute(
            "SELECT local_playlist_id FROM remote_playlists WHERE server_playlist_id = ?",
            (server_playlist_id,),
        )
        .fetchone()
    )
    return None if row is None else str(row["local_playlist_id"])


def server_playlist_of(store: RemoteStore, local_playlist_id: str) -> str | None:
    """The server playlist linked to a local playlist, or None."""
    row = (
        store.connection()
        .execute(
            "SELECT server_playlist_id FROM remote_playlists WHERE local_playlist_id = ?",
            (local_playlist_id,),
        )
        .fetchone()
    )
    return None if row is None else str(row["server_playlist_id"])


def log_texts(store: RemoteStore) -> list[str]:
    """The lines of the plugin's activity log, oldest first."""
    rows = store.connection().execute("SELECT text FROM remote_log ORDER BY log_id").fetchall()
    return [str(row["text"]) for row in rows]


def new_device_id() -> str:
    return str(uuid.uuid4())

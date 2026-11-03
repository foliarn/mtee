"""Tracks that a plugin provides without a file: storage, views, migration 030 and the guards.

Everything runs on a temporary SQLite database and copies of tiny files; nothing of the user's
library is touched (plan 125.2).
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, cast

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.metadata_edit import MetadataPatch
from mtee.domain.source_tracks import NonFileTrackError, SourceTrack
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.models.trash_model import TrashModel
from mtee.persistence.database import MIGRATIONS_DIR, Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.persistence.play_log_repository import PlayLogRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.persistence.trash_repository import TrashRepository
from mtee.services.analysis_service import AnalysisService
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.metadata_writer import MetadataEditService
from mtee.services.playlist_service import PlaylistService

PLUGIN = "remote"


def _track(key: str, title: str = "Title", **extra: Any) -> SourceTrack:
    return SourceTrack(key, title, artists=("Ann & Bob",), album="Album", **extra)


class _Store:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.path = base / "mtee.sqlite3"
        self.database = Database(self.path)
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.sources = SourceTrackRepository(self.database)
        self.music = base / "music"
        self.music.mkdir()

    def add_file_track(self, name: str = "local.wav") -> str:
        root = self.library.add_root(self.music)
        generation = self.library.begin_scan(str(root["id"]))
        path = self.music / name
        path.write_bytes(b"audio fixture")
        track_id = self.library.upsert_location(
            str(root["id"]),
            name,
            path,
            SourceRevision.observe(path),
            MetadataSnapshot(
                title=("Local",), artist=("Ann",), technical=TechnicalInfo(duration_us=1_000_000)
            ),
            generation,
        )
        self.library.finish_scan(str(root["id"]), generation, complete=True)
        return track_id

    def reopen(self) -> _Store:
        self.database.close()
        return _Store.__new__(_Store)._attach(self.base)

    def _attach(self, base: Path) -> _Store:
        self.base = base
        self.path = base / "mtee.sqlite3"
        self.database = Database(self.path)
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.sources = SourceTrackRepository(self.database)
        self.music = base / "music"
        return self


@pytest.fixture
def store(tmp_path: Path):
    value = _Store(tmp_path)
    yield value
    value.database.close()


# --- migration 030 ------------------------------------------------------------------------


def test_migration_030_creates_the_table_on_an_empty_database(tmp_path: Path) -> None:
    database = Database(tmp_path / "mtee.sqlite3")
    applied = database.migrate()
    assert {m.version: m.name for m in applied}[30] == "plugin_source_tracks"
    assert applied[-1].version == 31
    columns = {
        str(row["name"])
        for row in database.connection().execute("PRAGMA table_info(plugin_source_tracks)")
    }
    assert columns == {
        "plugin_id",
        "source_key",
        "track_id",
        "metadata_json",
        "album_artist",
        "available",
        "revision",
        "updated_at_utc",
    }
    assert database.schema_version() == 31
    database.close()


def test_migration_030_on_a_populated_schema_29_database_keeps_the_data_and_backs_up(
    tmp_path: Path,
) -> None:
    older = tmp_path / "migrations-29"
    older.mkdir()
    for script in MIGRATIONS_DIR.glob("*.sql"):
        if script.name < "030_":
            shutil.copyfile(script, older / script.name)
    path = tmp_path / "data" / "mtee.sqlite3"
    first = Database(path, migrations_dir=older)
    first.migrate()
    assert first.schema_version() == 29
    library = LibraryRepository(first)
    music = tmp_path / "music"
    music.mkdir()
    root = library.add_root(music)
    generation = library.begin_scan(str(root["id"]))
    file_path = music / "a.wav"
    file_path.write_bytes(b"audio")
    track_id = library.upsert_location(
        str(root["id"]),
        "a.wav",
        file_path,
        SourceRevision.observe(file_path),
        MetadataSnapshot(title=("A",), artist=("B",)),
        generation,
    )
    playlists = PlaylistService(PlaylistsRepository(first), library)
    playlist_id = playlists.create_playlist("Mine", [track_id])
    first.close()

    second = Database(path)
    applied = second.migrate()
    assert [m.version for m in applied] == [30, 31]
    assert second.schema_version() == 31
    (backup,) = path.parent.glob("mtee.sqlite3.v29.*.backup")
    assert backup.stat().st_size > 0
    # The data written before the migration is still there, and the new table starts empty.
    assert LibraryRepository(second).track(track_id)["title"] == "A"
    assert [
        r["trackId"]
        for r in PlaylistService(PlaylistsRepository(second), library).rows(playlist_id)
    ] == [track_id]
    assert (
        second.connection().execute("SELECT COUNT(*) FROM plugin_source_tracks").fetchone()[0] == 0
    )
    second.close()


# --- upsert, remove, list -----------------------------------------------------------------


def test_upsert_is_idempotent_and_returns_stable_track_ids(store: _Store) -> None:
    tracks = [_track("a"), _track("b", "Other", track_number=2, year=2020, duration_us=5_000_000)]
    first, changed = store.sources.upsert(PLUGIN, tracks)
    assert sorted(first) == ["a", "b"] and len(changed) == 2
    TrackId.parse(first["a"])  # a normal per-machine UUID

    second, changed_again = store.sources.upsert(PLUGIN, tracks)
    assert second == first
    assert changed_again == []  # nothing changed: nothing to announce
    assert [e.source_key for e in store.sources.entries(PLUGIN)] == ["a", "b"]
    assert store.database.connection().execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 2


def test_a_changed_track_keeps_its_id_and_raises_the_revision(store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a", "Old")])
    before = store.library.track(identities["a"])
    _, changed = store.sources.upsert(PLUGIN, [_track("a", "New")])
    after = store.library.track(identities["a"])
    assert changed == [identities["a"]]
    assert (before["title"], after["title"]) == ("Old", "New")
    assert after["revision"] == before["revision"] + 1  # the cover is read again


def test_a_track_listed_twice_in_one_call_keeps_its_last_version(store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a", "First"), _track("a", "Last")])
    assert len(identities) == 1
    assert store.library.track(identities["a"])["title"] == "Last"


def test_ids_are_stable_across_a_restart(store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a"), _track("b")])
    reopened = store.reopen()
    again, changed = reopened.sources.upsert(PLUGIN, [_track("b"), _track("a")])
    assert again == identities
    assert changed == []
    assert reopened.library.track(identities["a"])["sourceKey"] == "a"
    reopened.database.close()


def test_the_same_key_of_two_plugins_is_two_tracks(store: _Store) -> None:
    one, _ = store.sources.upsert("remote", [_track("k")])
    two, _ = store.sources.upsert("other", [_track("k")])
    assert one["k"] != two["k"]
    assert store.library.source_origin(one["k"]) == ("remote", "k")
    assert store.library.source_origin(two["k"]) == ("other", "k")
    assert [e.source_key for e in store.sources.entries("other")] == ["k"]


def test_remove_makes_the_track_unavailable_and_is_idempotent(store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a"), _track("b")])
    assert store.sources.remove(PLUGIN, ["a", "missing"]) == [identities["a"]]
    assert store.sources.remove(PLUGIN, ["a"]) == []  # already removed
    entries = {e.source_key: e for e in store.sources.entries(PLUGIN)}
    assert entries["a"].available is False and entries["b"].available is True
    assert [e.source_key for e in store.sources.entries(PLUGIN, available_only=True)] == ["b"]
    assert entries["a"].track_id == identities["a"]  # the id is kept
    assert store.library.track(identities["a"])["status"] == "unreadable"

    again, changed = store.sources.upsert(PLUGIN, [_track("a")])
    assert again["a"] == identities["a"] and changed == [identities["a"]]
    assert store.library.track(identities["a"])["status"] == "readable"


def test_a_removed_track_keeps_its_playlist_entry_and_its_play_log_rows(store: _Store) -> None:
    from datetime import UTC, datetime, timedelta

    from mtee.domain.play_log import PlayedTrack, PlayEvent

    identities, _ = store.sources.upsert(PLUGIN, [_track("a", "Streamed")])
    track_id = identities["a"]
    playlists = PlaylistService(PlaylistsRepository(store.database), store.library)
    playlist_id = playlists.create_playlist("Mixed", [track_id])
    started = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    PlayLogRepository(store.database).insert_events(
        [
            PlayEvent(
                event_id="e1",
                track=PlayedTrack(
                    track_id=track_id,
                    path="",
                    artist="Ann & Bob",
                    title="Streamed",
                    album="Album",
                    duration_us=0,
                ),
                started_at=started,
                ended_at=started + timedelta(seconds=40),
                heard_ms=40_000,
                counted=True,
            )
        ],
        "11111111-1111-1111-1111-111111111111",
    )
    (live,) = playlists.rows(playlist_id)
    assert live["available"] is True and live["trackId"] == track_id

    store.sources.remove(PLUGIN, ["a"])

    (gone,) = playlists.rows(playlist_id)
    assert gone["trackId"] == track_id  # the entry survives
    assert gone["available"] is False  # greyed out, never played
    assert gone["title"] == "Streamed"
    rows = store.database.connection().execute("SELECT track_id FROM play_events").fetchall()
    assert [r["track_id"] for r in rows] == [track_id]


# --- the views read the tracks ------------------------------------------------------------


def test_the_library_rows_carry_the_metadata_and_no_file(store: _Store) -> None:
    identities, _ = store.sources.upsert(
        PLUGIN,
        [
            SourceTrack(
                "a",
                "Song",
                artists=("Ann", "Bob"),
                album="Album",
                album_artist="Ann",
                track_number=3,
                duration_us=185_000_000,
                genre=("Dub",),
                year=2019,
            )
        ],
    )
    row = store.library.track(identities["a"])
    assert row["id"] == identities["a"]
    assert (row["title"], row["artist"], row["album"], row["genre"]) == (
        "Song",
        "Ann, Bob",
        "Album",
        "Dub",
    )
    assert (row["trackNumber"], row["year"], row["albumArtist"]) == ("3", "2019", "Ann")
    assert (row["durationUs"], row["seconds"], row["duration"]) == (185_000_000, 185, "3:05")
    assert row["sourcePluginId"] == PLUGIN and row["sourceKey"] == "a"
    assert row["path"] == "" and row["filename"] == "" and row["rootId"] == ""
    assert row["status"] == "readable"
    assert row["coverUrl"].startswith(f"image://artwork/{identities['a']}/")
    assert store.library.tracks_by_ids([identities["a"], "unknown"]) == [row]
    assert store.library.source_record(identities["a"]) is None  # never handed to file code


def test_a_file_track_has_no_source_keys(store: _Store) -> None:
    file_id = store.add_file_track()
    row = store.library.track(file_id)
    assert "sourcePluginId" not in row
    assert store.library.source_origin(file_id) is None
    assert store.library.non_file_refusal(file_id, "moved") == ""


def test_artist_credits_include_the_available_tracks_of_running_plugins(store: _Store) -> None:
    file_id = store.add_file_track()
    identities, _ = store.sources.upsert(PLUGIN, [_track("a"), _track("b")])
    store.sources.remove(PLUGIN, ["b"])
    credited = dict(store.library.artist_credit_rows())
    assert credited[file_id] == ("Ann",)
    assert credited[identities["a"]] == ("Ann & Bob",)
    assert identities["b"] not in credited  # removed: not listed

    store.library.set_running_source_plugins({"another"}, {})
    assert identities["a"] not in dict(store.library.artist_credit_rows())
    row = store.library.track(identities["a"])
    assert row["status"] == "unreadable"  # nothing can open it: an unavailable row


def test_the_refusal_names_the_plugin_by_its_title(store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a")])
    assert "remote" in store.library.non_file_refusal(identities["a"], "moved")
    store.library.set_running_source_plugins({PLUGIN}, {PLUGIN: "MTEE Remote"})
    assert store.library.non_file_refusal(identities["a"], "moved") == (
        "This track is provided by MTEE Remote and has no file on this computer, "
        "so it cannot be moved."
    )


# --- file operations refuse a track without a file ----------------------------------------


def test_tag_writes_refuse_a_track_without_a_file(store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a")])
    track_id = identities["a"]
    writer = MetadataEditService(
        store.library, MetadataHistoryRepository(store.database), FileAccessCoordinator()
    )

    capabilities = writer.capabilities(track_id)
    assert capabilities and all(not allowed for allowed, _reason in capabilities.values())
    assert all("no file on this computer" in reason for _allowed, reason in capabilities.values())
    with pytest.raises(NonFileTrackError, match="no file on this computer"):
        writer.inspect(track_id)
    result = writer.save(
        track_id, SourceRevision(0, 0), MetadataPatch.from_mapping({"title": "Hacked"}), "draft"
    )
    assert result.status == "failed" and "no file on this computer" in result.message
    undone = writer.undo("unknown-operation", "draft")
    assert undone.status == "failed"  # an unknown operation, no crash
    assert store.library.track(track_id)["title"] == "Title"


def test_moving_refuses_a_track_without_a_file(store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a")])
    service = FileMoveService(store.database, store.library, FileAccessCoordinator())
    folder = store.music / "Elsewhere"
    result = service.move(identities["a"], folder)
    assert result.status == "conflict"
    assert "no file on this computer" in result.message
    assert not folder.exists()


def test_analysis_refuses_a_track_without_a_file(store: _Store) -> None:
    from mtee.persistence.analysis_repository import AnalysisRepository

    identities, _ = store.sources.upsert(PLUGIN, [_track("a")])
    service = AnalysisService(
        store.library, AnalysisRepository(store.database), cast(Any, object()), None
    )
    report = service.analyze_track(identities["a"], cast(Any, None))
    assert report.ok is False
    assert "no file on this computer" in report.message


def test_recycling_refuses_a_track_without_a_file(qapp, store: _Store) -> None:
    identities, _ = store.sources.upsert(PLUGIN, [_track("a")])
    jobs = JobService(max_thread_count=2)
    model = TrashModel(
        store.library,
        jobs,
        cast(Any, object()),  # the Shell is never reached
        FileAccessCoordinator(),
        TrashRepository(store.database),
    )
    try:
        model.request_recycle([identities["a"]])
        deadline = time.monotonic() + 15
        while model.state == "preparing" and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert jobs.wait_for_done(15_000)
        qapp.processEvents()
        assert not model.canConfirm  # nothing to confirm
        (item,) = cast(list[dict[str, Any]], model.results)
        assert item["status"] == "conflict"
        assert "no file on this computer" in item["message"]
    finally:
        jobs.shutdown(2_000)


def test_the_plugin_files_api_refuses_a_track_without_a_file(store: _Store) -> None:
    from mtee.plugins.context import PluginHost

    identities, _ = store.sources.upsert(PLUGIN, [_track("a")])
    host = PluginHost(
        data_dir=store.base / "data",
        database=store.database,
        settings=cast(Any, object()),
        library=store.library,
        playlists=cast(Any, object()),
        jobs=cast(Any, object()),
        file_moves=FileMoveService(store.database, store.library, FileAccessCoordinator()),
        recycle=cast(Any, object()),
        roots=cast(Any, object()),
        refresh_playlists=lambda: None,
    )
    from mtee.plugins.api import PluginManifest

    context = host.context_for(
        PluginManifest(PLUGIN, "Remote", "", "1", 1, "mtee.plugins.remote:c")
    )
    root = store.library.add_root(store.music)
    result = context.files.move_track(identities["a"], str(root["id"]), "")
    assert result.status == "conflict" and "no file on this computer" in result.message
    assert context.library.tracks([identities["a"]]) == []  # `library` lists files only


# --- the cover comes from the plugin, on demand -------------------------------------------


def test_the_artwork_provider_asks_the_plugin_for_the_cover_of_its_track(
    qapp, store: _Store
) -> None:
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QColor, QImage

    from mtee.models.artwork_provider import ArtworkProvider
    from mtee.services.artwork_service import ArtworkService, placeholder_image

    class _Decoder(ArtworkService):
        """Decoding is tested in tests/unit/test_source_track_cover.py; here only who is asked."""

        def thumbnail_from_bytes(self, data: bytes | None, size: int, seed: str) -> QImage:
            if not data:
                return placeholder_image(seed, size)
            image = QImage(8, 8, QImage.Format.Format_RGB32)
            image.fill(QColor(200, 30, 30))
            return image

    identities, _ = store.sources.upsert(PLUGIN, [_track("with-cover"), _track("without")])
    asked: list[tuple[str, str]] = []

    def cover(plugin_id: str, key: str) -> bytes | None:
        asked.append((plugin_id, key))
        return b"image bytes" if key == "with-cover" else None

    provider = ArtworkProvider(store.library, _Decoder(), source_cover=cover)

    def request(key: str) -> QImage:
        track_id = identities[key]
        revision = store.library.track(track_id)["revision"]
        return provider.requestImage(f"{track_id}/{revision}/64", QSize(), QSize(64, 64))

    real, placeholder = request("with-cover"), request("without")
    assert asked == [(PLUGIN, "with-cover"), (PLUGIN, "without")]
    assert (real.width(), real.height()) == (8, 8)  # the plugin's image
    assert placeholder.width() == 64  # no cover: the usual placeholder
    request("with-cover")
    assert len(asked) == 2  # the cover that was found is cached
    request("without")
    assert len(asked) == 3  # a missing cover is asked again, the plugin may have it later

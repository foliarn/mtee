"""Repeatable synthetic schema-020 baseline, without touching a personal library."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.services.playlist_service import PlaylistService


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, encoding="utf-8").strip()


def prepare_fixtures(data_dir: Path) -> dict[str, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    base_path = data_dir / "synthetic-020.sqlite"
    if not base_path.exists():
        baseline_schema = data_dir / "baseline-schema-020"
        baseline_schema.mkdir(exist_ok=True)
        for migration in Database(data_dir / "unused.sqlite").migrations:
            if migration.version <= 20:
                (baseline_schema / migration.file_name).write_text(
                    migration.read_sql(), encoding="utf-8"
                )
        database = Database(base_path, migrations_dir=baseline_schema)
        database.migrate()
        database.close()
    base = Database(base_path)
    if base.schema_version() != 20:
        raise RuntimeError("The baseline fixture must use schema 020")
    base.close()

    return {"020": base_path}


def _populate(database: Database, data_dir: Path, count: int) -> tuple[str, str]:
    root_id = str(uuid5(NAMESPACE_URL, "mtee-110-root"))
    playlist_id = str(uuid5(NAMESPACE_URL, "mtee-110-playlist"))
    connection = database.connection()
    found = connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    if found == count:
        return root_id, playlist_id
    if found:
        raise RuntimeError("Fixture size differs; use a new --data-dir for this measurement")
    root_path = data_dir / "synthetic-library"
    with database.transaction() as transaction:
        transaction.execute(
            "INSERT INTO library_roots(root_id,path,path_key,name) VALUES(?,?,?,?)",
            (root_id, str(root_path), str(root_path).casefold(), "Synthetic library"),
        )
        transaction.execute(
            "INSERT INTO playlists(playlist_id,name,ordinal,updated_at_utc) VALUES(?,?,0,?)",
            (playlist_id, "Synthetic playlist", datetime.now(UTC).isoformat()),
        )
        tracks = []
        locations = []
        membership = []
        entries = []
        for index in range(count):
            identity = str(uuid5(NAMESPACE_URL, f"mtee-110-measure-{index}"))
            folder = "House" if index < 340 else "Other"
            relative = f"{folder}/Track {index:05d}.wav"
            path = root_path / relative
            tracks.append((identity,))
            locations.append(
                (str(path).casefold(), identity, str(path), 1024, 1, 0, "readable", "{}")
            )
            membership.append((root_id, identity, relative, 0))
            entries.append(
                (
                    str(uuid5(NAMESPACE_URL, f"mtee-110-entry-{index}")),
                    playlist_id,
                    identity,
                    index,
                    "{}",
                )
            )
        transaction.executemany("INSERT INTO tracks(track_id) VALUES(?)", tracks)
        transaction.executemany(
            "INSERT INTO track_locations("
            "path_key,track_id,path,size_bytes,mtime_ns,generation,status,metadata_json) "
            "VALUES(?,?,?,?,?,?,?,?)",
            locations,
        )
        transaction.executemany(
            "INSERT INTO root_tracks(root_id,track_id,relative_path,seen_generation) "
            "VALUES(?,?,?,?)",
            membership,
        )
        transaction.executemany(
            "INSERT INTO playlist_entries(entry_id,playlist_id,track_id,ordinal,snapshot_json) "
            "VALUES(?,?,?,?,?)",
            entries,
        )
    return root_id, playlist_id


def _sample(operation: Callable[[], object], repeats: int = 5) -> dict[str, float]:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
    }


def _startup(data_dir: Path) -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mtee",
            "--demo",
            "--smoke-test",
            "--data-dir",
            str(data_dir / "startup"),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )


def _measure_ui(
    data_dir: Path, database: Database, root_id: str, playlist_id: str, count: int
) -> dict[str, object]:
    """Probe the current MTEE QML view using an isolated copy of the fixture."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    from mtee.app import _build_runtime, _destroy_windows, _shutdown, create_application
    from mtee.cli import AppOptions
    from mtee.models.playlists_model import PlaylistsModel
    from mtee.models.track_list_model import TrackListModel
    from mtee.models.workspace_model import WorkspaceModel

    runtime_dir = data_dir / f"ui-runtime-{uuid4().hex[:8]}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    database.backup_to(runtime_dir / "mtee.sqlite3")
    application = create_application(["mtee-110-baseline"])
    runtime = _build_runtime(application, AppOptions(data_dir=runtime_dir))
    if runtime is None or not isinstance(runtime.workspace, WorkspaceModel):
        raise RuntimeError("Could not load the source application against the synthetic copy")
    window = runtime.engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("The source application did not create a Quick window")
    window.resize(1440, 900)
    workspace = runtime.workspace

    def wait_for_rows(tab_id: str, expected: int) -> float:
        started = time.perf_counter()
        observed = -1
        while time.perf_counter() - started < 15:
            QCoreApplication.processEvents()
            model = workspace._track_models.get(tab_id)
            if isinstance(model, TrackListModel):
                observed = model.rowCount()
            if observed == expected:
                window.grabWindow()
                return (time.perf_counter() - started) * 1000
            time.sleep(0.005)
        raise TimeoutError(f"The source view showed {observed}, expected {expected} rows")

    def find_item(name: str) -> QQuickItem:
        pending = [window.contentItem()]
        while pending:
            item = pending.pop()
            if item.objectName() == name:
                return item
            pending.extend(item.childItems())
        raise LookupError(f"Could not find QML item {name}")

    try:
        folder_tab = f"folder:{root_id}/House"
        workspace.openFolder(folder_tab)
        folder_ms = wait_for_rows(folder_tab, 340)
        listing = find_item("trackRowsList")
        scroll_times = []
        for offset in (800, 1600, 2400, 3200, 0):
            started = time.perf_counter_ns()
            listing.setProperty("contentY", offset)
            QCoreApplication.processEvents()
            window.grabWindow()
            scroll_times.append((time.perf_counter_ns() - started) / 1_000_000)

        ids = [
            row["id"]
            for row in LibraryRepository(runtime.database).tracks_in_folder(root_id, "House")
        ]
        selection_times = []
        for identity in ids[:5]:
            started = time.perf_counter_ns()
            workspace.selectTrack(identity, "single", ids)
            QCoreApplication.processEvents()
            window.grabWindow()
            selection_times.append((time.perf_counter_ns() - started) / 1_000_000)

        playlist_model = cast(PlaylistsModel, workspace.playlistModel)
        started = time.perf_counter()
        while not playlist_model.details(playlist_id) and time.perf_counter() - started < 15:
            QCoreApplication.processEvents()
            time.sleep(0.005)
        if not playlist_model.details(playlist_id):
            raise TimeoutError("The synthetic playlist did not appear in the sidebar model")
        workspace.openPlaylist(playlist_id)
        playlist_tab = f"playlist:{playlist_id}"
        playlist_ms = wait_for_rows(playlist_tab, count)
        return {
            "folder_open_to_render_ms": round(folder_ms, 3),
            "playlist_open_to_render_ms": round(playlist_ms, 3),
            "scroll_render_ms": {
                "median_ms": round(statistics.median(scroll_times), 3),
                "min_ms": round(min(scroll_times), 3),
                "max_ms": round(max(scroll_times), 3),
            },
            "selection_render_ms": {
                "median_ms": round(statistics.median(selection_times), 3),
                "min_ms": round(min(selection_times), 3),
                "max_ms": round(max(selection_times), 3),
            },
            "note": "Offscreen programmatic scroll/selection plus grabWindow; not pointer timing",
        }
    finally:
        _shutdown(runtime)
        _destroy_windows(runtime)
        application.quit()


def _measure_native_playback(data_dir: Path) -> dict[str, float]:
    """Time explicit Play until the shared native service reports Playing."""
    from PySide6.QtCore import QCoreApplication

    from mtee.app import create_application
    from mtee.domain.playback import PlaybackStatus
    from mtee.prototypes.genre_manager_110 import GenreReviewPrototype

    create_application(["mtee-110-native-measure"])
    prototype = GenreReviewPrototype(
        data_dir / "native-latency", "selection", "house", silent_audio=True
    )
    if prototype._player is None or prototype.playerError:
        raise RuntimeError("The native player did not initialize for the baseline probe")
    samples = []
    try:
        for row in prototype._tracks[:5]:
            started = time.perf_counter_ns()
            prototype.playTrack(row["id"])
            while (time.perf_counter_ns() - started) < 10_000_000_000:
                QCoreApplication.processEvents()
                if (
                    prototype._player.state.current_id == row["id"]
                    and prototype._player.state.status is PlaybackStatus.PLAYING
                ):
                    samples.append((time.perf_counter_ns() - started) / 1_000_000)
                    break
                time.sleep(0.005)
            else:
                raise TimeoutError("The native service did not report Playing")
    finally:
        prototype.close()
        QCoreApplication.processEvents()
    return {
        "median_ms": round(statistics.median(samples), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
    }


def _measure_plugin_ui(
    data_dir: Path, database: Database, root_id: str, count: int
) -> dict[str, object]:
    """Time the real plugin page on a separate synthetic database copy."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    from mtee.app import _build_runtime, _destroy_windows, _shutdown, create_application
    from mtee.cli import AppOptions
    from mtee.models.track_list_model import TrackListModel
    from mtee.models.workspace_model import WorkspaceModel
    from mtee.plugins.genre_manager.models import GenreManagerModel

    runtime_dir = data_dir / f"plugin-ui-{uuid4().hex[:8]}"
    runtime_dir.mkdir(parents=True)
    database.backup_to(runtime_dir / "mtee.sqlite3")
    application = create_application(["mtee-110-plugin-measure"])
    runtime = _build_runtime(application, AppOptions(data_dir=runtime_dir))
    if runtime is None:
        raise RuntimeError("Could not open the plugin on the synthetic database")
    if not isinstance(runtime.workspace, WorkspaceModel):
        raise RuntimeError("Could not bind the plugin to the source workspace")
    window = runtime.engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("The source application did not create a Quick window")
    window.resize(1440, 900)
    workspace = runtime.workspace

    def wait_ready(expected: int) -> float:
        started = time.perf_counter()
        while time.perf_counter() - started < 20:
            QCoreApplication.processEvents()
            manager = cast(GenreManagerModel | None, workspace.genreManager)
            if (
                manager is not None
                and not cast(dict[str, object], manager.state)["busy"]
                and cast(dict[str, object], manager.state)["total"] == expected
            ):
                window.grabWindow()
                return (time.perf_counter() - started) * 1000
            time.sleep(0.005)
        raise TimeoutError(f"Genre Manager did not show {expected} synthetic rows")

    try:
        lazy_before_open = workspace.genreManager is None
        started = time.perf_counter()
        workspace.openGenreManagerView("classify", "Genre Manager")
        manager = cast(GenreManagerModel | None, workspace.genreManager)
        while manager is not None and cast(dict[str, object], manager.state)["busy"]:
            if time.perf_counter() - started > 20:
                raise TimeoutError("Genre Manager did not load")
            QCoreApplication.processEvents()
            time.sleep(0.005)
        if manager is None:
            raise RuntimeError("Genre Manager was not created")
        opened_ms = (time.perf_counter() - started) * 1000
        manager.openSource("folder", "House", root_id, False)
        folder_ms = wait_ready(340)
        pending: list[QQuickItem] = [window.contentItem()]
        listing = None
        while pending:
            item = pending.pop()
            if item.objectName() == "genreTrackList":
                listing = item
                break
            pending.extend(item.childItems())
        if listing is None:
            raise RuntimeError("Genre Manager track list was not rendered")
        scroll_samples = []
        for offset in (800, 1600, 2400, 3200, 0):
            start = time.perf_counter_ns()
            listing.setProperty("contentY", offset)
            QCoreApplication.processEvents()
            window.grabWindow()
            scroll_samples.append((time.perf_counter_ns() - start) / 1_000_000)
        ids = cast(TrackListModel, manager.rowsModel).track_ids_snapshot()
        feedback_samples = []
        for identity in ids[:5]:
            start = time.perf_counter_ns()
            manager.selectTrack(identity, False, False)
            QCoreApplication.processEvents()
            window.grabWindow()
            feedback_samples.append((time.perf_counter_ns() - start) / 1_000_000)
        playlist_id = str(uuid5(NAMESPACE_URL, "mtee-110-playlist"))
        manager.openSource("playlist", playlist_id, "", False)
        playlist_ms = wait_ready(count)
        return {
            "lazy_before_open": lazy_before_open,
            "plugin_open_ms": round(opened_ms, 3),
            "folder_open_to_render_ms": round(folder_ms, 3),
            "playlist_open_to_render_ms": round(playlist_ms, 3),
            "scroll_render_ms": _summary(scroll_samples),
            "selection_render_ms": _summary(feedback_samples),
            "note": "Offscreen programmatic timings including grabWindow; no pointer timing",
        }
    finally:
        _shutdown(runtime)
        _destroy_windows(runtime)
        application.quit()


def _summary(samples: list[float]) -> dict[str, float]:
    return {
        "median_ms": round(statistics.median(samples), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("baseline", "plugin"), default="baseline")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=(340, 2800, 10000), default=2800)
    parser.add_argument("--with-ui", action="store_true", help="Probe QML with this synthetic copy")
    options = parser.parse_args()
    data_dir = options.data_dir.resolve()
    fixtures = prepare_fixtures(data_dir)
    base = Database(fixtures["020"])
    root_id, playlist_id = _populate(base, data_dir, options.count)
    if options.mode == "plugin":
        plugin_path = data_dir / f"synthetic-plugin-{uuid4().hex[:8]}.sqlite"
        base.backup_to(plugin_path)
        base.close()
        database = Database(plugin_path)
        database.migrate()
    else:
        database = base
    library = LibraryRepository(database)
    playlists = PlaylistService(PlaylistsRepository(database), library)
    measures: dict[str, object] = {
        "startup_offscreen_demo": _sample(lambda: _startup(data_dir)),
        "folder": _sample(lambda: library.tracks_in_folder(root_id, "House")),
        "playlist": _sample(lambda: playlists.rows(playlist_id)),
        "selection_ids": _sample(
            lambda: [row["id"] for row in library.tracks_in_folder(root_id, "House")[:340]]
        ),
    }
    if options.mode == "plugin":
        from mtee.plugins.genre_manager.repository import GenreManagerRepository
        from mtee.plugins.genre_manager.sessions import GenreSessionRepository

        repository = GenreManagerRepository(database)
        repository.ensure_catalogue()
        sessions = GenreSessionRepository(database, library, PlaylistsRepository(database))
        folder_session = sessions.open_source("folder", "House", root_id=root_id)
        playlist_session = sessions.open_source("playlist", playlist_id)
        measures["catalogue"] = _sample(repository.genres)
        measures["source_options"] = _sample(sessions.source_options)
        measures["classify_340_rows"] = _sample(lambda: sessions.rows(folder_session["session_id"]))
        measures["large_playlist_rows"] = _sample(
            lambda: sessions.rows(playlist_session["session_id"])
        )
    if options.with_ui:
        if options.mode == "plugin":
            measures["plugin_ui_offscreen"] = _measure_plugin_ui(
                data_dir, database, root_id, options.count
            )
        else:
            measures["source_ui_offscreen"] = _measure_ui(
                data_dir, database, root_id, playlist_id, options.count
            )
            measures["native_play_to_playing_null_audio"] = _measure_native_playback(data_dir)
    result = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "revision": _git("rev-parse", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "mode": options.mode,
        "synthetic_count": options.count,
        "schema_version": database.schema_version(),
        "measurements": measures,
        "not_measured": (
            ["audible output", "pointer-to-feedback timing"]
            if options.with_ui
            else ["source QML rendering", "scroll", "selection feedback", "native playback"]
        ),
    }
    database.close()
    output = data_dir / f"{options.mode}-results.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Helpers of the remote plugin tests: audio copies, a fake local library, a real plugin context.

The local side of the first match is faked: ``FakeLibrary`` exposes the tracks with their real
file paths, and ``FakeFiles.read_lease`` yields those paths. Everything else (the database, the
settings, the jobs' helpers and the ffmpeg runtime) is the real one, from ``PluginHost``.
Audio files are copies made in temporary folders by the pinned ffmpeg of the repository.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from mtee.plugins.remote.client import RemoteClient  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.manifest import MANIFEST  # pyright: ignore[reportMissingImports]
from tests.plugins.remote.conftest import PLUGIN_DIR, ROOT, RemoteServer

from mtee.domain.recycling import RecycleOutcome
from mtee.persistence.database import Database, discover_migrations
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.source_track_repository import SourceTrackRepository
from mtee.plugins.api import JobContext, LibraryRoot, LibraryTrack, PluginContext
from mtee.plugins.context import PluginHost
from mtee.services.jobs import JobService

PINNED_FFMPEG = ROOT / "vendor" / "ffmpeg" / "bin" / "ffmpeg.exe"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PUBLISH_TIMEOUT_S = 120.0


def pinned_ffmpeg() -> Path:
    """The pinned ffmpeg of the repository; the tests that need it are skipped without it."""
    if not PINNED_FFMPEG.is_file():
        pytest.skip("The pinned ffmpeg is missing from vendor/ffmpeg.")
    return PINNED_FFMPEG


def make_sine(path: Path, frequency: int = 440, seconds: float = 1.0) -> Path:
    """Write a FLAC sine wave at ``path`` (a new file) and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(pinned_ffmpeg()),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration={seconds}",
            "-c:a",
            "flac",
            "-f",
            "flac",
            str(path),
        ],
        check=True,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    return path


def copy_of(source: Path, destination: Path) -> Path:
    """Copy ``source`` to a new ``destination`` and return it; the source is never written."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def track(track_id: str, path: Path, *, readable: bool = True) -> LibraryTrack:
    """A library track as the core lists it, for the fake library."""
    return LibraryTrack(
        track_id=track_id,
        path=path,
        title=path.stem,
        artists=("Tester",),
        album="Tests",
        duration_us=1_000_000,
        readable=readable,
    )


class FakeLibrary:
    """The local library of a test: its watched folders and the tracks in them."""

    def __init__(self, roots: Sequence[Path], tracks: Sequence[LibraryTrack]) -> None:
        self._roots = [Path(root) for root in roots]
        self._tracks = list(tracks)

    def add(self, item: LibraryTrack) -> None:
        """Add a track, as a scan of the folder would (the test wrote the file itself)."""
        self._tracks.append(item)

    def set_path(self, track_id: str, path: Path) -> None:
        """Point a track at another path: the test renamed the file on disk first."""
        self._tracks = [
            dataclasses.replace(item, path=path) if item.track_id == track_id else item
            for item in self._tracks
        ]

    def remove(self, track_id: str) -> None:
        """Drop a track, as the core does when its file went to the Recycle Bin."""
        self._tracks = [item for item in self._tracks if item.track_id != track_id]

    def track_ids(self) -> list[str]:
        return [item.track_id for item in self._tracks]

    def tracks(self, track_ids: Sequence[str]) -> list[LibraryTrack]:
        by_id = {item.track_id: item for item in self._tracks}
        return [by_id[track_id] for track_id in track_ids if track_id in by_id]

    def roots(self) -> list[LibraryRoot]:
        return [
            LibraryRoot(root_id=f"local-{index}", path=root)
            for index, root in enumerate(self._roots)
        ]

    def root_path(self, root_id: str) -> Path:
        """The folder of a watched folder, by the identifier ``roots`` gave it."""
        return self._roots[int(root_id.removeprefix("local-"))]

    def add_watched_folder(self, path: Path) -> str:
        raise NotImplementedError("The fake library has no folder to add.")

    def rescan(self, path: Path) -> bool:
        return False


class FakeFiles:
    """The file operations of a test, done on the real files of the temporary folders.

    ``read_lease`` yields the track's real path, as the core's lease does. ``import_file``,
    ``replace_content`` and ``move_track`` do what the core does on disk, but without the library
    scan: the file a replacement takes out goes to ``recycle`` (the fake Recycle Bin). Every call is
    recorded in ``calls`` as a tuple, the operation first.

    ``attach_file`` moves the file into the folder and adds the track to the fake library under the
    same identifier, and deletes its source row as the core does (``sources``, a
    ``FakeTrackSources``: the row is deleted, not marked unavailable). ``recycle``
    only records the request, as the core's confirmation would; ``recycle_now`` is the job-side
    ``DeleteRequest.recycle``: it moves the files to the fake Recycle Bin and drops the tracks.
    """

    def __init__(
        self, library: FakeLibrary, recycle: Path, sources: FakeTrackSources | None = None
    ) -> None:
        self._library = library
        self._sources = sources
        self.recycle_folder = recycle
        self.calls: list[tuple[Any, ...]] = []

    def recycle(self, track_ids: Sequence[str]) -> None:
        """The request that opens the core confirmation: recorded, nothing moves."""
        self.calls.append(("recycle", list(track_ids)))

    def recycle_now(self, track_ids: Sequence[str]) -> RecycleOutcome:
        """The job-side recycle of a confirmed selection: files to the fake Recycle Bin."""
        recycled: list[str] = []
        for track_id in track_ids:
            found = self._library.tracks([track_id])
            if not found:
                continue
            path = found[0].path
            self.recycle_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(_free_name(self.recycle_folder / path.name)))
            self._library.remove(track_id)
            recycled.append(track_id)
        self.calls.append(("recycle_now", list(track_ids)))
        return RecycleOutcome(recycled=tuple(recycled))

    def attach_file(self, track_id: str, source: Path, folder: Path) -> Path:
        if self._sources is not None and not any(
            entry.track_id == track_id and entry.available for entry in self._sources.list()
        ):
            raise ValueError(f"The track {track_id} is not a source track of this plugin.")
        if not any(_is_inside(root.path, folder) for root in self._library.roots()):
            raise ValueError("The folder is outside the library.")
        folder.mkdir(parents=True, exist_ok=True)
        target = _free_name(folder / source.name)
        shutil.move(str(source), str(target))
        self._library.add(track(track_id, target))
        if self._sources is not None:
            self._sources.release(track_id)
        self.calls.append(("attach", track_id, folder))
        return target

    @contextmanager
    def read_lease(self, track_id: str) -> Iterator[Path]:
        found = self._library.tracks([track_id])
        if not found:
            raise LookupError(track_id)
        path = found[0].path
        if not path.is_file():
            raise FileNotFoundError(str(path))
        yield path

    def import_file(self, source: Path, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        target = _free_name(folder / source.name)
        shutil.move(str(source), str(target))
        self.calls.append(("import", target))
        return target

    def replace_content(self, track_id: str, source: Path) -> Path:
        path = self._path_of(track_id)
        self.recycle_folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(_free_name(self.recycle_folder / path.name)))
        shutil.move(str(source), str(path))
        self.calls.append(("replace", track_id))
        return path

    def move_track(self, track_id: str, root_id: str, relative_folder: str) -> None:
        path = self._path_of(track_id)
        folder = self._library.root_path(root_id) / relative_folder
        folder.mkdir(parents=True, exist_ok=True)
        target = _free_name(folder / path.name)
        shutil.move(str(path), str(target))
        self._library.set_path(track_id, target)
        self.calls.append(("move", track_id, root_id, relative_folder))

    def _path_of(self, track_id: str) -> Path:
        found = self._library.tracks([track_id])
        if not found:
            raise LookupError(track_id)
        return found[0].path


class FakeTrackSources:
    """The track sources of a test: the real store, with ``adopt`` recorded instead of stored.

    ``adopt`` follows the core's rules that a test can see (the track has no file any more, the key
    is free) and records the call in ``adopted``. The core stores the source row; a test that
    needs it reads the file system or the link table instead.

    ``release`` is the core's attachment step: it deletes the source row of the track, as
    ``SourceTrackRepository.release_in_transaction`` does (``remove`` only marks it unavailable).
    """

    def __init__(self, real: Any, library: FakeLibrary, database: Database) -> None:
        self._real = real
        self._library = library
        self._database = database
        self.adopted: list[tuple[str, Any]] = []

    def upsert(self, tracks: Sequence[Any]) -> dict[str, str]:
        return cast(dict[str, str], self._real.upsert(tracks))

    def remove(self, source_keys: Sequence[str]) -> int:
        return int(self._real.remove(source_keys))

    def release(self, track_id: str) -> None:
        with self._database.transaction() as connection:
            SourceTrackRepository.release_in_transaction(connection, track_id)

    def list(self, *, available_only: bool = False) -> list[Any]:
        return list(self._real.list(available_only=available_only))

    def adopt(self, track_id: str, entry: Any) -> str:
        if self._library.tracks([track_id]):
            raise ValueError(f"The track {track_id} still has a file on this computer.")
        taken = [item for item in self.list() if item.source_key == entry.source_key]
        if any(item.track_id != track_id for item in taken):
            raise ValueError(f"The key {entry.source_key} already belongs to another track.")
        self.adopted.append((track_id, entry))
        return track_id


def _is_inside(root: Path, folder: Path) -> bool:
    """True when ``folder`` is ``root`` or a folder under it."""
    base = os.path.normcase(os.path.abspath(root))
    target = os.path.normcase(os.path.abspath(folder))
    return target == base or target.startswith(base + os.sep)


def _free_name(path: Path) -> Path:
    """``path``, or the first ``name (n).ext`` of its folder that is not taken."""
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


class FakeJob:
    """Stands in for the job of a task: records the progress, and cancels when asked."""

    def __init__(self) -> None:
        self.progress: list[float] = []
        self.cancelled = False

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise RuntimeError("cancelled")

    def report_progress(self, value: float) -> None:
        self.progress.append(value)


def fake_job() -> JobContext:
    return cast(JobContext, FakeJob())


def make_context(tmp_path: Path, library: FakeLibrary) -> PluginContext:
    """A real plugin context over a temporary database, with the fake library and files."""
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    database.migrate_plugin("remote", discover_migrations(PLUGIN_DIR / "remote" / "migrations"))
    host = PluginHost(
        data_dir=tmp_path,
        database=database,
        settings=SettingsRepository(database),
        library=MagicMock(),
        playlists=MagicMock(),
        jobs=JobService(),
        file_moves=MagicMock(),
        recycle=MagicMock(),
        roots=MagicMock(),
        refresh_playlists=lambda: None,
        source_tracks=SourceTrackRepository(database),
    )
    context = host.context_for(MANIFEST)
    sources = FakeTrackSources(context.track_sources, library, database)
    return dataclasses.replace(
        context,
        library=cast(Any, library),
        files=cast(Any, FakeFiles(library, tmp_path / "recycle", sources)),
        track_sources=cast(Any, sources),
        base_dir=tmp_path / "plugin-data" / "remote",
    )


def publish(
    server: RemoteServer,
    username: str,
    password: str,
    files: Mapping[str, Path],
    *,
    root_name: str = "Music",
) -> tuple[RemoteClient, str]:
    """Create a root for ``username``, copy ``files`` into it, scan, and wait for the hashes.

    ``files`` maps a path inside the root (POSIX) to a source file. Returns the signed-in client
    of that user and the root's identifier. The server computes the audio hashes itself.
    """
    _, token = RemoteClient(server.url).login(username, password, "Test: publish")
    client = RemoteClient(server.url, token)
    _, _, body = client.request("POST", "/api/v1/roots", json={"name": root_name})
    root_id = str(json.loads(body)["root_id"])
    root_dir = server.music_dir / username / root_name
    for relative, source in files.items():
        copy_of(source, root_dir / relative)
    client.request("POST", f"/api/v1/roots/{root_id}/scan")
    deadline = time.monotonic() + PUBLISH_TIMEOUT_S
    while True:
        items = client.all_items(root_id=root_id)
        if len(items) == len(files) and all(
            item.get("hash_state") in ("done", "error") for item in items
        ):
            return client, root_id
        if time.monotonic() > deadline:
            pytest.fail("The server did not hash the copied files in time.")
        time.sleep(0.2)


def new_root(client: RemoteClient, name: str = "Music") -> str:
    """Create an empty root for the signed-in user of ``client``; return its identifier."""
    _, _, body = client.request("POST", "/api/v1/roots", json={"name": name})
    return str(json.loads(body)["root_id"])


def upload_file(
    client: RemoteClient,
    root_id: str,
    relative: str,
    source: Path,
    *,
    base_item_id: str | None = None,
    base_revision: int | None = None,
    chunk_bytes: int = 1024 * 1024,
) -> dict[str, Any]:
    """Send ``source`` to the server at ``relative`` with the plugin's client; return the item.

    With a base item the upload replaces that item's file, as a second device would do.
    """
    data = source.read_bytes()
    opened = client.open_upload(
        root_id=root_id,
        relative_path=relative,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        base_item_id=base_item_id,
        base_revision=base_revision,
    )
    upload_id = str(opened["upload_id"])
    offset = 0
    while offset < len(data):
        offset = client.upload_chunk(
            upload_id, offset, data[offset : offset + chunk_bytes], len(data)
        )
    return dict(client.commit_upload(upload_id)["item"])


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digests(folder: Path) -> dict[str, str]:
    """The SHA-256 of every file under ``folder``, by its relative POSIX path."""
    return {
        path.relative_to(folder).as_posix(): sha256_of(path)
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


@contextlib.contextmanager
def signed_in(server: RemoteServer, username: str, password: str) -> Iterator[RemoteClient]:
    """A client signed in as ``username``; the device is signed out at the end."""
    _, token = RemoteClient(server.url).login(username, password, "Test: client")
    client = RemoteClient(server.url, token)
    try:
        yield client
    finally:
        with contextlib.suppress(Exception):
            client.logout()

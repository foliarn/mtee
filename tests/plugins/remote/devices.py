"""Two devices of one account, for the fetch tests (plan 126.4).

Device A is the computer under test: a context with a fake library over copies in a temporary
folder, a real database, and a real first-match-free push. Device B is a second device of the same
account (a second ``RemoteClient``) that changes the items on the server. The fixtures that use
them live in the test modules, which import the helpers below.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mtee.plugins.remote.client import RemoteClient  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.fetch import (  # pyright: ignore[reportMissingImports]
    FetchResult,
    fetch_once,
)
from mtee.plugins.remote.push import (  # pyright: ignore[reportMissingImports]
    detect_changes,
    pending_count,
    run_queue,
)
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.helpers import (
    FakeLibrary,
    copy_of,
    fake_job,
    make_context,
    make_sine,
    new_root,
    signed_in,
    track,
)

from mtee.plugins.api import PluginContext

MakeUser = Callable[[], tuple[str, str]]
NO_ITEM = "0" * 32


def source_files(folder: Path) -> dict[str, Path]:
    """Source audio for a test module, made once in ``folder``; a test only copies them."""
    return {
        "short": make_sine(folder / "short.flac", 440, seconds=2),
        "long": make_sine(folder / "long.flac", 660, seconds=8),
        "other": make_sine(folder / "other.flac", 880, seconds=2),
    }


@dataclasses.dataclass
class Computer:
    """Device A, the computer under test, with the second device B of the same account."""

    context: PluginContext
    store: RemoteStore
    library: FakeLibrary
    local: Path
    client: RemoteClient
    peer: RemoteClient
    root_id: str

    def add_file(self, name: str, source: Path) -> str:
        """Copy ``source`` into the watched folder, written long ago; return its track id."""
        path = copy_of(source, self.local / name)
        written = time.time() - 10
        os.utime(path, (written, written))
        track_id = f"track-{name}"
        self.library.add(track(track_id, path))
        return track_id

    def path_of(self, track_id: str) -> Path:
        return self.library.tracks([track_id])[0].path

    def push(self) -> None:
        """One push pass on this device, without the idle delay: what it changed is sent."""
        detect_changes(self.context, self.store, idle_delay_s=0, now=time.time(), job=fake_job())
        run_queue(self.context, self.store, self.client, fake_job())
        assert pending_count(self.store) == 0

    def detect(self, now: float = 1e12) -> None:
        """A detection pass only: it hashes and queues what changed, and sends nothing."""
        detect_changes(self.context, self.store, idle_delay_s=0, now=now, job=fake_job())

    def fetch(self) -> FetchResult:
        return fetch_once(self.context, self.store, self.client, fake_job())

    def link(self, track_id: str) -> dict[str, Any]:
        row = (
            self.store.connection()
            .execute("SELECT * FROM remote_links WHERE track_id = ?", (track_id,))
            .fetchone()
        )
        assert row is not None, f"{track_id} is not linked"
        return dict(row)

    def link_of_item(self, item_id: str) -> dict[str, Any] | None:
        row = (
            self.store.connection()
            .execute("SELECT * FROM remote_links WHERE item_id = ?", (item_id,))
            .fetchone()
        )
        return None if row is None else dict(row)

    def conflicts(self) -> list[dict[str, Any]]:
        rows = self.store.connection().execute("SELECT * FROM remote_conflicts").fetchall()
        found: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            entry["kind"] = json.loads(entry["local_json"]).get("kind")
            found.append(entry)
        return found

    def item_at(self, relative: str) -> dict[str, Any]:
        for item in self.client.all_items(root_id=self.root_id):
            if item["relative_path"] == relative:
                return item
        raise AssertionError(f"No item at {relative} on the server.")

    def calls(self) -> list[tuple[Any, ...]]:
        """The file operations this device asked for, in order (see ``helpers.FakeFiles``)."""
        return list(cast(Any, self.context.files).calls)

    def available_sources(self) -> set[str]:
        return {entry.source_key for entry in self.context.track_sources.list(available_only=True)}


def wait_hashed(client: RemoteClient, root_id: str) -> None:
    """Wait until the server has hashed its items (it holds each file while it does)."""
    deadline = time.monotonic() + 60
    while True:
        items = client.all_items(root_id=root_id)
        if all(item.get("hash_state") in ("done", "error") for item in items):
            return
        if time.monotonic() > deadline:
            pytest.fail("The server did not hash the items in time.")
        time.sleep(0.2)


@contextlib.contextmanager
def open_computer(tmp_path: Path, server: RemoteServer, make_user: MakeUser) -> Iterator[Computer]:
    """Device A with a mapped watched folder on a new root, and device B, both signed in."""
    username, password = make_user()
    with (
        signed_in(server, username, password) as client,
        signed_in(server, username, password) as peer,
    ):
        root_id = new_root(client)
        local = tmp_path / "Music"
        local.mkdir()
        library = FakeLibrary([local], [])
        # The tests run on one thread: a call to the graphical thread happens at once here.
        context = dataclasses.replace(
            make_context(tmp_path, library), run_on_gui=lambda call: call()
        )
        store = RemoteStore(context)
        store.save_mapping(FolderMapping(str(local), root_id, ""))
        yield Computer(context, store, library, local, client, peer, root_id)

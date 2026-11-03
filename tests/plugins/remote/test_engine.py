"""The sync engine against the real server (plan 126.3): modes, triggers and the status item.

The connection is a stand-in that holds the state and the client of a signed-in device. The
passes run in real jobs and are waited for with ``qtbot``; the 60-second timer is not waited for.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from mtee.plugins.remote.client import RemoteClient  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.engine import (  # pyright: ignore[reportMissingImports]
    MANUAL,
    SyncEngine,
    set_idle_delay,
    set_sync_mode,
)
from mtee.plugins.remote.first_match import DONE_SETTING  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.store import (  # pyright: ignore[reportMissingImports]
    FolderMapping,
    RemoteStore,
)
from pytestqt.qtbot import QtBot
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.helpers import (
    FakeLibrary,
    copy_of,
    make_context,
    make_sine,
    new_root,
    signed_in,
    track,
)

from mtee.plugins.api import PluginContext, Tone

WAIT_MS = 60_000


class StatusRecorder:
    """Stands in for the status item: keeps the texts the engine shows."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def update(
        self,
        text: str,
        tone: Tone = "neutral",
        progress: float | None = None,
        tooltip: str = "",
        icon: str | None = None,
    ) -> None:
        self.texts.append(text)

    def clear(self) -> None:
        self.texts.append("")


class FakeLink:
    """The connection as the engine sees it: connected, with the client of a signed-in device."""

    def __init__(self, client: RemoteClient) -> None:
        self.state = "connected"
        self._client = client
        self.refreshed = 0

    def client(self) -> RemoteClient | None:
        return self._client

    def refresh_status(self) -> None:
        self.refreshed += 1


@dataclasses.dataclass
class Device:
    """One computer of the test: its context, its folder, the engine and what it shows."""

    context: PluginContext
    library: FakeLibrary
    store: RemoteStore
    local: Path
    client: RemoteClient
    root_id: str
    engine: SyncEngine
    link: FakeLink
    status: StatusRecorder
    notices: list[str]
    sources: dict[str, Path]
    added: int = 0

    def add_file(self) -> None:
        """Copy a source into the folder as a newly written file, and add it to the library."""
        self.added += 1
        path = copy_of(self.sources["short"], self.local / f"track-{self.added}.flac")
        self.library.add(track(f"t{self.added}", path))

    def items(self) -> list[dict[str, Any]]:
        return self.client.all_items(root_id=self.root_id)


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("engine-sources")
    return {"short": make_sine(folder / "short.flac", 440, seconds=2)}


@pytest.fixture
def device(
    qtbot: QtBot,
    tmp_path: Path,
    remote_server: RemoteServer,
    make_user: Callable[[], tuple[str, str]],
    sources: dict[str, Path],
) -> Iterator[Device]:
    username, password = make_user()
    with signed_in(remote_server, username, password) as client:
        root_id = new_root(client)
        local = tmp_path / "Music"
        local.mkdir()
        library = FakeLibrary([local], [])
        status = StatusRecorder()
        notices: list[str] = []
        context = dataclasses.replace(
            make_context(tmp_path, library), status_item=status, notify=notices.append
        )
        store = RemoteStore(context)
        store.save_mapping(FolderMapping(str(local), root_id, ""))
        context.settings.set(DONE_SETTING, "true")
        set_idle_delay(context, 0)
        link = FakeLink(client)
        engine = SyncEngine(context, link)
        yield Device(
            context, library, store, local, client, root_id, engine, link, status, notices, sources
        )
        engine.shutdown()


def wait_idle(qtbot: QtBot, engine: SyncEngine) -> None:
    qtbot.waitUntil(lambda: not engine.busy, timeout=WAIT_MS)


def test_auto_mode_sends_a_new_file_on_a_pass(qtbot: QtBot, device: Device) -> None:
    device.add_file()

    device.engine.request_pass()
    wait_idle(qtbot, device.engine)

    assert len(device.items()) == 1
    assert device.engine.pending == 0
    assert "Syncing 1 of 1" in device.status.texts
    assert device.link.refreshed >= 1, "the status item shows Connected again after the pass"


def test_manual_mode_queues_until_apply(qtbot: QtBot, device: Device) -> None:
    set_sync_mode(device.context, MANUAL)
    device.add_file()

    device.engine.request_pass()
    wait_idle(qtbot, device.engine)

    assert device.items() == []
    assert device.engine.pending == 1
    assert device.status.texts == [], "nothing is sent, so the status bar shows no progress"

    device.engine.apply_pending()
    wait_idle(qtbot, device.engine)

    assert len(device.items()) == 1
    assert device.engine.pending == 0


def test_a_library_scan_and_a_connection_start_run_a_pass(qtbot: QtBot, device: Device) -> None:
    device.add_file()
    device.engine.on_library_scanned(device.local)
    wait_idle(qtbot, device.engine)
    assert len(device.items()) == 1

    device.add_file()
    device.engine.on_state("connected")
    wait_idle(qtbot, device.engine)
    assert len(device.items()) == 2


def test_no_pass_runs_before_the_first_match(qtbot: QtBot, device: Device) -> None:
    device.context.settings.delete(DONE_SETTING)
    device.add_file()

    device.engine.request_pass()
    device.engine.apply_pending()

    assert not device.engine.busy
    assert device.items() == []
    assert device.notices == ["Finish the first match first, in Settings > Remote."]

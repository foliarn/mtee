"""Helpers of the playback and stream cache tests (plan 127.5 and 127.6).

A ``StaticLink`` stands in for the connection manager: a test chooses the client it gives and the
state it reports (``connected`` or ``offline``). The cover pictures are made with the pinned ffmpeg
on copies, never on the source files of the tests.
"""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from mtee.plugins.remote.cache import (  # pyright: ignore[reportMissingImports]
    ext_of,
    open_cache,
)
from mtee.plugins.remote.client import RemoteClient  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.sources import server_item_row  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.store import RemoteStore  # pyright: ignore[reportMissingImports]
from tests.plugins.remote.helpers import pinned_ffmpeg

from mtee.plugins.api import PluginContext

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class StaticLink:
    """The connection as the track source sees it: a client, and the state the manager reports."""

    def __init__(self, client: RemoteClient | None, state: str = "connected") -> None:
        self._client = client
        self.state = state

    def client(self) -> RemoteClient | None:
        return self._client


def item_facts(store: RemoteStore, item_id: str) -> tuple[str, str]:
    """The SHA-256 the server reports for a server item, and the extension of its file."""
    row = server_item_row(store.connection(), item_id)
    assert row is not None and row["sha256"] is not None, f"{item_id} is not a server item"
    return str(row["sha256"]), ext_of(str(row["relative_path"]))


def wait_for_copy(context: PluginContext, item_id: str, sha256: str, ext: str) -> Path:
    """Wait until the background download has put a verified copy in the stream cache."""
    cache = open_cache(context)
    deadline = time.monotonic() + 30
    while True:
        found = cache.lookup(item_id, sha256, ext)
        if found is not None:
            return found
        if time.monotonic() > deadline:
            pytest.fail("The background download did not keep a copy in 30 seconds.")
        time.sleep(0.2)


def http_get(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    """GET ``url`` with the standard library; return ``(status, lower-case headers, body)``.

    An error answer (4xx, 5xx) is returned, not raised.
    """
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, _lower(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, _lower(error.headers), error.read()


def _lower(headers: Any) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


def make_cover_copy(source: Path, destination: Path, folder: Path) -> Path:
    """A copy of ``source`` with a red square as its front cover; ``source`` is not changed."""
    ffmpeg = str(pinned_ffmpeg())
    picture = folder / "cover.jpg"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x320",
            "-frames:v",
            "1",
            str(picture),
        ],
        check=True,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-i",
            str(picture),
            "-map",
            "0:a",
            "-map",
            "1:v",
            "-c",
            "copy",
            "-disposition:v:0",
            "attached_pic",
            "-f",
            "flac",
            str(destination),
        ],
        check=True,
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    return destination

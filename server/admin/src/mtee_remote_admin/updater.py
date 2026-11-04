"""Download a new source of the server and put it in place of the installed one.

The archive is GitHub's tarball of a branch or tag (`Origin.tarball_url`), or a local file. It is
unpacked next to the installed source with the `data` filter of `tarfile` (no absolute path, no
`..`, no link out of the folder, no device file), its one top folder is dropped, and it must hold
`server/compose.yaml`. Only then does it replace `source/`; the source before it is kept as
`source.previous/`. The settings (`server.env`) and the data folder are never inside the source,
so an update never touches them. Rebuilding and restarting is the caller's step.
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .paths import Layout, Origin

DOWNLOAD_TIMEOUT_S = 120


class UpdateError(Exception):
    """The new source could not be installed; the installed one is unchanged."""


def download(origin: Origin, target: Path, opener: Callable[..., Any] | None = None) -> Path:
    """Download the tarball of `origin` to `target` and return it."""
    open_url = opener or urllib.request.urlopen
    try:
        reply = open_url(origin.tarball_url, timeout=DOWNLOAD_TIMEOUT_S)
        with reply, open(target, "wb") as handle:
            shutil.copyfileobj(reply, handle)
    except OSError as error:
        raise UpdateError(
            f"The source of {origin.repo} ({origin.ref}) could not be downloaded: {error}"
        ) from None
    return target


def install_archive(where: Layout, archive: Path) -> None:
    """Unpack `archive` and put it in place of the installed source (kept as previous)."""
    where.home.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".source-", dir=where.home))
    try:
        try:
            with tarfile.open(archive, "r:*") as bundle:
                bundle.extractall(staging, filter="data")
        except (tarfile.TarError, OSError) as error:
            raise UpdateError(f"The archive could not be unpacked: {error}") from None
        top = [entry for entry in staging.iterdir() if entry.is_dir()]
        root = top[0] if len(top) == 1 and not (staging / "server").is_dir() else staging
        if not (root / "server" / "compose.yaml").is_file():
            raise UpdateError("The archive holds no MTEE Remote server (server/compose.yaml).")
        if where.previous_source.exists():
            shutil.rmtree(where.previous_source)
        if where.source.exists():
            where.source.rename(where.previous_source)
        root.rename(where.source)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def update(where: Layout, origin: Origin, opener: Callable[..., Any] | None = None) -> None:
    """Download the source of `origin` and install it in place of the current one."""
    with tempfile.TemporaryDirectory(prefix="mtee-remote-") as folder:
        archive = download(origin, Path(folder) / "source.tar.gz", opener)
        install_archive(where, archive)

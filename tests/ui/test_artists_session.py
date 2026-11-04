"""Artist tabs are not restored at startup (plan 112).

Kept in its own file: each UI test file runs one runtime at a time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from tests.ui.artists_support import (
    active_tab,
    artist_tabs,
    ready,
    seed,
    start,
    stop,
    text,
    wait_until,
)


def test_artist_tabs_are_not_restored_at_startup(qapp, monkeypatch, tmp_path: Path) -> None:
    data_dir, _tracks = seed(tmp_path)
    runtime = start(qapp, monkeypatch, data_dir)
    workspace, _root = ready(runtime)
    workspace.openArtistPage("chase", "")
    assert active_tab(workspace) == "artist:chase"
    stop(runtime)  # flushes the saved workspace, as the application does on exit

    runtime = start(qapp, monkeypatch, data_dir)
    try:
        workspace, _root = ready(runtime)
        assert artist_tabs(workspace) == []
        assert not active_tab(workspace).startswith("artist:")
    finally:
        stop(runtime)


def test_the_artists_order_comes_back_after_a_restart(qapp, monkeypatch, tmp_path: Path) -> None:
    data_dir, _tracks = seed(tmp_path)
    runtime = start(qapp, monkeypatch, data_dir)
    workspace, _root = ready(runtime)
    cast(Any, workspace).artistList.setSortMode("fewestTracks")
    stop(runtime)  # flushes the saved workspace

    runtime = start(qapp, monkeypatch, data_dir)
    try:
        workspace, root = ready(runtime)
        assert cast(Any, workspace).artistList.sortMode == "fewestTracks"
        workspace.setActivity("artists")
        assert wait_until(lambda: text(root, "cycleButtonLabel") == "Fewest tracks")
    finally:
        stop(runtime)

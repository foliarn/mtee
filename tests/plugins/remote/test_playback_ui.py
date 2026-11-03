"""Settings > Remote: the Playback group in the real window (plans 127.5 and 127.6).

The group shows the quality of a server track on this computer (Original by default), the cache
size in GB and the Clear cache button with the size of the cache. It is drawn with or without a
connection, since the cache is on this computer.
"""

from __future__ import annotations

from pathlib import Path

from tests.helpers.ui_plugin import (
    find_item,
    need_item,
    settle,
    start_app,
    visible_texts,
    window_of,
    workspace_of,
)
from tests.plugins.remote.conftest import PLUGIN_DIR

from mtee.app import _shutdown

REMOTE_PAGE = "plugin:remote.remote"


def test_playback_group_has_the_quality_levels_the_cache_size_and_clear_cache(
    qapp: object, tmp_path: Path
) -> None:
    runtime = start_app(tmp_path / "data", (PLUGIN_DIR,), ("remote",))
    try:
        workspace = workspace_of(runtime)
        window = window_of(runtime)
        workspace.openSettings()
        workspace.setSettingsPage(REMOTE_PAGE)
        settle(runtime)

        texts = visible_texts(window)
        for expected in ("Playback", "Quality on this computer", "Cache size (GB)", "Clear cache"):
            assert expected in texts, expected
        assert find_item(window, "remoteGroupPlayback") is not None
        for level in ("Original", "Lossless", "320 kbps", "128 kbps"):
            assert level in texts, level
        assert need_item(window, "remoteLevelOriginal").property("checked") is True
        assert need_item(window, "remoteLevelLossless").property("checked") is False
        assert need_item(window, "remoteCacheSize").property("value") == 10
        assert find_item(window, "remoteClearCache") is not None
    finally:
        _shutdown(runtime)

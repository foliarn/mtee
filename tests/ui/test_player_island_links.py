"""Bottom player: title and artist links, and the like heart.

In v0.1 the links come from the core artist index. One runtime serves the module, as in the
other UI files: several runtimes in one process leave worker threads that read a closed
database. The tests run in file order.
"""

from __future__ import annotations

import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QPoint, QPointF, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.artists_support import stop as stop_runtime
from tests.ui.test_player_views import _find, _UiPlayerBackend

from mtee.app import _build_runtime
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 24000)


def _seed(base: Path) -> tuple[Path, dict[str, str], dict[str, str]]:
    """Alpha has one credit, Bravo two, Charlie none; returns the data dir and ids.

    The credits are the Artist tag of each file, read by the core artist index. The keys
    of the artists are their normalized names.
    """
    audio = base / "audio"
    audio.mkdir(parents=True)
    data_dir = base / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root_record = library.add_root(audio)
    track_ids: dict[str, str] = {}
    credits = {"Alpha": ("Hedex",), "Bravo": ("Hedex", "Bou"), "Charlie": ()}
    for index, (title, names) in enumerate(credits.items()):
        path = audio / f"{index}.wav"
        _write_wav(path)
        track_id = library.upsert_location(
            root_record["id"],
            path.name,
            path,
            SourceRevision.observe(path),
            MetadataSnapshot(
                title=(title,), artist=names, technical=TechnicalInfo(duration_us=3_000_000)
            ),
            0,
        )
        track_ids[title] = track_id
    database.close()
    artist_keys = {"Hedex": "hedex", "Bou": "bou"}
    return data_dir, {"root": str(root_record["id"]), **track_ids}, artist_keys


def _centre(item: QQuickItem) -> QPoint:
    point = item.mapToScene(item.boundingRect().center())
    return QPoint(round(point.x()), round(point.y()))


def _pump(milliseconds: int) -> None:
    deadline = time.monotonic() + milliseconds / 1000
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=_centre(item))
    _pump(60)


def _visible_texts(item: QQuickItem) -> str:
    """Joined text of the visible Text items under item, in visual order."""
    if not item.isVisible():
        return ""
    text = item.property("text")
    found = text if isinstance(text, str) else ""
    for child in item.childItems():
        found += _visible_texts(child)
    return found


def _active_tab(workspace: WorkspaceModel) -> str:
    typed = cast(Any, workspace)
    return str(typed.groups[typed.activeGroup]["active"])


def _wait_until(predicate: Callable[[], bool], timeout_ms: int = 10_000) -> bool:
    """Pump the event loop until ``predicate`` holds; False when the timeout passes first.

    The sleeps between the event passes let the background jobs run: QTest.qWait keeps the
    interpreter lock, which starves the job threads that the artist index waits for.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    while not predicate():
        if time.monotonic() > deadline:
            return False
        QCoreApplication.processEvents()
        time.sleep(0.01)
    return True


def _play(runtime: Any, root: QQuickWindow, source_id: str, track_id: str) -> WorkspaceModel:
    workspace = cast(WorkspaceModel, runtime.workspace)
    assert runtime.jobs.wait_for_done(10_000)
    # The artist index is built in the background and reaches the window through a signal.
    assert _wait_until(lambda: workspace.artistRevision > 0)
    workspace.openFolder(f"folder:{source_id}/")
    workspace.playTrack(track_id, f"folder:{source_id}/")
    _pump(60)
    assert workspace.playingId == track_id
    assert _find(root, "playerIsland") is not None
    return workspace


@pytest.fixture(scope="module")
def island(qapp, tmp_path_factory):
    data_dir, tracks, artists = _seed(tmp_path_factory.mktemp("island"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
        patch.setattr("mtee.plugins.registry.PLUGIN_UI_ENABLED", False)
        runtime = _build_runtime(qapp, AppOptions(data_dir=data_dir))
        assert runtime is not None
        root = runtime.engine.rootObjects()[0]
        assert isinstance(root, QQuickWindow)
        root.resize(1440, 900)
        yield runtime, root, tracks, artists
        stop_runtime(runtime)


def test_like_heart_toggles_the_liked_state(island) -> None:
    runtime, root, tracks, _artists = island
    workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
    heart = _find(root, "playerIslandLike")
    assert heart is not None and heart.isVisible()
    assert heart.property("icon") == "heart"

    _click(root, heart)
    assert _wait_until(lambda: workspace.isLiked(tracks["Alpha"]), 5000)
    assert _wait_until(lambda: heart.property("icon") == "heart-filled", 5000)

    _click(root, heart)
    assert _wait_until(lambda: not workspace.isLiked(tracks["Alpha"]), 5000)
    assert _wait_until(lambda: heart.property("icon") == "heart", 5000)


def test_title_goes_to_the_folder_the_track_plays_from(island) -> None:
    runtime, root, tracks, artists = island
    workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
    workspace.openArtistPage(artists["Hedex"], "Hedex")
    assert _active_tab(workspace) == f"artist:{artists['Hedex']}"

    title = _find(root, "playerIslandTitle")
    assert title is not None and title.property("enabled")
    _click(root, title)

    folder_tab = f"folder:{tracks['root']}/"
    assert _wait_until(lambda: _active_tab(workspace) == folder_tab, 5000)
    assert workspace.selectedIds == [tracks["Alpha"]]


def test_revealing_a_track_from_an_artist_source_opens_that_artist(island) -> None:
    runtime, root, tracks, artists = island
    workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
    workspace.openFolder(f"folder:{tracks['root']}/")
    assert _active_tab(workspace) != f"artist:{artists['Hedex']}"

    workspace.revealTrack(tracks["Alpha"], f"artist:{artists['Hedex']}")
    assert _active_tab(workspace) == f"artist:{artists['Hedex']}"


def test_one_credited_artist_opens_its_page_from_the_artist_link(island) -> None:
    runtime, root, tracks, artists = island
    workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
    link = _find(root, "playerIslandArtist_0")
    assert link is not None and link.property("text") == "Hedex"
    assert _find(root, "playerIslandArtist_1") is None

    _click(root, link)
    assert _wait_until(lambda: _active_tab(workspace) == f"artist:{artists['Hedex']}", 5000)


def test_several_credited_artists_are_separate_links(island) -> None:
    runtime, root, tracks, _artists = island
    workspace = _play(runtime, root, tracks["root"], tracks["Bravo"])
    credits = workspace.trackArtists(tracks["Bravo"])
    assert len(credits) == 2
    first, second = _find(root, "playerIslandArtist_0"), _find(root, "playerIslandArtist_1")
    assert first is not None and second is not None
    assert _find(root, "playerIslandArtist_2") is None
    assert first.property("text") == credits[0]["name"]
    assert second.property("text") == credits[1]["name"]

    # Names are shown in credit order, comma separated, with no trailing comma.
    row = _find(root, "playerIslandArtists")
    assert row is not None and row.isVisible()
    assert _visible_texts(row) == f"{credits[0]['name']}, {credits[1]['name']}"
    assert root.findChild(QObject, "playerIslandArtistMenu") is None

    _click(root, second)
    target = f"artist:{credits[1]['id']}"
    assert _wait_until(lambda: _active_tab(workspace) == target, 5000)


def test_v01_links_come_from_the_core_index_without_plugins(island) -> None:
    """With the plugins off (v0.1), the artist links read the Artist tags through the core index."""
    runtime, root, tracks, artists = island
    workspace = _play(runtime, root, tracks["root"], tracks["Bravo"])
    assert workspace.artistManager is None
    assert workspace.trackArtists(tracks["Bravo"]) == [
        {"id": artists["Hedex"], "name": "Hedex"},
        {"id": artists["Bou"], "name": "Bou"},
    ]
    row = _find(root, "playerIslandArtists")
    assert row is not None and row.isVisible()
    plain = _find(root, "playerIslandArtistText")
    assert plain is not None and not plain.isVisible()
    _click(root, _find(root, "playerIslandArtist_1"))
    assert _wait_until(lambda: _active_tab(workspace) == f"artist:{artists['Bou']}", 5000)


def test_track_without_credits_has_no_artist_link(island) -> None:
    runtime, root, tracks, _artists = island
    workspace = _play(runtime, root, tracks["root"], tracks["Charlie"])
    plain = _find(root, "playerIslandArtistText")
    assert plain is not None and plain.isVisible()
    assert plain.property("text") == "Unknown artist"
    row = _find(root, "playerIslandArtists")
    assert row is not None and not row.isVisible()
    assert _find(root, "playerIslandArtist_0") is None
    before = _active_tab(workspace)

    _click(root, plain)
    _pump(100)
    assert _active_tab(workspace) == before


def test_heart_stays_clear_of_the_centre_at_a_narrow_width(island) -> None:
    runtime, root, tracks, _artists = island
    root.resize(720, 800)
    try:
        _play(runtime, root, tracks["root"], tracks["Bravo"])
        _pump(60)
        heart = _find(root, "playerIslandLike")
        previous = _find(root, "previousButton")
        assert heart is not None and heart.isVisible()
        assert previous is not None
        heart_right = heart.mapToScene(QPointF(heart.width(), 0)).x()
        transport_left = previous.mapToScene(QPointF(0, 0)).x()
        assert heart_right <= transport_left
    finally:
        root.resize(1440, 900)

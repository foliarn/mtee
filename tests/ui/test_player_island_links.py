"""Bottom player: title and artist links, and the like heart."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QPoint, QPointF, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from tests.ui.test_player_views import _find, _UiPlayerBackend

from mtee.app import _build_runtime, _shutdown
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.artist_repository import ArtistRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artist_identification_service import ArtistIdentificationService


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 24000)


def _seed(base: Path) -> tuple[Path, dict[str, str], dict[str, str]]:
    """Alpha has one credit, Bravo two, Charlie none; returns the data dir and ids."""
    audio = base / "audio"
    audio.mkdir(parents=True)
    data_dir = base / "data"
    database = Database(data_dir / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    identification = ArtistIdentificationService(library, ArtistRepository(database))
    root_record = library.add_root(audio)
    track_ids: dict[str, str] = {}
    credits = {"Alpha": ["Hedex"], "Bravo": ["Hedex", "Bou"], "Charlie": None}
    for index, (title, names) in enumerate(credits.items()):
        path = audio / f"{index}.wav"
        _write_wav(path)
        track_id = library.upsert_location(
            root_record["id"],
            path.name,
            path,
            SourceRevision.observe(path),
            MetadataSnapshot(
                title=(title,), artist=("Example",), technical=TechnicalInfo(duration_us=3_000_000)
            ),
            0,
        )
        if names is not None:
            identification.sync_tags(track_id, names, None)
        track_ids[title] = track_id
    artist_ids = {item["name"]: item["id"] for item in ArtistRepository(database).catalog()}
    database.close()
    return data_dir, {"root": str(root_record["id"]), **track_ids}, artist_ids


def _centre(item: QQuickItem) -> QPoint:
    point = item.mapToScene(item.boundingRect().center())
    return QPoint(round(point.x()), round(point.y()))


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=_centre(item))
    QTest.qWait(60)


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


def _start(qapp: Any, monkeypatch: Any, data_dir: Path) -> Any:
    monkeypatch.setattr("mtee.app.MpvBackend", _UiPlayerBackend)
    runtime = _build_runtime(qapp, AppOptions(data_dir=data_dir))
    assert runtime is not None
    return runtime


def _play(runtime: Any, root: QQuickWindow, source_id: str, track_id: str) -> WorkspaceModel:
    workspace = cast(WorkspaceModel, runtime.workspace)
    assert runtime.jobs.wait_for_done(10_000)
    workspace.openFolder(f"folder:{source_id}/")
    workspace.playTrack(track_id, f"folder:{source_id}/")
    QTest.qWait(60)
    assert workspace.playingId == track_id
    assert _find(root, "playerIsland") is not None
    return workspace


def test_like_heart_toggles_the_liked_state(qapp, qtbot, tmp_path: Path, monkeypatch) -> None:
    data_dir, tracks, _artists = _seed(tmp_path)
    runtime = _start(qapp, monkeypatch, data_dir)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    try:
        workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
        heart = _find(root, "playerIslandLike")
        assert heart is not None and heart.isVisible()
        assert heart.property("icon") == "heart"

        _click(root, heart)
        qtbot.waitUntil(lambda: workspace.isLiked(tracks["Alpha"]), timeout=5000)
        qtbot.waitUntil(lambda: heart.property("icon") == "heart-filled", timeout=5000)

        _click(root, heart)
        qtbot.waitUntil(lambda: not workspace.isLiked(tracks["Alpha"]), timeout=5000)
        qtbot.waitUntil(lambda: heart.property("icon") == "heart", timeout=5000)
    finally:
        _shutdown(runtime)


def test_title_goes_to_the_folder_the_track_plays_from(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    data_dir, tracks, artists = _seed(tmp_path)
    runtime = _start(qapp, monkeypatch, data_dir)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    try:
        workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
        workspace.openArtistPage(artists["Hedex"], "Hedex")
        assert _active_tab(workspace) == f"artist:{artists['Hedex']}"

        title = _find(root, "playerIslandTitle")
        assert title is not None and title.property("enabled")
        _click(root, title)

        folder_tab = f"folder:{tracks['root']}/"
        qtbot.waitUntil(lambda: _active_tab(workspace) == folder_tab, timeout=5000)
        assert workspace.selectedIds == [tracks["Alpha"]]
    finally:
        _shutdown(runtime)


def test_revealing_a_track_from_an_artist_source_opens_that_artist(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    data_dir, tracks, artists = _seed(tmp_path)
    runtime = _start(qapp, monkeypatch, data_dir)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    try:
        workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
        workspace.openFolder(f"folder:{tracks['root']}/")
        assert _active_tab(workspace) != f"artist:{artists['Hedex']}"

        workspace.revealTrack(tracks["Alpha"], f"artist:{artists['Hedex']}")
        assert _active_tab(workspace) == f"artist:{artists['Hedex']}"
    finally:
        _shutdown(runtime)


def test_one_credited_artist_opens_its_page_from_the_artist_link(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    data_dir, tracks, artists = _seed(tmp_path)
    runtime = _start(qapp, monkeypatch, data_dir)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    try:
        workspace = _play(runtime, root, tracks["root"], tracks["Alpha"])
        link = _find(root, "playerIslandArtist_0")
        assert link is not None and link.property("text") == "Hedex"
        assert _find(root, "playerIslandArtist_1") is None

        _click(root, link)
        qtbot.waitUntil(
            lambda: _active_tab(workspace) == f"artist:{artists['Hedex']}", timeout=5000
        )
    finally:
        _shutdown(runtime)


def test_several_credited_artists_are_separate_links(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    data_dir, tracks, _artists = _seed(tmp_path)
    runtime = _start(qapp, monkeypatch, data_dir)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    try:
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
        qtbot.waitUntil(lambda: _active_tab(workspace) == target, timeout=5000)
    finally:
        _shutdown(runtime)


def test_track_without_credits_has_no_artist_link(qapp, qtbot, tmp_path: Path, monkeypatch) -> None:
    data_dir, tracks, _artists = _seed(tmp_path)
    runtime = _start(qapp, monkeypatch, data_dir)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(1440, 900)
    try:
        workspace = _play(runtime, root, tracks["root"], tracks["Charlie"])
        plain = _find(root, "playerIslandArtistText")
        assert plain is not None and plain.isVisible()
        assert plain.property("text") == "Example"
        row = _find(root, "playerIslandArtists")
        assert row is not None and not row.isVisible()
        assert _find(root, "playerIslandArtist_0") is None
        before = _active_tab(workspace)

        _click(root, plain)
        QTest.qWait(100)
        assert _active_tab(workspace) == before
    finally:
        _shutdown(runtime)


def test_heart_stays_clear_of_the_centre_at_a_narrow_width(
    qapp, qtbot, tmp_path: Path, monkeypatch
) -> None:
    data_dir, tracks, _artists = _seed(tmp_path)
    runtime = _start(qapp, monkeypatch, data_dir)
    root = runtime.engine.rootObjects()[0]
    assert isinstance(root, QQuickWindow)
    root.resize(720, 800)
    try:
        _play(runtime, root, tracks["root"], tracks["Bravo"])
        QTest.qWait(60)
        heart = _find(root, "playerIslandLike")
        previous = _find(root, "previousButton")
        assert heart is not None and heart.isVisible()
        assert previous is not None
        heart_right = heart.mapToScene(QPointF(heart.width(), 0)).x()
        transport_left = previous.mapToScene(QPointF(0, 0)).x()
        assert heart_right <= transport_left
    finally:
        _shutdown(runtime)

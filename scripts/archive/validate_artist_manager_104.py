"""Load and exercise the artist manager window on a synthetic library (plan 104).

The script creates a few silent WAV files under ``.local/validation/104/ui``, runs the
real application runtime offscreen, opens every page and dialog of the manager, drives
the analysis and a confirmation, and writes screenshots next to the data. It reports
every QML warning: a component that never loads is a failure. It touches no user file.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mutagen.id3 import TIT2, TPE1
from mutagen.wave import WAVE
from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    Qt,
    QtMsgType,
    qInstallMessageHandler,
)
from PySide6.QtQuick import QQuickWindow

import mtee.app as application_module
from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.app_paths import resolve_app_paths
from mtee.services.metadata_reader import MetadataReader

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / ".local" / "validation" / "104" / "ui"
FILES = (
    ("Skream - Midnight Request Line.wav", None, None),
    ("Skream & Benga - Night.wav", None, None),
    ("Benga - Crunked Up (Skream Remix).wav", None, None),
    ("Pangaea - Router.wav", None, None),
    ("Mala - Changes (Digital Mystikz Flip).wav", None, None),
    ("t1.wav", ["Burial"], "Archangel"),
    ("t2.wav", ["Kode9, Spaceape"], "Sine"),
    ("t3.wav", ["MPH & A+"], "Long title " + "x" * 60),
    ("01 - Unknown.wav", None, None),
    ("track.wav", None, None),
)
warnings: list[str] = []


def message_handler(kind: QtMsgType, _context: object, message: str) -> None:
    if "QFontDatabase" in message or "fonts" in message:
        return  # the offscreen platform ships no font directory: not a defect of the window
    if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        warnings.append(message)
        print(f"[qt] {message}", file=sys.stderr)


def build_library() -> Path:
    if BASE.exists():
        shutil.rmtree(BASE)
    music = BASE / "music"
    music.mkdir(parents=True)
    for name, artists, title in FILES:
        path = music / name
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8_000)
            handle.writeframes(b"\x00\x00" * 1_600)
        if artists or title:
            audio = WAVE(path)
            audio.add_tags()
            if artists:
                audio.tags.add(TPE1(encoding=3, text=artists))
            if title:
                audio.tags.add(TIT2(encoding=3, text=[title]))
            audio.save()
    database = Database(resolve_app_paths(BASE / "data").ensure().database_path)
    database.migrate()
    library = LibraryRepository(database)
    root_id = str(library.add_root(music)["id"])
    generation = library.begin_scan(root_id)
    reader = MetadataReader()
    entries = [
        (p.name, p, SourceRevision.observe(p), reader.read(p)) for p in sorted(music.glob("*.wav"))
    ]
    library.upsert_locations(root_id, entries, generation)
    library.finish_scan(root_id, generation, complete=True)
    database.close()
    return music


def pump(application, seconds: float = 0.5, until=None) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        application.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until is not None else True


def main() -> int:
    qInstallMessageHandler(message_handler)
    music = build_library()
    application = create_application(["validate"])
    runtime = _build_runtime(application, AppOptions(data_dir=BASE / "data"))
    if runtime is None:
        print("The window did not load.", file=sys.stderr)
        return 1
    window = runtime.engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    window.resize(1280, 800)
    workspace = runtime.workspace
    manager = workspace.artistManager
    results: dict[str, str] = {}

    def shot(name: str) -> None:
        pump(application, 0.4)
        path = BASE / f"{name}.png"
        window.grabWindow().save(str(path))
        results[name] = str(path.relative_to(ROOT))

    def find(name: str, start: QObject | None = None) -> QObject:
        """Search the object tree and the visual tree, since a Loader parents differently."""
        queue = [(start or window.contentItem(), 0)]
        while queue:
            node, depth = queue.pop(0)
            if node.objectName() == name:
                return node
            if depth < 40:
                for child in [*node.children(), *getattr(node, "childItems", list)()]:
                    queue.append((child, depth + 1))
        raise AssertionError(f"{name} was not created")

    pump(application, 1.0)
    workspace.setActivity("artists")
    shot("01-sidebar-empty")
    workspace.openArtistView("from_tags.tracks", "From tags · Tracks")
    shot("02-from-tags-before-analysis")

    manager.analyzeCollection()
    done = pump(
        application,
        20,
        lambda: bool(manager.state.get("cohortReady")) and not manager.analyzing,
    )
    print("analysis finished:", done, manager.state)
    pump(application, 1.0)
    shot("03-from-tags-tracks")
    workspace.openArtistView("from_tags.artists", "From tags · Artists")
    shot("04-from-tags-artists")
    workspace.openArtistView("suggested.tracks", "Suggested · Tracks")
    shot("05-suggested-locked")

    # Edit a track of the first step with the dialog, then confirm the step.
    workspace.openArtistView("from_tags.tracks", "From tags · Tracks")
    pump(application, 0.6)
    tracks = manager.listModel("from_tags.tracks")
    first = tracks.index(0, 0)
    track_id = tracks.data(first, 257)
    view = find("artistReviewView")
    dialog = find("artistEditDialog", view)
    QMetaObject.invokeMethod(
        dialog, "show", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", track_id)
    )
    shot("06-edit-dialog")
    QMetaObject.invokeMethod(dialog, "close")
    pump(application, 0.3)
    manager.requestConfirmation("from_tags", "tracks", "")
    confirm = find("artistConfirmDialog", view)
    pump(application, 1.0, lambda: bool(confirm.property("opened")))
    shot("07-confirm-dialog")
    QMetaObject.invokeMethod(confirm, "close")
    pump(application, 0.3)

    captured: dict = {}
    manager.confirmationReady.connect(lambda preview: captured.update(preview))
    manager.requestConfirmation("from_tags", "tracks", "")
    pump(application, 3, lambda: bool(captured))
    pump(application, 0.3)
    QMetaObject.invokeMethod(confirm, "close")
    outcome = manager.confirm(captured["items"], False, "validation lot")
    print("confirm:", outcome)
    pump(
        application,
        20,
        lambda: not manager.applying and bool(manager.state["categories"]["from_tags"]["complete"]),
    )
    pump(application, 1.0)
    print("files after the first lot:", sorted(p.name for p in music.glob("*.wav")))
    shot("08-after-first-confirmation")
    workspace.openArtistView("suggested.tracks", "Suggested · Tracks")
    suggested_tracks = manager.listModel("suggested.tracks")
    pump(application, 0.8)
    print(
        "suggested rows:",
        [
            suggested_tracks.data(suggested_tracks.index(i, 0), 258)
            for i in range(suggested_tracks.rowCount())
        ],
    )
    shot("09-suggested-tracks")
    workspace.openArtistView("suggested.artists", "Suggested · Artists")
    shot("10-suggested-artists")
    suggested = manager.listModel("suggested.artists")
    pump(application, 0.6)
    artist_id = suggested.data(suggested.index(0, 0), 257)
    action = find("artistActionDialog", find("artistReviewView"))
    QMetaObject.invokeMethod(
        action,
        "show",
        Qt.ConnectionType.DirectConnection,
        Q_ARG("QVariant", "merge"),
        Q_ARG("QVariant", artist_id),
        Q_ARG("QVariant", "Skream"),
    )
    shot("11-artist-merge-dialog")
    QMetaObject.invokeMethod(action, "close")
    workspace.openArtistView("needs_input.tracks", "Needs input · Tracks")
    shot("12-needs-input-locked")
    # Delivery B: the catalog and the page of an artist, from the confirmed tracks.
    catalog = manager.listModel("catalog")
    pump(application, 1.0, lambda: catalog.rowCount() > 0)
    names = [catalog.data(catalog.index(i, 0), 258) for i in range(catalog.rowCount())]
    print("catalog:", names)
    workspace.setActivity("artists")
    workspace.openArtistView("catalog", "Artists")
    shot("13-artist-catalog")
    burial = next(
        catalog.data(catalog.index(i, 0), 257)
        for i in range(catalog.rowCount())
        if catalog.data(catalog.index(i, 0), 258) == "Kode9"
    )
    workspace.openArtistPage(burial, "Kode9")
    pump(application, 1.5)
    shot("14-artist-page")
    workspace.setActivity("explorer")
    shot("15-explorer")

    print("music folder:", music)
    for name, path in results.items():
        print(f"{name}: {path}")
    teardown = len(warnings)
    _shutdown(runtime)
    destroy = getattr(application_module, "_destroy_windows", None)
    if destroy is not None:  # absent from older builds of the application module
        destroy(runtime)
    print(f"warnings before teardown: {teardown}")
    return 1 if teardown else 0


if __name__ == "__main__":
    raise SystemExit(main())

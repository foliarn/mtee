"""Load the core Artists view on a synthetic library and capture what it shows (plan 112).

The script writes silent WAV files and their Artist tags under ``.local/validation/112-view``,
runs the real application runtime offscreen with the plugins off (v0.1), and drives the
Artists activity, an artist page, its "…" menu and an artist link of the player island. It
reports the texts it read and writes one screenshot per step next to the data. It reports
every QML warning: a component that never loads is a failure. It touches no user file.

    uv run python scripts/archive/validate_artists_112_view.py
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / ".local" / "validation" / "112-view"
# title, Artist tag values, album, track number
TRACKS = (
    ("Brand New Day", ("Chase & Status",), "Brand New", "2"),
    ("Hold Tight", ("Chase",), "Alpha", "3"),
    ("Low Light", ("Camo & Krooked",), "Alpha", "1"),
    ("Opening", ("Chase",), "Alpha", "1/9"),
    ("Night Drive", ("Chase",), "Night", "1"),
    ("Ceremony", ("Sub Focus", "Wilkinson"), "Singles", "1"),
    ("Hollow", ("Status",), "Singles", "2"),
)
warnings: list[str] = []


def message_handler(kind: QtMsgType, _context: object, message: str) -> None:
    if "QFontDatabase" in message or "fonts" in message:
        return  # the offscreen platform ships no font directory: not a defect of the view
    if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        warnings.append(message)
        print(f"[qt] {message}", file=sys.stderr)


def build_library() -> Path:
    if BASE.exists():
        shutil.rmtree(BASE)
    audio = BASE / "audio"
    audio.mkdir(parents=True)
    database = Database(BASE / "data" / "mtee.sqlite3")
    database.migrate()
    library = LibraryRepository(database)
    root_record = library.add_root(audio)
    for index, (title, artists, album, number) in enumerate(TRACKS):
        path = audio / f"{index:02d} {title}.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8_000)
            handle.writeframes(b"\x00\x00" * 24_000)
        library.upsert_location(
            root_record["id"],
            path.name,
            path,
            SourceRevision.observe(path),
            MetadataSnapshot(
                title=(title,),
                artist=artists,
                album=(album,),
                track_number=(number,),
                technical=TechnicalInfo(duration_us=3_000_000),
            ),
            0,
        )
    database.close()
    return audio


def pump(seconds: float = 0.4, until=None) -> bool:
    """Process events while sleeping, so that the background jobs can run."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until() if until is not None else True


def find(root: QQuickItem, name: str) -> QQuickItem | None:
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name and item.isVisible():
            return item
        pending.extend(item.childItems())
    return None


def text_of(root: QQuickItem, name: str) -> str:
    item = find(root, name)
    value = item.property("text") if item is not None else None
    return value if isinstance(value, str) else "(not visible)"


def click(window: QQuickWindow, item: QQuickItem) -> None:
    point = item.mapToScene(item.boundingRect().center())
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point.toPoint())
    pump(0.3)


def main() -> int:
    qInstallMessageHandler(message_handler)
    build_library()
    application = create_application(["validate-112-view"])
    runtime = _build_runtime(application, AppOptions(data_dir=BASE / "data"))
    if runtime is None:
        print("The window did not load.", file=sys.stderr)
        return 1
    window = runtime.engine.rootObjects()[0]
    assert isinstance(window, QQuickWindow)
    window.resize(1440, 900)
    workspace = runtime.workspace
    assert runtime.jobs.wait_for_done(15_000)
    pump(1.0, until=lambda: workspace.artistRevision > 0)
    results: dict[str, str] = {}

    def shot(name: str) -> None:
        pump(0.4)
        path = BASE / f"{name}.png"
        window.grabWindow().save(str(path))
        results[name] = str(path.relative_to(ROOT))

    workspace.setActivity("artists")
    pump(0.5)
    print("artistCount:", text_of(window.contentItem(), "artistCount"))
    shot("01-artists-list")

    workspace.openArtistPage("chase", "")
    pump(1.0, until=lambda: text_of(window.contentItem(), "artistTitleText") == "Chase")
    print("page title:", text_of(window.contentItem(), "artistTitleText"))
    print("page meta:", text_of(window.contentItem(), "artistTrackCount"))
    cover = find(window.contentItem(), "artistCover")
    print("cover source:", cover.property("source") if cover is not None else "(missing)")
    model = workspace.trackModelForTab("artist:chase", "artist", "chase", "index", True)
    pump(1.0, until=lambda: model.count == 4)
    print("track order:", [row["title"] for row in model.rows])
    shot("02-artist-page")

    more = find(window.contentItem(), "artistMoreButton")
    if more is None:
        print("The more button is missing.", file=sys.stderr)
        return 1
    click(window, more)
    shot("03-artist-menu")

    workspace.playTrack(model.rows[0]["id"], "artist:chase", model.rows)
    pump(0.6)
    island_link = find(window.contentItem(), "playerIslandArtist_0")
    print("island link text:", island_link.property("text") if island_link else "(missing)")
    if island_link is not None:
        click(window, island_link)
        pump(0.8, until=lambda: workspace.groups[workspace.activeGroup]["active"] == "artist:chase")
    print("active tab after the link:", workspace.groups[workspace.activeGroup]["active"])
    shot("04-island-link")

    workspace.artistList.setFilterText("cam")
    pump(0.6, until=lambda: text_of(window.contentItem(), "artistCount") == "1 of 5 artists")
    print("search count:", text_of(window.contentItem(), "artistCount"))
    shot("05-artists-search")

    _shutdown(runtime)
    print("screenshots:")
    for name, path in results.items():
        if name.endswith(".png") or path.endswith(".png"):
            print(" ", path)
    print("QML warnings:", len(warnings))
    for message in warnings:
        print("  ", message)
    return 0 if not warnings else 2


if __name__ == "__main__":
    sys.exit(main())

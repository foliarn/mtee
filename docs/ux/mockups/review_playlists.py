"""Open/capture the playlist QML review using only illustrative in-memory data."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.icon_provider import IconProvider

ROOT = Path(__file__).resolve().parents[3]
SCENES = {
    "playlist": (1440, 900),
    "search": (1440, 900),
    "menu": (1440, 900),
    "columns": (1440, 900),
    "empty": (1280, 720),
    "narrow": (760, 820),
    "artwork": (1440, 900),
    "liked": (1440, 900),
    "create": (1440, 900),
    "export": (1440, 900),
    "import": (1440, 900),
    "locate": (1440, 900),
}


def settle(app: QGuiApplication, duration: float = 0.3) -> None:
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--verify-interactions", action="store_true")
    parser.add_argument("--native", action="store_true", help="Use the native Windows Qt platform")
    parser.add_argument("--scene", choices=SCENES, default="playlist")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/ux/playlists-2026-09-30")
    args = parser.parse_args()
    if (args.capture or args.verify_interactions) and not args.native:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QGuiApplication(sys.argv[:1])
    families = register_fonts()
    if resolve_ui_family(families) == "sans-serif" and os.name == "nt":
        # Qt's offscreen Windows platform does not enumerate installed fonts.
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if font_path.is_file():
                QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont(resolve_ui_family(families)))
    print(f"Font: {app.font().family()}")
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(ROOT / "src/mtee/qml"))
    engine.addImageProvider("icon", IconProvider())
    warnings: list[str] = []

    def record_warnings(items: list) -> None:
        for item in items:
            message = item.toString()
            warnings.append(message)
            print(message, file=sys.stderr)

    engine.warnings.connect(record_warnings)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("PlaylistReview.qml"))))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("The review root is not a Qt Quick window")
    window.setProperty("scene", args.scene)
    window.resize(*SCENES[args.scene])
    settle(app)
    if args.verify_interactions:
        window.setProperty("scene", "playlist")
        window.resize(1440, 900)
        settle(app)

        def click(name: str) -> None:
            item = window.findChild(QQuickItem, name)
            if item is None:
                # Repeater delegates are visually parented but can have a
                # different QObject owner from the application window.
                pending = [window.contentItem()]
                while pending:
                    candidate = pending.pop()
                    if candidate.objectName() == name:
                        item = candidate
                        break
                    pending.extend(candidate.childItems())
            if item is None:
                raise AssertionError(f"Missing control: {name}")
            point = item.mapToScene(item.boundingRect().center())
            QTest.mouseClick(
                window, Qt.MouseButton.LeftButton, pos=QPoint(round(point.x()), round(point.y()))
            )
            settle(app)

        click("playlistSearchButton")
        if not window.property("searchOpen"):
            raise AssertionError("Search did not open")
        for character in "northline":
            QTest.keyClick(window, ord(character.upper()))
        settle(app)
        typed_query = str(window.property("query"))
        if typed_query.casefold() != "northline" or window.property("playableCount") != 1:
            raise AssertionError(f"Search did not filter playable rows: {typed_query!r}")
        click("playlistPlayButton")
        if window.property("playingId") != "a":
            raise AssertionError("Play did not use the visible available track")
        click("playlistSearchButton")
        if window.property("query") != typed_query or window.property("searchOpen"):
            raise AssertionError("Collapsing search lost text or failed")
        click("addTrack_a")
        popup = window.findChild(QObject, "reviewAddMenu")
        if popup is None or not popup.property("opened"):
            raise AssertionError("Playlist menu did not open")
        click("reviewDestination_night")
        if not popup.property("opened"):
            raise AssertionError("Membership click closed the menu")
        if window.property("feedback") != "Removed from playlist":
            raise AssertionError("Membership removal did not apply immediately")
        click("reviewDestination_night")
        if window.property("feedback") != "Added to playlist" or not popup.property("opened"):
            raise AssertionError("Membership addition did not apply immediately")
        QTest.keyClick(window, Qt.Key.Key_Escape)
        settle(app)
        if popup.property("opened"):
            raise AssertionError("Escape did not close the focused playlist menu")
        click("likeTrack_a")
        window.setProperty("scene", "liked")
        settle(app)
        if window.property("playableCount") != 1:
            raise AssertionError("Local likes did not update Liked tracks")
        print(
            "Interactions: reveal/filter/collapse search, play visible tracks, "
            "persistent menu, immediate add/remove, local likes passed"
        )
    if args.capture:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for scene, dimensions in SCENES.items():
            window.resize(*dimensions)
            window.setProperty("scene", scene)
            settle(app)
            capture = window.grabWindow()
            destination = args.output_dir / f"{scene}-{dimensions[0]}x{dimensions[1]}.png"
            if capture.isNull() or not capture.save(str(destination)):
                raise RuntimeError(f"Cannot capture {scene}")
            print(
                destination.relative_to(ROOT) if destination.is_relative_to(ROOT) else destination
            )
    if warnings:
        print(f"Failed: {len(warnings)} QML warning(s)", file=sys.stderr)
        return 2
    if args.capture or args.verify_interactions:
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

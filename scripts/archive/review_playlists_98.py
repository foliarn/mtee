"""Open or capture the plan 98 playlist interaction review with fictional data."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.icon_provider import IconProvider

ROOT = Path(__file__).resolve().parents[2]
SCENES = (
    "creation-menu",
    "creation-resume",
    "creation-opened",
    "title-edit",
    "cover-hover",
    "drag-single",
    "drag-multiple",
    "drop-playlist",
    "insert-list",
    "insert-artwork",
    "playback-states",
    "playback-paused",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=SCENES, default="playback-states")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native", action="store_true", help="Capture with the native Qt platform")
    args = parser.parse_args()
    if args.width < 880 or args.height < 600:
        parser.error("Review size must be at least 880 x 600")
    if args.output and not args.native:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QGuiApplication(sys.argv[:1])
    families = register_fonts()
    if resolve_ui_family(families) == "sans-serif" and os.name == "nt":
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont(resolve_ui_family(families)))
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
    qml = ROOT / "docs/ux/mockups/Playlists98Review.qml"
    engine.load(QUrl.fromLocalFile(str(qml)))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("Review root is not a Qt Quick window")
    window.resize(args.width, args.height)
    window.setProperty("scene", args.scene)
    until = time.monotonic() + 0.35
    while time.monotonic() < until:
        app.processEvents()
        time.sleep(0.01)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grabWindow().save(str(args.output)):
            raise RuntimeError(f"Could not capture {args.output}")
        print(args.output)
        window.close()
        return 2 if warnings else 0
    if warnings:
        return 2
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

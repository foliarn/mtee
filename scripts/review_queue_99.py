"""Open or capture the illustrative queue review without user data."""

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

ROOT = Path(__file__).resolve().parents[1]
SCENES = {
    "panel": (1280, 800),
    "fullscreen": (1440, 900),
    "track-menu": (1280, 800),
    "queue-menu": (1280, 800),
    "drag": (1280, 800),
    "empty": (1280, 800),
}


def settle(app: QGuiApplication) -> None:
    until = time.monotonic() + 0.3
    while time.monotonic() < until:
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--scene", choices=SCENES, default="panel")
    args = parser.parse_args()
    if args.capture and not args.native:
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
    engine.load(QUrl.fromLocalFile(str(ROOT / "docs/ux/mockups/Queue99Review.qml")))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("Queue review did not create a Qt Quick window")
    if args.capture:
        output = ROOT / "docs/ux/queue-99-2026-10-01"
        output.mkdir(parents=True, exist_ok=True)
        for scene, dimensions in SCENES.items():
            window.setProperty("scene", scene)
            window.resize(*dimensions)
            settle(app)
            path = output / f"{scene}-{dimensions[0]}x{dimensions[1]}.png"
            if not window.grabWindow().save(str(path)):
                raise RuntimeError(f"Capture failed: {scene}")
            print(path.relative_to(ROOT))
        window.close()
        return 2 if warnings else 0
    window.setProperty("scene", args.scene)
    window.resize(*SCENES[args.scene])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

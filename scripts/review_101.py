"""Open or capture the illustrative plan 101 reviews without user data.

Two prototypes: the right panel (Info, Queue, History) and the compact
"Add to playlist" menu. Both only use in-memory sample data.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.icon_provider import IconProvider

ROOT = Path(__file__).resolve().parents[1]
PANEL = "RightPanel101Review.qml"
MENU = "PlaylistMenu101Review.qml"
SCENES: dict[str, tuple[str, tuple[int, int]]] = {
    "queue": (PANEL, (1280, 800)),
    "queue-hover": (PANEL, (1280, 800)),
    "queue-drag": (PANEL, (1280, 800)),
    "queue-menu": (PANEL, (1280, 800)),
    "queue-empty": (PANEL, (1280, 800)),
    "history": (PANEL, (1280, 800)),
    "history-menu": (PANEL, (1280, 800)),
    "history-empty": (PANEL, (1280, 800)),
    "history-times": (PANEL, (1280, 800)),
    "menu": (MENU, (1280, 800)),
    "menu-search": (MENU, (1280, 800)),
    "menu-partial": (MENU, (1280, 800)),
    "menu-empty": (MENU, (1280, 800)),
    "menu-compare": (MENU, (1280, 800)),
}


def settle(app: QGuiApplication) -> None:
    until = time.monotonic() + 0.3
    while time.monotonic() < until:
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true", help="write PNG files (offscreen)")
    parser.add_argument("--native", action="store_true", help="capture with the native platform")
    parser.add_argument("--close-after", type=float, default=0.0,
                        help="close the window after N seconds (load check)")
    parser.add_argument("--scene", choices=SCENES, default="queue")
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
    warnings: list[str] = []

    def record_warnings(items: list) -> None:
        for item in items:
            message = item.toString()
            warnings.append(message)
            print(message, file=sys.stderr)

    def load(qml: str) -> tuple[QQmlApplicationEngine, QQuickWindow]:
        engine = QQmlApplicationEngine()
        engine.addImportPath(str(ROOT / "src/mtee/qml"))
        engine.addImageProvider("icon", IconProvider())
        engine.warnings.connect(record_warnings)
        engine.load(QUrl.fromLocalFile(str(ROOT / "docs/ux/mockups" / qml)))
        if not engine.rootObjects():
            raise RuntimeError(f"Review failed to load: {qml}")
        window = engine.rootObjects()[0]
        if not isinstance(window, QQuickWindow):
            raise RuntimeError("Review did not create a Qt Quick window")
        return engine, window

    if args.capture:
        output = ROOT / "docs/ux/review-101-2026-10-01"
        output.mkdir(parents=True, exist_ok=True)
        loaded: dict[str, tuple[QQmlApplicationEngine, QQuickWindow]] = {}
        for scene, (qml, dimensions) in SCENES.items():
            if qml not in loaded:
                loaded[qml] = load(qml)
            window = loaded[qml][1]
            window.setProperty("scene", scene)
            window.resize(*dimensions)
            settle(app)
            path = output / f"{scene}-{dimensions[0]}x{dimensions[1]}.png"
            if not window.grabWindow().save(str(path)):
                raise RuntimeError(f"Capture failed: {scene}")
            print(path.relative_to(ROOT))
        for _engine, window in loaded.values():
            window.close()
        return 2 if warnings else 0

    qml, dimensions = SCENES[args.scene]
    _engine, window = load(qml)
    window.setProperty("scene", args.scene)
    window.resize(*dimensions)
    if args.close_after > 0:
        QTimer.singleShot(int(args.close_after * 1000), app.quit)
    code = app.exec()
    return 2 if warnings else code


if __name__ == "__main__":
    raise SystemExit(main())

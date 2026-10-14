"""Open or capture the plan 103 artist and mapping review mockups."""

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
    "artists", "review", "batch", "narrow", "empty", "loading", "error", "changed",
    "multi", "encoding", "collision",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=SCENES, default="review")
    parser.add_argument("--width", type=int, default=1480)
    parser.add_argument("--height", type=int, default=940)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--capture-dir", type=Path, help="Capture all review scenes as PNG files")
    parser.add_argument("--native", action="store_true", help="Capture with the native Qt platform")
    args = parser.parse_args()
    if args.width < 600 or args.height < 560:
        parser.error("Review size must be at least 600 x 560")
    if (args.output or args.capture_dir) and not args.native:
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
    engine.load(QUrl.fromLocalFile(str(ROOT / "docs/ux/mockups/Mapping103Review.qml")))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("Review root is not a Qt Quick window")

    def capture(scene: str, output: Path) -> None:
        window.resize(1040, 760) if scene == "narrow" else window.resize(args.width, args.height)
        window.setProperty("scene", scene)
        until = time.monotonic() + 0.4
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(0.01)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grabWindow().save(str(output)):
            raise RuntimeError(f"Could not capture {output}")
        print(output)

    if args.capture_dir:
        for scene in SCENES:
            capture(scene, args.capture_dir / f"{scene}.png")
        window.close()
        return 2 if warnings else 0
    if args.output:
        capture(args.scene, args.output)
        window.close()
        return 2 if warnings else 0
    window.resize(args.width, args.height)
    window.setProperty("scene", args.scene)
    if warnings:
        return 2
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

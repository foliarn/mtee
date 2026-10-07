"""Open the isolated QML review for plan 109, or capture its fictional scenes."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from mtee.fonts import register_fonts, resolve_ui_family

ROOT = Path(__file__).resolve().parents[1]
SCENES = (
    "seed",
    "house",
    "jump-up",
    "mixed",
    "manager",
    "meta",
    "tags",
    "filters",
    "retained",
    "saving",
    "error",
    "create",
    "delete",
    "multi",
    "split",
    "narrow",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=SCENES, default="house")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    if args.width < 900 or args.height < 640:
        parser.error("Review size must be at least 900 x 640")
    if (args.output or args.capture_dir) and not args.native:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QGuiApplication(sys.argv[:1])
    app.setFont(QFont(resolve_ui_family(register_fonts())))
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(ROOT / "src/mtee/qml"))
    warnings: list[str] = []

    def record_warnings(items: list) -> None:
        for item in items:
            warnings.append(item.toString())
            print(item.toString(), file=sys.stderr)

    engine.warnings.connect(record_warnings)
    engine.load(QUrl.fromLocalFile(str(ROOT / "src/mtee/qml/prototypes/genres/Review.qml")))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        raise RuntimeError("Review root must be a Qt Quick window")

    def prepare(scene: str) -> None:
        window.resize(
            960 if scene == "narrow" else args.width, 720 if scene == "narrow" else args.height
        )
        window.setProperty("scene", scene)

    def capture(scene: str, output: Path) -> None:
        prepare(scene)
        until = time.monotonic() + 0.3
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(0.01)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grabWindow().save(str(output)):
            raise RuntimeError(f"Could not capture {output}")
        print(output)

    if args.capture_dir or args.output:
        if args.capture_dir:
            for scene in SCENES:
                capture(scene, args.capture_dir / f"{scene}.png")
        else:
            capture(args.scene, args.output)
        window.close()
        return 2 if warnings else 0
    prepare(args.scene)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

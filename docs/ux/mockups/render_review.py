"""Render the native QML review gallery without opening user data."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

ROOT = Path(__file__).resolve().parents[3]
GALLERY = Path(__file__).with_name("ReviewGallery.qml")
SCENES: dict[str, tuple[int, int]] = {
    "header-wide": (1440, 900),
    "header-medium": (1280, 720),
    "header-split": (1100, 760),
    "columns-menu": (1440, 900),
    "columns-many": (1600, 900),
    "columns-reduced": (1440, 900),
    "columns-single": (1280, 720),
    "columns-split": (1100, 760),
    "wave-compare": (1440, 900),
    "wave-positions": (1440, 900),
    "wave-edges": (1280, 900),
    "wave-narrow": (620, 900),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "ux" / "review-ux-ui-2026-09",
        help="Directory where PNG screenshots are written.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication(sys.argv[:1])
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    if font_id >= 0:
        app.setFont(QFont("Segoe UI"))

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(ROOT / "src" / "mtee" / "qml"))
    engine.warnings.connect(
        lambda warnings: [print(item.toString(), file=sys.stderr) for item in warnings]
    )
    engine.load(QUrl.fromLocalFile(str(GALLERY)))
    roots = engine.rootObjects()
    if not roots:
        return 1
    window = roots[0]
    screen = app.primaryScreen()
    if screen is None:
        print("Qt did not provide a screen for the offscreen renderer.", file=sys.stderr)
        return 1

    for scene, (width, height) in SCENES.items():
        window.setProperty("scene", scene)
        window.resize(width, height)
        QCoreApplication.processEvents()
        time.sleep(0.08)
        QCoreApplication.processEvents()
        image = screen.grabWindow(int(window.winId()))
        if image.isNull():
            print(f"Could not capture scene {scene!r}.", file=sys.stderr)
            return 2
        path = args.output_dir / f"{scene}-{width}x{height}.png"
        if not image.save(str(path), "PNG"):
            print(f"Could not write screenshot {path}.", file=sys.stderr)
            return 2
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Launch the isolated QML review of the core Artists view (plan 112).

The window uses synthetic tags only. It reads and writes no database, no setting and no
audio file, so it takes no data directory. Run it from the repository root:

    uv run python scripts/review_artists_112.py --scenario selected
    uv run python scripts/review_artists_112.py --variant inline --size 1100x760
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from mtee.assets import qml_dir
from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.icon_provider import ICON_PROVIDER_ID, IconProvider
from mtee.prototypes.artists_112 import SCENARIOS, ArtistsReviewPrototype


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="default")
    parser.add_argument("--variant", choices=("menu", "inline"), default="menu")
    parser.add_argument("--size", choices=("1440x900", "1100x760"))
    parser.add_argument("--open-menu", action="store_true", help="Open the page's more menu")
    parser.add_argument("--capture", type=Path, help="Save a screenshot of the review window")
    parser.add_argument("--smoke-test", action="store_true")
    options = parser.parse_args()
    application = QGuiApplication(sys.argv[:1])
    application.setFont(QFont(resolve_ui_family(register_fonts()), 10))
    prototype = ArtistsReviewPrototype(options.scenario)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir()))
    engine.addImageProvider(ICON_PROVIDER_ID, IconProvider())
    engine.rootContext().setContextProperty("prototype", prototype)
    source = qml_dir() / "prototypes" / "artists_112" / "ReviewWindow.qml"
    engine.load(QUrl.fromLocalFile(str(source)))
    if not engine.rootObjects():
        return 4
    window = engine.rootObjects()[0]
    window.setProperty("variant", options.variant)
    if options.size:
        width, height = (int(value) for value in options.size.split("x"))
        if isinstance(window, QQuickWindow):
            window.setWidth(width)
            window.setHeight(height)
    if options.open_menu:
        QTimer.singleShot(150, lambda: window.openMenu())
    if options.capture:

        def capture() -> None:
            options.capture.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(window, QQuickWindow):
                window.grabWindow().save(str(options.capture))

        QTimer.singleShot(500, capture)
    if options.smoke_test:
        QTimer.singleShot(650 if options.capture else 100, application.quit)
    result = application.exec()
    for root in engine.rootObjects():
        root.deleteLater()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

"""Launch the isolated QML review of plans 114-115 (Settings, Profile, columns, dialogs).

Sample data only: the window never opens the MTEE database, the settings or any audio
file. Example, from the repository root:

    uv run python scripts/review_settings_profile_114.py --view settings \
        --category privacy --data-dir .local/validation/114/review
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
from mtee.prototypes.settings_profile_114 import SettingsProfilePrototype


def _report_warnings(warnings: list) -> None:
    """Print every QML warning: a component that does not load is a defect of the review."""
    for warning in warnings:
        print(f"[qml] {warning.toString()}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--view", choices=("settings", "profile", "explorer"), default="settings")
    parser.add_argument(
        "--category",
        choices=(
            "general",
            "library",
            "playback",
            "analysis",
            "shortcuts",
            "privacy",
            "about",
        ),
        default="general",
    )
    parser.add_argument("--period", choices=("week", "month", "year", "all"), default="month")
    parser.add_argument(
        "--dialog", choices=("clear-history", "reset-statistics", "restore-confirm"), default=""
    )
    parser.add_argument(
        "--columns", action="store_true", help="Show the Plays and Last played columns"
    )
    parser.add_argument("--column-menu", action="store_true", help="Open the Columns menu")
    parser.add_argument("--size", default="1440x900", help="Window size, WIDTHxHEIGHT")
    parser.add_argument("--capture", type=Path, help="Save a screenshot of the window")
    parser.add_argument("--smoke-test", action="store_true")
    options = parser.parse_args()

    application = QGuiApplication(sys.argv[:1])
    application.setFont(QFont(resolve_ui_family(register_fonts()), 10))
    prototype = SettingsProfilePrototype(options.data_dir.resolve())
    prototype.setView(options.view)
    prototype.setCategory(options.category)
    prototype.setPeriod(options.period)
    if options.columns:
        prototype.setColumn("plays", True)
        prototype.setColumn("lastPlayed", True)
    if options.dialog:
        prototype.openDialog(options.dialog)

    engine = QQmlApplicationEngine()
    engine.warnings.connect(_report_warnings)
    engine.addImportPath(str(qml_dir()))
    engine.addImageProvider(ICON_PROVIDER_ID, IconProvider())
    engine.rootContext().setContextProperty("prototype", prototype)
    source = qml_dir() / "prototypes" / "settings_profile_114" / "ReviewWindow.qml"
    engine.load(QUrl.fromLocalFile(str(source)))
    if not engine.rootObjects():
        return 4
    window = engine.rootObjects()[0]
    if isinstance(window, QQuickWindow):
        width, height = (int(value) for value in options.size.split("x"))
        window.setWidth(width)
        window.setHeight(height)
    if options.column_menu:
        window.setProperty("columnMenuOpen", True)

    if options.capture:

        def capture() -> None:
            options.capture.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(window, QQuickWindow):
                window.grabWindow().save(str(options.capture))

        QTimer.singleShot(700, capture)
    if options.smoke_test:
        QTimer.singleShot(900 if options.capture else 150, application.quit)
    result = application.exec()
    for root in engine.rootObjects():
        root.deleteLater()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

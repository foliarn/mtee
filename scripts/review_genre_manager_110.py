"""Launch the isolated QML review for plan 110."""

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
from mtee.prototypes.genre_manager_110 import GenreReviewPrototype


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("selection", "brush"), default="selection")
    parser.add_argument(
        "--scenario", choices=("house", "playlist", "batch", "new"), default="house"
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--capture", type=Path, help="Save a screenshot of the review window")
    parser.add_argument("--size", choices=("1440x900", "1100x760"))
    parser.add_argument(
        "--section",
        choices=("Plugins", "Classify", "Genres", "Uncertain", "Organize"),
        default="Classify",
    )
    parser.add_argument("--verify-playback", action="store_true")
    parser.add_argument("--show-source-picker", action="store_true")
    parser.add_argument("--show-folder-tag", action="store_true")
    options = parser.parse_args()
    application = QGuiApplication(sys.argv[:1])
    application.setFont(QFont(resolve_ui_family(register_fonts()), 10))
    prototype = GenreReviewPrototype(
        options.data_dir.resolve(),
        options.variant,
        options.scenario,
        silent_audio=options.verify_playback,
    )
    if options.section == "Organize":
        prototype.preparePreview()
    else:
        prototype.setSection(options.section)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir()))
    engine.addImageProvider(ICON_PROVIDER_ID, IconProvider())
    engine.rootContext().setContextProperty("prototype", prototype)
    source = qml_dir() / "prototypes" / "genre_manager_110" / "ReviewWindow.qml"
    engine.load(QUrl.fromLocalFile(str(source)))
    if not engine.rootObjects():
        prototype.close()
        return 4
    if options.size:
        width, height = (int(value) for value in options.size.split("x"))
        window = engine.rootObjects()[0]
        if isinstance(window, QQuickWindow):
            window.setWidth(width)
            window.setHeight(height)

    def open_review_popup(name: str) -> None:
        getattr(engine.rootObjects()[0], name)()

    if options.show_source_picker:
        QTimer.singleShot(100, lambda: open_review_popup("openSourcePicker"))
    if options.show_folder_tag:
        QTimer.singleShot(100, lambda: open_review_popup("openFolderTagPopup"))
    if options.capture:

        def capture() -> None:
            options.capture.parent.mkdir(parents=True, exist_ok=True)
            window = engine.rootObjects()[0]
            if isinstance(window, QQuickWindow):
                window.grabWindow().save(str(options.capture))

        QTimer.singleShot(450, capture)
    if options.smoke_test:
        QTimer.singleShot(
            1800 if options.verify_playback else 650 if options.capture else 100, application.quit
        )
    if options.verify_playback:
        QTimer.singleShot(100, lambda: prototype.playTrack(prototype._tracks[0]["id"]))
    result = application.exec()
    if options.verify_playback:
        print(f"Native playback status: {prototype.playback_status()}; Qt exit code: {result}")
    prototype.close()
    QCoreApplication.processEvents()
    if options.verify_playback:
        print("Native player closed")
    for root in engine.rootObjects():
        root.deleteLater()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

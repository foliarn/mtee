"""Capture one review scenario on the real Qt desktop platform."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtQuick import QQuickWindow

from mtee import app as mtee_app
from mtee.cli import AppOptions


def main() -> int:
    if len(sys.argv) not in {3, 5}:
        print(
            "usage: capture_ux_scenario.py SCENARIO OUTPUT.png [WIDTH HEIGHT]",
            file=sys.stderr,
        )
        return 2

    scenario = sys.argv[1]
    output = Path(sys.argv[2]).resolve()
    width = int(sys.argv[3]) if len(sys.argv) == 5 else 1440
    height = int(sys.argv[4]) if len(sys.argv) == 5 else 900
    output.parent.mkdir(parents=True, exist_ok=True)

    application = mtee_app.create_application(["mtee"])
    runtime = mtee_app._build_runtime(
        application,
        AppOptions(
            data_dir=output.parent / ".local" / scenario,
            demo=True,
            scenario=scenario,
        ),
    )
    if runtime is None:
        return 1

    window = runtime.engine.rootObjects()[0]
    if not isinstance(window, QQuickWindow):
        print("MTEE root is not a QQuickWindow", file=sys.stderr)
        return 1
    window.resize(width, height)

    def capture() -> None:
        QCoreApplication.processEvents()
        image = window.grabWindow()
        if not image.save(str(output)):
            raise RuntimeError(f"Could not save {output}")
        application.quit()

    QTimer.singleShot(180, capture)
    exit_code = application.exec()
    runtime.jobs.shutdown()
    runtime.database.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

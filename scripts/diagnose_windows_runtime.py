"""Run bounded isolated smoke cycles and emit an anonymized runtime report."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import qVersion


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, required=True, help="Isolated diagnostic data root"
    )
    parser.add_argument("--cycles", type=int, default=1, help="Number of child launches (1-50)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-child timeout in seconds")
    parser.add_argument(
        "--executable", type=Path, help="Packaged MTEE.exe; defaults to this Python"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Disable the library, artwork and audio services"
    )
    parser.add_argument(
        "--disable-native-frame",
        action="store_true",
        help="Isolate Qt without the native window filter",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    if not 1 <= options.cycles <= 50:
        _parser().error("--cycles must be between 1 and 50")
    if not 0.1 <= options.timeout <= 120:
        _parser().error("--timeout must be between 0.1 and 120 seconds")
    options.data_dir.mkdir(parents=True, exist_ok=True)
    packaged = options.executable is not None
    report: dict[str, object] = {
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python": "packaged" if packaged else platform.python_version(),
        "pyside": "packaged" if packaged else pyside_version,
        "qt": "packaged" if packaged else qVersion(),
        "cycles_requested": options.cycles,
        "timeout_seconds": options.timeout,
        "results": [],
    }
    results: list[dict[str, object]] = []
    for index in range(options.cycles):
        data_dir = options.data_dir / f"cycle-{index + 1:02d}"
        command = ([str(options.executable)] if packaged else [sys.executable, "-m", "mtee"]) + [
            "--data-dir",
            str(data_dir),
            "--smoke-test",
        ]
        if options.demo:
            command.append("--demo")
        if options.disable_native_frame:
            command.append("--diagnostic-no-native-frame")
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=options.timeout,
                env={**os.environ, "PYTHONFAULTHANDLER": "1"},
            )
        except subprocess.TimeoutExpired:
            results.append({"cycle": index + 1, "result": "timeout"})
        else:
            results.append(
                {"cycle": index + 1, "result": "exited", "exit_code": completed.returncode}
            )
    report["results"] = results
    print(json.dumps(report, indent=2, sort_keys=True))
    return (
        0
        if all(item["result"] == "exited" and item.get("exit_code") == 0 for item in results)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

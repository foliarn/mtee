"""Location of the resources shipped with MTEE.

The paths never depend on the current directory. Inside a PyInstaller build the
resources live in the extraction directory exposed by ``sys._MEIPASS``.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["fonts_dir", "icons_dir", "is_frozen", "main_qml", "qml_dir", "resources_root"]


def is_frozen() -> bool:
    """Return whether MTEE runs from a packaged build."""
    return bool(getattr(sys, "frozen", False))


def resources_root() -> Path:
    """Return the directory holding the ``qml`` and ``resources`` trees."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(str(bundle_dir)) / "mtee"
    return Path(__file__).resolve().parent


def qml_dir() -> Path:
    """Return the directory of the QML files."""
    return resources_root() / "qml"


def main_qml() -> Path:
    """Return the QML file loaded at startup."""
    return qml_dir() / "Main.qml"


def fonts_dir() -> Path:
    """Return the directory of the embedded fonts."""
    return resources_root() / "resources" / "fonts"


def icons_dir() -> Path:
    """Return the directory of the interface icons."""
    return resources_root() / "resources" / "icons"

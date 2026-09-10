"""Registration of the interface font.

Geist Sans is the font chosen by the visual direction. It is loaded from the
embedded resources when its files are present; otherwise the first available
fallback of the platform is used, and the caller may report the substitution.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase

from mtee.assets import fonts_dir

__all__ = ["FALLBACK_FAMILIES", "PREFERRED_FAMILY", "register_fonts", "resolve_ui_family"]

PREFERRED_FAMILY = "Geist Sans"
FALLBACK_FAMILIES = ("Segoe UI Variable Text", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans")
_FONT_SUFFIXES = (".ttf", ".otf")


def register_fonts(directory: Path | None = None) -> list[str]:
    """Register every font file of ``directory`` and return the families added."""
    source = directory or fonts_dir()
    families: list[str] = []
    if not source.is_dir():
        return families
    for path in sorted(source.iterdir()):
        if path.suffix.lower() not in _FONT_SUFFIXES:
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families


def resolve_ui_family(registered: list[str] | None = None) -> str:
    """Return the family to use for the interface.

    The preferred family wins when it was registered or is installed; otherwise
    the first available fallback is returned, and finally the generic sans-serif
    family of the platform.
    """
    available = set(registered or [])
    if PREFERRED_FAMILY in available:
        return PREFERRED_FAMILY
    installed = set(QFontDatabase.families())
    if PREFERRED_FAMILY in installed:
        return PREFERRED_FAMILY
    for family in FALLBACK_FAMILIES:
        if family in installed:
            return family
    return "sans-serif"

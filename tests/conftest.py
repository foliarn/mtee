"""Shared test configuration.

The tests never open a real window: the offscreen platform of Qt is selected
before any Qt import. An interactive check of the window stays a separate,
manual step of the recipe.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QStandardPaths


@pytest.fixture(autouse=True)
def isolated_standard_paths() -> None:
    """Keep Qt standard locations inside the temporary area of the test run."""
    QStandardPaths.setTestModeEnabled(True)

"""Shared test configuration.

The tests never open a real window: the offscreen platform of Qt is selected
before any Qt import. An interactive check of the window stays a separate,
manual step of the recipe.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QStandardPaths

from mtee.services.main_thread_gc import install_main_thread_gc


@pytest.fixture(scope="session")
def qapp(qapp: QCoreApplication) -> QCoreApplication:
    """The application of pytest-qt, with the cyclic collector of MTEE on its thread.

    Each test leaves models and closures behind; collected on a job worker, a cycle
    holding a Qt object corrupts the event dispatcher of the graphical thread.
    """
    install_main_thread_gc(qapp)
    return qapp


@pytest.fixture(autouse=True)
def isolated_standard_paths() -> None:
    """Keep Qt standard locations inside the temporary area of the test run."""
    QStandardPaths.setTestModeEnabled(True)

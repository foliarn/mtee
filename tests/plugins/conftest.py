"""Plugins are imported as ``mtee.plugins.<id>``; each test leaves the import state as it was."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator

import pytest

import mtee.plugins


@pytest.fixture(autouse=True)
def restore_plugin_state() -> Iterator[None]:
    """Put back the plugin import path and drop the plugin modules a test imported."""
    path_before = list(mtee.plugins.__path__)
    modules_before = set(sys.modules)
    yield
    mtee.plugins.__path__[:] = path_before
    for name in [key for key in sys.modules if key not in modules_before]:
        if name.startswith("mtee.plugins."):
            del sys.modules[name]
            if name.count(".") == 2:
                with contextlib.suppress(AttributeError):
                    delattr(mtee.plugins, name.rpartition(".")[2])

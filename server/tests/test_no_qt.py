"""The server must import without PySide6, even when it is installed."""

from __future__ import annotations

import subprocess
import sys

SCRIPT = """
import importlib
import importlib.abc
import pkgutil
import sys


class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "PySide6" or name.startswith("PySide6.") or name.startswith("shiboken"):
            raise ImportError("Qt import blocked: " + name)
        return None


sys.meta_path.insert(0, BlockQt())

import mtee_remote

for info in pkgutil.walk_packages(mtee_remote.__path__, "mtee_remote."):
    importlib.import_module(info.name)
importlib.import_module("mtee.services.metadata_reader")
importlib.import_module("mtee.domain.metadata")
assert not any(name.startswith("PySide6") for name in sys.modules)
"""


def test_server_imports_without_qt() -> None:
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr

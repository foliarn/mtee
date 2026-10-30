"""Runs a plugin's Python module in a helper process, from the sources and from MTEE.exe.

A plugin starts a helper process with ``PluginContext.python_command`` (see ``mtee.plugins.api``)
when a part of its work must run apart from MTEE. The helper puts the plugin's package and the
shared ``libs/`` copies chosen for the running plugins on its import path, then runs the module
as ``__main__``. It never opens a window and imports no Qt module.

Command line, after ``--plugin-helper`` in the packaged exe or after ``-m mtee.plugin_helper`` in
the sources: ``<plugin_id> <module> [args...]``. The setup is read from the environment variable
``MTEE_PLUGIN_HELPER``, a JSON text written by ``encode_setup``.
"""

from __future__ import annotations

import json
import os
import runpy
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import mtee.plugins
from mtee.plugins.libraries import install_finder

__all__ = [
    "HELPER_ENVIRONMENT_VARIABLE",
    "HELPER_FLAG",
    "HelperSetup",
    "decode_setup",
    "dispatch",
    "encode_setup",
    "main",
]

HELPER_ENVIRONMENT_VARIABLE = "MTEE_PLUGIN_HELPER"
HELPER_FLAG = "--plugin-helper"
_USAGE = "usage: <plugin_id> <module> [args...]"


@dataclass(slots=True)
class HelperSetup:
    """What a helper process needs: the plugin folders to add, and the shared library copies.

    ``libraries`` maps each shared top-level module to its ``libs/`` folder, as
    ``PluginManager.library_locations`` does.
    """

    plugin_folders: tuple[Path, ...] = ()
    libraries: dict[str, Path] = field(default_factory=dict)


def encode_setup(setup: HelperSetup) -> str:
    """Return the JSON text of ``setup`` for the environment variable."""
    return json.dumps(
        {
            "plugin_folders": [str(folder) for folder in setup.plugin_folders],
            "libraries": {name: str(folder) for name, folder in setup.libraries.items()},
        },
        sort_keys=True,
    )


def decode_setup(text: str) -> HelperSetup:
    """Read the JSON text written by ``encode_setup``; raise ``ValueError`` on another shape."""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("the setup is not a JSON object")
    folders = data.get("plugin_folders", [])
    libraries = data.get("libraries", {})
    if not isinstance(folders, list) or not all(isinstance(item, str) for item in folders):
        raise ValueError("plugin_folders is not a list of paths")
    if not isinstance(libraries, dict) or not all(
        isinstance(name, str) and isinstance(folder, str) for name, folder in libraries.items()
    ):
        raise ValueError("libraries is not a mapping of names to paths")
    return HelperSetup(
        tuple(Path(item) for item in folders),
        {name: Path(folder) for name, folder in libraries.items()},
    )


def dispatch(argv: Sequence[str]) -> int | None:
    """Run the helper when ``argv`` asks for it, and return its exit code; otherwise return None.

    The packaged entry point calls this before it imports the Qt application, so a helper
    process never creates a window.
    """
    if len(argv) < 2 or argv[1] != HELPER_FLAG:
        return None
    return main(argv[2:])


def main(argv: Sequence[str]) -> int:
    """Run ``<module>`` with ``args`` in this process and return the exit code.

    ``argv`` is ``<plugin_id> <module> [args...]``. A ``SystemExit`` of the module gives the
    exit code. The error of any other exception is left to Python, as with ``python -m``.
    """
    if len(argv) < 2:
        sys.stderr.write(f"{_USAGE}\n")
        return 2
    plugin_id, module, *args = argv
    raw = os.environ.get(HELPER_ENVIRONMENT_VARIABLE)
    if raw is None:
        sys.stderr.write(f"{plugin_id}: {HELPER_ENVIRONMENT_VARIABLE} is not set\n")
        return 2
    try:
        setup = decode_setup(raw)
    except ValueError as error:
        sys.stderr.write(f"{plugin_id}: {HELPER_ENVIRONMENT_VARIABLE} is invalid: {error}\n")
        return 2
    for folder in setup.plugin_folders:
        _add_to_package_path(folder)
    install_finder(setup.libraries)
    sys.argv = [module, *args]
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as exit_request:
        return _exit_code(exit_request.code)
    return 0


def _add_to_package_path(folder: Path) -> None:
    # The same as mtee.plugins.loader.add_to_package_path, which this module cannot import:
    # the loader imports the plugin interface, which imports Qt.
    entry = str(folder)
    if entry not in mtee.plugins.__path__:
        mtee.plugins.__path__.append(entry)


def _exit_code(code: object) -> int:
    """Turn the argument of ``SystemExit`` into an exit code, as the interpreter does."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    sys.stderr.write(f"{code}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

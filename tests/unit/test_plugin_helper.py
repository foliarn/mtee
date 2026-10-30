"""The plugin helper processes: the commands, the setup they read, and the run of a real module."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import mtee.plugin_helper as plugin_helper
from mtee.plugin_helper import HELPER_ENVIRONMENT_VARIABLE, HelperSetup, decode_setup, encode_setup
from mtee.plugins.api import PluginContext

PLUGIN_ID = "probe"
MODULE = "mtee.plugins.probe.printer"


def _context(setup: HelperSetup) -> PluginContext:
    return PluginContext(
        plugin_id=PLUGIN_ID,
        database=MagicMock(),
        library=MagicMock(),
        playlists=MagicMock(),
        jobs=MagicMock(),
        files=MagicMock(),
        settings=MagicMock(),
        base_dir=Path("unused"),
        notify=MagicMock(),
        log=logging.getLogger("test.helper"),
        helper_setup=lambda: setup,
    )


@pytest.fixture
def not_frozen(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delattr(sys, "frozen", raising=False)
    yield


def test_the_command_from_the_sources_runs_the_helper_module_isolated(not_frozen: None) -> None:
    command = _context(HelperSetup()).python_command(MODULE, "status", "--json")

    assert command == [
        sys.executable,
        "-I",
        "-m",
        "mtee.plugin_helper",
        PLUGIN_ID,
        MODULE,
        "status",
        "--json",
    ]


def test_the_command_in_the_packaged_exe_uses_the_plugin_helper_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\MTEE\MTEE.exe")

    command = _context(HelperSetup()).python_command(MODULE, "dl")

    assert command == [
        r"C:\Program Files\MTEE\MTEE.exe",
        "--plugin-helper",
        PLUGIN_ID,
        MODULE,
        "dl",
    ]


def test_the_environment_carries_the_plugin_folder_and_the_libraries(tmp_path: Path) -> None:
    setup = HelperSetup(
        plugin_folders=(tmp_path / "plugins",),
        libraries={"fakelib": tmp_path / "libs"},
    )

    environment = _context(setup).python_environment()

    assert set(environment) == {HELPER_ENVIRONMENT_VARIABLE}
    data = json.loads(environment[HELPER_ENVIRONMENT_VARIABLE])
    assert data == {
        "plugin_folders": [str(tmp_path / "plugins")],
        "libraries": {"fakelib": str(tmp_path / "libs")},
    }
    assert decode_setup(environment[HELPER_ENVIRONMENT_VARIABLE]) == setup


def test_a_setup_of_another_shape_is_refused() -> None:
    with pytest.raises(ValueError):
        decode_setup("[1, 2]")
    with pytest.raises(ValueError):
        decode_setup(json.dumps({"plugin_folders": "x", "libraries": {}}))
    with pytest.raises(ValueError):
        decode_setup(json.dumps({"plugin_folders": [], "libraries": {"a": 3}}))


def test_the_helper_module_imports_no_qt_module() -> None:
    code = "import sys, mtee.plugin_helper; print('PySide6' in sys.modules)"

    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "False"


@pytest.fixture
def probe_plugin(tmp_path: Path) -> Iterator[Path]:
    """A plugin folder with a module that prints the version of a bundled library."""
    folder = tmp_path / "plugins"
    package = folder / PLUGIN_ID
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "printer.py").write_text(
        "import fakelib\nimport sys\nprint(fakelib.VERSION)\nprint(sys.argv[1:])\n",
        encoding="utf-8",
    )
    libs = tmp_path / "libs" / "fakelib"
    libs.mkdir(parents=True)
    (libs / "__init__.py").write_text('VERSION = "9.9"\n', encoding="utf-8")
    yield tmp_path


def test_the_real_helper_runs_a_plugin_module_with_its_bundled_library(
    probe_plugin: Path,
) -> None:
    setup = HelperSetup(
        plugin_folders=(probe_plugin / "plugins",),
        libraries={"fakelib": probe_plugin / "libs"},
    )
    context = _context(setup)
    environment = {**os.environ, **context.python_environment()}

    result = subprocess.run(
        [*context.python_command(MODULE, "one", "two")],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["9.9", "['one', 'two']"]


def test_the_helper_gives_the_exit_code_of_the_module(probe_plugin: Path) -> None:
    (probe_plugin / "plugins" / PLUGIN_ID / "failing.py").write_text(
        "raise SystemExit(7)\n", encoding="utf-8"
    )
    setup = HelperSetup(plugin_folders=(probe_plugin / "plugins",))
    context = _context(setup)
    environment = {**os.environ, **context.python_environment()}

    result = subprocess.run(
        [*context.python_command(f"mtee.plugins.{PLUGIN_ID}.failing")],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
        check=False,
    )

    assert result.returncode == 7


def test_main_refuses_a_missing_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HELPER_ENVIRONMENT_VARIABLE, raising=False)

    assert plugin_helper.main([PLUGIN_ID, MODULE]) == 2


def test_dispatch_leaves_other_commands_to_the_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(plugin_helper, "main", lambda argv: calls.append(list(argv)) or 5)

    assert plugin_helper.dispatch(["MTEE.exe", "--help"]) is None
    assert plugin_helper.dispatch(["MTEE.exe"]) is None
    assert calls == []

    assert plugin_helper.dispatch(["MTEE.exe", "--plugin-helper", PLUGIN_ID, MODULE, "x"]) == 5
    assert calls == [[PLUGIN_ID, MODULE, "x"]]


def test_the_encoded_setup_round_trips() -> None:
    setup = HelperSetup((Path("a"),), {"lib": Path("b")})

    assert decode_setup(encode_setup(setup)) == setup

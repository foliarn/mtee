"""The restart command of MTEE, from the sources and from the frozen executable (plan 123.6).

No test starts a process: the launcher is a recorder.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mtee.services.restart import restart_command, restart_environment, start_detached


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", ["MTEE.exe", "--data-dir", "C:/data", "--plugin-dir", "x"])


@pytest.fixture
def from_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", ["/usr/bin/mtee", "--data-dir", "C:/data"])


def test_a_frozen_restart_runs_the_executable_with_the_same_arguments(frozen: None) -> None:
    assert restart_command() == [sys.executable, "--data-dir", "C:/data", "--plugin-dir", "x"]


def test_a_restart_from_the_sources_runs_the_module_with_the_same_arguments(
    from_sources: None,
) -> None:
    assert restart_command() == [sys.executable, "-m", "mtee", "--data-dir", "C:/data"]


def test_a_frozen_child_gets_the_reset_flag_and_no_other_change(
    frozen: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("_PYI_TEST_MARKER", "parent")

    environment = restart_environment()

    assert environment["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert environment["_PYI_TEST_MARKER"] == "parent"


def test_a_source_child_is_a_copy_of_the_environment(
    from_sources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PYINSTALLER_RESET_ENVIRONMENT", raising=False)

    environment = restart_environment()

    assert "PYINSTALLER_RESET_ENVIRONMENT" not in environment
    assert environment == dict(os.environ)


def test_start_detached_passes_the_command_and_the_detached_flags(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(arguments: list[str], **options: object) -> None:
        calls.append((arguments, options))

    start_detached(["mtee", "--demo"], {"A": "1"}, runner=runner)

    arguments, options = calls[0]
    assert arguments == ["mtee", "--demo"]
    assert options["env"] == {"A": "1"}
    assert options["close_fds"] is True
    assert options["creationflags"] == getattr(subprocess, "DETACHED_PROCESS", 0)


def test_start_detached_reports_a_process_that_cannot_start() -> None:
    def runner(arguments: list[str], **options: object) -> None:
        raise FileNotFoundError(arguments[0])

    with pytest.raises(FileNotFoundError):
        start_detached(["missing.exe"], {}, runner=runner)

"""The internal wait option of a restarted MTEE, and the wait for a process exit (plan 123.6).

The tests start only short Python subprocesses of their own, and end them in their cleanup.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator

import pytest

from mtee.services.wait_for_exit import strip_wait_option, wait_for_process_exit


@pytest.fixture
def exited_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


@pytest.fixture
def sleeping_process() -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    try:
        yield process
    finally:
        process.terminate()
        process.wait()


def test_an_absent_option_leaves_the_arguments_and_gives_no_pid() -> None:
    assert strip_wait_option(["mtee", "--data-dir", "C:/data"]) == (
        ["mtee", "--data-dir", "C:/data"],
        None,
    )


def test_a_valid_pair_is_removed_and_its_pid_returned() -> None:
    assert strip_wait_option(["mtee", "--wait-for-exit", "1234", "--demo"]) == (
        ["mtee", "--demo"],
        1234,
    )


def test_a_malformed_value_is_ignored_and_removed() -> None:
    assert strip_wait_option(["mtee", "--wait-for-exit", "abc", "--demo"]) == (
        ["mtee", "--demo"],
        None,
    )


@pytest.mark.parametrize("value", ["0", "-5", "1.5", ""])
def test_a_value_that_is_not_a_positive_whole_number_is_removed(value: str) -> None:
    assert strip_wait_option(["mtee", "--wait-for-exit", value]) == (["mtee"], None)


def test_an_option_at_the_end_without_value_is_removed() -> None:
    assert strip_wait_option(["mtee", "--demo", "--wait-for-exit"]) == (["mtee", "--demo"], None)


def test_the_program_name_is_never_searched() -> None:
    assert strip_wait_option(["--wait-for-exit", "5"]) == (["--wait-for-exit", "5"], None)


def test_a_pid_that_does_not_exist_is_reported_as_exited(exited_pid: int) -> None:
    assert wait_for_process_exit(exited_pid) is True


def test_a_process_that_exits_within_the_timeout_is_reported_as_exited() -> None:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.3)"])
    try:
        assert wait_for_process_exit(process.pid) is True
    finally:
        process.wait()


def test_a_process_still_running_after_the_timeout_is_reported_as_not_exited(
    sleeping_process: subprocess.Popen[bytes],
) -> None:
    assert wait_for_process_exit(sleeping_process.pid, timeout_s=0.2) is False

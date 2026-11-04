"""The Compose commands and the JSON answers of `mtee-remote admin`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mtee_remote_admin.compose import Compose, ComposeError
from mtee_remote_admin.paths import Layout


class Recorder:
    """A fake `subprocess.run`: records each command and answers what the test set."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, options.get("input")))
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


@pytest.fixture
def where(tmp_path: Path) -> Layout:
    return Layout(tmp_path / "home", tmp_path / "config")


def test_every_command_names_the_project_the_file_and_the_settings(where: Layout) -> None:
    run = Recorder()
    Compose(where, run).up()
    ((command, _stdin),) = run.calls
    assert command == [
        "docker", "compose", "-p", "mtee-remote",
        "-f", str(where.home / "source" / "server" / "compose.yaml"),
        "--env-file", str(where.config / "server.env"),
        "up", "-d",
    ]  # fmt: skip


def test_an_admin_command_gets_the_password_on_stdin_only(where: Layout) -> None:
    run = Recorder(stdout=json.dumps({"message": "Account ana created."}) + "\n")
    answer = Compose(where, run).admin(
        "user-create", "--username", "ana", "--password-stdin", password="a long secret"
    )
    assert answer == {"message": "Account ana created."}
    ((command, stdin),) = run.calls
    assert command[8:] == [
        "exec", "-T", "server", "mtee-remote", "admin",
        "user-create", "--username", "ana", "--password-stdin",
    ]  # fmt: skip
    assert "a long secret" not in " ".join(command)
    assert stdin == "a long secret\n"


def test_a_refusal_of_the_server_is_its_own_sentence(where: Layout) -> None:
    run = Recorder(stdout=json.dumps({"error": "There is no account named bo."}), returncode=1)
    with pytest.raises(ComposeError, match=r"There is no account named bo\."):
        Compose(where, run).admin("user-set", "--username", "bo", "--admin", "no")


def test_a_stopped_server_says_so(where: Layout) -> None:
    run = Recorder(returncode=1, stderr='service "server" is not running')
    with pytest.raises(ComposeError, match=r"not running\. Start it first"):
        Compose(where, run).admin("users")


def test_the_state_reads_both_json_formats_of_compose(where: Layout) -> None:
    line = json.dumps({"Service": "server", "State": "running"})
    assert Compose(where, Recorder(stdout=line + "\n")).state() == "running"
    listed = json.dumps([{"Service": "server", "State": "exited"}])
    assert Compose(where, Recorder(stdout=listed)).state() == "exited"
    assert Compose(where, Recorder(stdout="")).state() == "absent"


def test_docker_missing_is_a_sentence(where: Layout) -> None:
    def missing(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("docker")

    with pytest.raises(ComposeError, match="Docker is not installed"):
        Compose(where, missing).up()

"""Docker Compose for the installed server, and the `mtee-remote admin` commands inside it.

Every command names the compose file of the source, the settings file and a fixed project name,
so it works from any folder and never mixes with another Compose project:

    docker compose -p mtee-remote -f <source>/server/compose.yaml --env-file <config>/server.env ...

`Compose.admin(...)` runs `exec -T server mtee-remote admin ...` and reads its JSON answer; a
password goes on stdin, never in the command line.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .paths import Layout

PROJECT = "mtee-remote"
SERVICE = "server"
Runner = Callable[..., subprocess.CompletedProcess[str]]


class ComposeError(Exception):
    """A command that failed, with the sentence to show; `stdout` is what it printed."""

    def __init__(self, message: str, stdout: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout


def docker_available() -> str | None:
    """None when `docker compose` can be used; else the sentence that says what is missing."""
    if shutil.which("docker") is None:
        return "Docker is not installed. Install Docker Engine and its Compose plugin first."
    result = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return "The Docker Compose plugin is missing (`docker compose version` failed)."
    return None


class Compose:
    def __init__(self, where: Layout, run: Runner = subprocess.run) -> None:
        self._where = where
        self._run = run

    def command(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "-p",
            PROJECT,
            "-f",
            str(self._where.compose_file),
            "--env-file",
            str(self._where.env_file),
            *args,
        ]

    def call(self, *args: str, stdin: str | None = None, timeout: float = 600) -> str:
        """Run a compose command; its output, or `ComposeError` with Docker's last lines."""
        try:
            result = self._run(
                self.command(*args),
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            raise ComposeError("Docker is not installed on this machine.") from None
        except subprocess.TimeoutExpired:
            raise ComposeError(f"`docker compose {args[0]}` did not finish in time.") from None
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
            raise ComposeError(
                " ".join(tail) or f"`docker compose {args[0]}` failed.", result.stdout or ""
            )
        return result.stdout

    # -- the container ------------------------------------------------------------------
    def build(self) -> str:
        return self.call("build", timeout=1800)

    def up(self) -> str:
        return self.call("up", "-d")

    def stop(self) -> str:
        return self.call("stop")

    def restart(self) -> str:
        # `up -d` recreates the container when the settings changed; `restart` would not.
        return self.call("up", "-d", "--force-recreate")

    def logs(self, lines: int = 200) -> str:
        return self.call("logs", "--no-color", "--tail", str(lines), SERVICE, timeout=60)

    def state(self) -> str:
        """The state of the server container ("running", "exited"...), or "absent"."""
        out = self.call("ps", "--all", "--format", "json", SERVICE, timeout=60).strip()
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            rows.extend(parsed if isinstance(parsed, list) else [parsed])
        for row in rows:
            if row.get("Service") == SERVICE:
                return str(row.get("State", "unknown")).lower()
        return "absent"

    # -- inside the container -----------------------------------------------------------
    def admin(self, *args: str, password: str | None = None) -> dict[str, Any]:
        """Run `mtee-remote admin <args>` in the container and return its JSON answer."""
        stdin = None if password is None else password + "\n"
        try:
            out = self.call("exec", "-T", SERVICE, "mtee-remote", "admin", *args, stdin=stdin)
        except ComposeError as error:
            raise ComposeError(_admin_error(error)) from None
        return _json_answer(out)

    def server_command(self, *args: str) -> str:
        """A text command of `mtee-remote` in the container (adopt-root, scan)."""
        return self.call("exec", "-T", SERVICE, "mtee-remote", *args, timeout=3600).strip()


def _json_answer(out: str) -> dict[str, Any]:
    for line in reversed(out.strip().splitlines()):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            if "error" in parsed:
                raise ComposeError(str(parsed["error"]))
            return parsed
    raise ComposeError("The server answered something unreadable.")


def _admin_error(error: ComposeError) -> str:
    """The sentence of a failed admin command: the server's own, or why it could not run."""
    for line in reversed(error.stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "error" in parsed:
            return str(parsed["error"])
    text = str(error)
    if "is not running" in text or "no container" in text.lower():
        return "The server is not running. Start it first."
    return text


def health(host: str, port: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Whether `GET /health` answers on the host, and the version it reports."""
    address = "127.0.0.1" if host in ("", "localhost") else host
    try:
        with urllib.request.urlopen(f"http://{address}:{port}/health", timeout=timeout) as reply:
            body = json.loads(reply.read().decode("utf-8") or "{}")
    except (urllib.error.URLError, OSError, ValueError):
        return False, ""
    version = body.get("version", "") if isinstance(body, dict) else ""
    return True, str(version)

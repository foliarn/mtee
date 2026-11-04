"""`install.sh` run for real in a temporary home, from a local tarball of this source.

Docker is not needed (`MTEE_REMOTE_SKIP_DOCKER_CHECK`), and the program is installed with the
real `uv tool install` into the temporary home. Skipped when `uv` or `sh` is missing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2]
SCRIPT = SERVER / "install.sh"
SKIPPED = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "data", ".data", ".music"}


def tarball(path: Path, version: str) -> Path:
    """A GitHub-like tarball: one top folder holding `server/` (without virtual environments)."""

    def keep(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        return None if SKIPPED & set(Path(info.name).parts) else info

    with tarfile.open(path, "w:gz") as bundle:
        bundle.add(SERVER, arcname="mtee-remote-main/server", filter=keep)
        marker = path.with_suffix(".version")
        marker.write_text(version)
        bundle.add(marker, arcname="mtee-remote-main/VERSION")
    return path


def run_install(home: Path, archive: Path) -> subprocess.CompletedProcess[str]:
    uv = shutil.which("uv")
    assert uv is not None
    env = {
        "HOME": str(home),
        "PATH": f"{Path(uv).parent}:/usr/bin:/bin",
        "MTEE_REMOTE_TARBALL": str(archive),
        "MTEE_REMOTE_SKIP_DOCKER_CHECK": "1",
        "MTEE_REMOTE_NO_START": "1",
        "MTEE_REMOTE_REPO": "someone/mtee-remote",
        "MTEE_REMOTE_REF": "v0.2.0",
        "UV_TOOL_DIR": str(home / "tools"),
        "UV_TOOL_BIN_DIR": str(home / "bin"),
        # The packages come from the cache of this machine, not from a new download.
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(Path.home() / ".cache" / "uv")),
    }
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "SSL_CERT_FILE", "UV_NATIVE_TLS"):
        if name in os.environ:
            env[name] = os.environ[name]
    return subprocess.run(
        ["sh", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=600, check=False
    )


@pytest.mark.skipif(shutil.which("uv") is None or shutil.which("sh") is None, reason="needs uv")
def test_the_script_installs_the_source_and_the_program_and_keeps_the_previous(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = run_install(home, tarball(tmp_path / "one.tar.gz", "1"))
    assert first.returncode == 0, first.stderr + first.stdout

    share = home / ".local" / "share" / "mtee-remote"
    assert (share / "source" / "server" / "compose.yaml").is_file()
    assert (share / "source" / "VERSION").read_text() == "1"
    origin = json.loads((home / ".config" / "mtee-remote" / "admin.json").read_text())
    assert origin == {"repo": "someone/mtee-remote", "ref": "v0.2.0"}
    program = home / "bin" / "mtee-remote-admin"
    version = subprocess.run(
        [str(program), "--version"], capture_output=True, text=True, check=False
    )
    assert version.returncode == 0 and "mtee-remote-admin" in version.stdout
    status = subprocess.run(
        [str(program), "--status"],
        capture_output=True,
        text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert status.returncode == 1 and "Not set up" in status.stdout

    second = run_install(home, tarball(tmp_path / "two.tar.gz", "2"))
    assert second.returncode == 0, second.stderr
    assert (share / "source" / "VERSION").read_text() == "2"
    assert (share / "source.previous" / "VERSION").read_text() == "1"


def test_a_repository_name_with_odd_characters_is_refused(tmp_path: Path) -> None:
    result = subprocess.run(
        ["sh", str(SCRIPT)],
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "MTEE_REMOTE_REPO": "a/b;rm -rf ~"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "letters, digits" in result.stderr

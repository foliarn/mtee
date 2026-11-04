"""Where an installed MTEE Remote lives on the host, and the installer's choices.

The install script (`install.sh`) and this program agree on one layout:

- `MTEE_REMOTE_HOME` (default `~/.local/share/mtee-remote`):
  - `source/`: the server's source, as downloaded (it holds `server/compose.yaml`); an update
    replaces it, and the one before is kept as `source.previous/`;
  - `data/`: the default `DATA_DIR` (database, backups, uploads).
- `MTEE_REMOTE_CONFIG` (default `~/.config/mtee-remote`):
  - `server.env`: the settings of the server, the `.env` that Docker Compose reads; it is kept
    outside `source/`, so an update never touches it;
  - `admin.json`: where the source comes from (`repo`, `ref`), written by the installer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPO = "foliarn/mtee-remote"
DEFAULT_REF = "main"


@dataclass(frozen=True)
class Layout:
    home: Path
    config: Path

    @property
    def source(self) -> Path:
        return self.home / "source"

    @property
    def previous_source(self) -> Path:
        return self.home / "source.previous"

    @property
    def server_dir(self) -> Path:
        """The folder of `compose.yaml` inside the source."""
        return self.source / "server"

    @property
    def compose_file(self) -> Path:
        return self.server_dir / "compose.yaml"

    @property
    def env_file(self) -> Path:
        return self.config / "server.env"

    @property
    def default_data_dir(self) -> Path:
        return self.home / "data"

    @property
    def origin_file(self) -> Path:
        return self.config / "admin.json"

    @property
    def installed(self) -> bool:
        return self.compose_file.is_file()

    @property
    def configured(self) -> bool:
        return self.env_file.is_file()


@dataclass(frozen=True)
class Origin:
    """The repository and the branch or tag the source is downloaded from."""

    repo: str = DEFAULT_REPO
    ref: str = DEFAULT_REF

    @property
    def tarball_url(self) -> str:
        return f"https://codeload.github.com/{self.repo}/tar.gz/{self.ref}"


def layout(environ: dict[str, str] | None = None) -> Layout:
    env = dict(os.environ) if environ is None else environ
    home = Path(env.get("HOME", str(Path.home())))
    root = env.get("MTEE_REMOTE_HOME") or str(home / ".local" / "share" / "mtee-remote")
    config = env.get("MTEE_REMOTE_CONFIG") or str(home / ".config" / "mtee-remote")
    return Layout(Path(root).expanduser(), Path(config).expanduser())


def read_origin(where: Layout) -> Origin:
    try:
        raw = json.loads(where.origin_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Origin()
    if not isinstance(raw, dict):
        return Origin()
    repo = raw.get("repo")
    ref = raw.get("ref")
    return Origin(
        repo if isinstance(repo, str) and repo else DEFAULT_REPO,
        ref if isinstance(ref, str) and ref else DEFAULT_REF,
    )


def write_origin(where: Layout, origin: Origin) -> None:
    where.config.mkdir(parents=True, exist_ok=True)
    where.origin_file.write_text(
        json.dumps({"repo": origin.repo, "ref": origin.ref}, indent=2) + "\n", encoding="utf-8"
    )

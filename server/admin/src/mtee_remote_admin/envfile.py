"""The settings of the server: the `.env` file Docker Compose reads, and the rule of each field.

`EnvFile` keeps the file as it is (comments, blank lines, keys this program does not know) and
changes only the values it is asked to. `FIELDS` lists what the TUI shows, with the check of each
value; `check` returns a sentence for a value that the server or Compose would refuse, and `None`
when it is fine. `warning` returns a sentence for a value that works but deserves a word (plain
HTTP on the home network).
"""

from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_USERNAME = re.compile(r"^[a-z0-9_.-]{2,32}$")
_NETWORK_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
_HOME_NETWORKS = tuple(
    ipaddress.ip_network(text) for text in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class EnvFile:
    """A `.env` file: its lines in order, with the values read from them."""

    def __init__(self, lines: list[str] | None = None) -> None:
        self._lines = list(lines or [])

    @classmethod
    def read(cls, path: Path) -> EnvFile:
        return cls(path.read_text(encoding="utf-8").splitlines())

    def write(self, path: Path) -> None:
        """Write the file in place of `path`: a new file, then a rename, so it is never half."""
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        part.write_text("\n".join(self._lines) + "\n", encoding="utf-8")
        os.chmod(part, 0o600)
        os.replace(part, path)

    def values(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for line in self._lines:
            match = _LINE.match(line)
            if match is not None and not line.lstrip().startswith("#"):
                found[match.group(1)] = _unquote(match.group(2).strip())
        return found

    def get(self, key: str, default: str = "") -> str:
        return self.values().get(key, default)

    def set(self, key: str, value: str) -> None:
        """Change the value of `key` where it is, or add it at the end."""
        text = f"{key}={_quote(value)}"
        for index, line in enumerate(self._lines):
            match = _LINE.match(line)
            if match is not None and match.group(1) == key and not line.lstrip().startswith("#"):
                self._lines[index] = text
                return
        self._lines.append(text)

    @property
    def lines(self) -> list[str]:
        return list(self._lines)


def _quote(value: str) -> str:
    if value == "" or re.fullmatch(r"[A-Za-z0-9_./:,@+-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        if text[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    # An unquoted value ends at a comment that follows a space.
    return re.split(r"\s+#", text, maxsplit=1)[0].strip()


# -- the fields -------------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    key: str
    label: str
    help: str
    check: Callable[[str], str | None]
    default: Callable[[], str] = lambda: ""
    warning: Callable[[str], str | None] = lambda _value: None
    restart: bool = True  # the server reads it when the container starts


def _username(value: str) -> str | None:
    if not _USERNAME.match(value):
        return "2 to 32 characters: lower-case letters, digits, '_', '.' or '-'."
    return None


def _existing_folder(value: str) -> str | None:
    if not value:
        return "Required."
    path = Path(value).expanduser()
    if not path.is_absolute():
        return "Give an absolute path, starting with /."
    if not path.is_dir():
        return "This folder does not exist."
    return None


def _absolute(value: str) -> str | None:
    if not value:
        return "Required."
    if not Path(value).expanduser().is_absolute():
        return "Give an absolute path, starting with /."
    return None


def _port(value: str) -> str | None:
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        return "A port number from 1 to 65535."
    return None


def _bind(value: str) -> str | None:
    if value in ("127.0.0.1", "localhost"):
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return "127.0.0.1, or this machine's address on the home network (for example 192.168…)."
    if address.is_unspecified:
        return "Never 0.0.0.0: that would publish the server on every network."
    if not any(address in network for network in _HOME_NETWORKS):
        return "Only 127.0.0.1 or a home-network address (10.x, 172.16-31.x, 192.168.x)."
    return None


def _bind_warning(value: str) -> str | None:
    if value in ("127.0.0.1", "localhost", ""):
        return None
    return (
        "Plain HTTP on the home network: passwords and device tokens travel unencrypted. "
        "Use it on a network you trust, or put an HTTPS proxy in front."
    )


def _url(value: str) -> str | None:
    if value and not re.match(r"^https?://[^\s/]+", value):
        return (
            "Empty, or an address starting with https:// (for example https://music.example.net)."
        )
    return None


def _proxies(value: str) -> str | None:
    for part in filter(None, (piece.strip() for piece in value.split(","))):
        try:
            ipaddress.ip_network(part, strict=False)
        except ValueError:
            return f"{part} is not an IP address or network."
    return None


def _whole(value: str) -> str | None:
    if not value.isdigit():
        return "A whole number, 0 or more."
    return None


def _network(value: str) -> str | None:
    if value and not _NETWORK_NAME.match(value):
        return "A Docker network name: letters, digits, '_', '.' or '-'."
    return None


FIELDS: tuple[Field, ...] = (
    Field(
        "ADMIN_USER", "Admin account", "The MTEE account whose music folder is mounted.", _username
    ),
    Field(
        "MUSIC_DIR",
        "Music folder",
        "The folder of your music on this machine. It is used where it is, never copied.",
        _existing_folder,
    ),
    Field(
        "DATA_DIR",
        "Data folder",
        "Database, backups and uploads. Owned by the user below.",
        _absolute,
    ),
    Field(
        "PORT",
        "Port",
        "The port of the server on this machine.",
        _port,
        default=lambda: "8080",
    ),
    Field(
        "BIND_ADDRESS",
        "Listen on",
        "127.0.0.1 (this machine, behind a proxy) or this machine's home-network address.",
        _bind,
        default=lambda: "127.0.0.1",
        warning=_bind_warning,
    ),
    Field(
        "PUBLIC_URL",
        "Public address",
        "The https address your devices use, when a proxy publishes the server.",
        _url,
    ),
    Field(
        "TRUSTED_PROXIES",
        "Trusted proxies",
        "The address of your reverse proxy, as the container sees it. Empty: 127.0.0.1.",
        _proxies,
    ),
    Field(
        "SCAN_INTERVAL",
        "Scan every (seconds)",
        "Scan the libraries for files copied in by hand. 0: only when asked.",
        _whole,
        default=lambda: "0",
    ),
    Field(
        "UID",
        "Files owner (uid)",
        "The user that owns the music files: `id -u`. Changing it rebuilds the image.",
        _whole,
        default=lambda: str(os.getuid()),
    ),
    Field(
        "GID",
        "Files group (gid)",
        "The group of the music files: `id -g`. Changing it rebuilds the image.",
        _whole,
        default=lambda: str(os.getgid()),
    ),
    Field(
        "PROXY_NETWORK",
        "Proxy network",
        "Docker network of a reverse proxy, if compose.yaml joins one. Usually empty.",
        _network,
    ),
)

FIELD_BY_KEY = {field.key: field for field in FIELDS}
# Changing one of these needs `docker compose build`, not only a restart.
BUILD_KEYS = frozenset({"UID", "GID"})


def problems(values: dict[str, str]) -> dict[str, str]:
    """The sentence of each field whose value would be refused."""
    found: dict[str, str] = {}
    for field in FIELDS:
        message = field.check(values.get(field.key, ""))
        if message is not None:
            found[field.key] = message
    return found

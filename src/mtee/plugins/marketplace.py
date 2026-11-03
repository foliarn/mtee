"""The Marketplace: the plugin list, compatible versions and downloads (plan 123.4).

The plugin list is an ``index.json`` in a public GitHub repository. Each plugin has an entry,
and each entry lists its packages (``versions``). A package is downloaded only when the user
asks for it, its size and SHA-256 are checked against the list, and its ``plugin.json`` must
name the same plugin and version. The downloaded file is then installed by the normal path:
``installer.inspect``, the warning, and ``installer.install``. This module never installs.

The HTTP calls use ``urllib.request`` with a timeout; the core has no HTTP client of its own.
This module does not import Qt.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from mtee import __version__
from mtee.plugins.installer import plugins_folder
from mtee.plugins.loader import plugin_id_problem
from mtee.plugins.package import PACKAGE_SUFFIX, PLUGIN_JSON, PackageError, PluginDescription

__all__ = [
    "DOWNLOADS_FOLDER",
    "INDEX_URL",
    "MAX_INDEX_BYTES",
    "OFFICIAL_ADDRESS",
    "MarketplaceCancelledError",
    "MarketplaceEntry",
    "MarketplaceError",
    "MarketplaceIndex",
    "MarketplaceVersion",
    "available_update",
    "compatible_version",
    "download",
    "fetch_index",
    "index_url",
    "normalize_address",
    "parse_index",
]

_LOGGER = logging.getLogger(__name__)

# The raw index.json of the Marketplace repository (foliarn/mtee-plugins, default branch).
# The repository is created by the maintainer. This URL is the single place to change.
INDEX_URL = "https://raw.githubusercontent.com/foliarn/mtee-plugins/main/index.json"
# The official list, as it is named in Settings > Plugins > Marketplaces. It cannot be removed.
OFFICIAL_ADDRESS = "foliarn/mtee-plugins"
INDEX_SCHEMA = 1
MAX_INDEX_BYTES = 2 * 1024 * 1024
DOWNLOADS_FOLDER = ".downloads"
_CHUNK_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UNREADABLE = "The plugin list could not be read"
_GITHUB_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+")
_GITHUB_PAGE = re.compile(
    r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+?)(?:\.git)?/?"
)

Opener = Callable[..., Any]
ProgressCallback = Callable[[int, int], None]


class MarketplaceError(RuntimeError):
    """The Marketplace cannot be read or a download is refused; the message is one sentence."""

    # Shown in Tasks as its message alone (see docs/plugins.md, the readable attribute).
    readable = True


class MarketplaceCancelledError(MarketplaceError):
    """A download was cancelled by the user; the partial file has been removed."""


@dataclass(frozen=True, slots=True)
class MarketplaceVersion:
    """One package of a plugin, as the index describes it.

    ``size`` is the size of the package file in bytes; ``sha256`` is its digest in lowercase hex.
    ``platform`` is ``"any"`` or ``"win_amd64"``, as in ``plugin.json``.
    """

    version: str
    api_version: int
    python: str
    platform: str
    url: str
    sha256: str
    size: int
    released: str


@dataclass(frozen=True, slots=True)
class MarketplaceEntry:
    """A plugin of the Marketplace, with the packages its entry lists, in the order of the index."""

    id: str
    title: str
    description: str
    author: str
    homepage: str
    licence: str
    uses_network: bool
    versions: tuple[MarketplaceVersion, ...]


@dataclass(frozen=True, slots=True)
class MarketplaceIndex:
    """The plugin list: its schema number and its entries."""

    schema: int
    entries: tuple[MarketplaceEntry, ...]


class _BadEntryError(ValueError):
    """One entry of the plugin list is not usable; the entry is skipped and the reason logged."""


def parse_index(text: str) -> MarketplaceIndex:
    """Read the text of an ``index.json``.

    Raise ``MarketplaceError`` with one sentence when the text is not a JSON object, names another
    schema, or has no ``plugins`` list. A bad entry is logged and skipped, so that one bad plugin
    does not hide the others.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        reason = f"it is not valid JSON (line {error.lineno})"
        raise MarketplaceError(f"{_UNREADABLE}: {reason}.") from error
    if not isinstance(data, dict):
        raise MarketplaceError(f"{_UNREADABLE}: it does not hold one JSON object.")
    schema = _top_field(data, "schema", int)
    if schema != INDEX_SCHEMA:
        raise MarketplaceError(
            f"{_UNREADABLE}: it has schema {schema}, but this MTEE reads schema {INDEX_SCHEMA}."
        )
    items = _top_field(data, "plugins", list)
    entries: list[MarketplaceEntry] = []
    for number, item in enumerate(items, start=1):
        try:
            entries.append(_entry(item))
        except _BadEntryError as error:
            _LOGGER.warning("Plugin list entry %d is skipped: %s", number, error)
    return MarketplaceIndex(schema, tuple(entries))


def _top_field(data: Mapping[str, Any], key: str, kind: type) -> Any:
    """Return a top-level field of the index, refusing a missing one or one of another type."""
    expected = "a whole number" if kind is int else "a list"
    if key not in data:
        raise MarketplaceError(f"{_UNREADABLE}: it has no {key} field.")
    value = data[key]
    if not _is_kind(value, kind):
        raise MarketplaceError(f"{_UNREADABLE}: its {key} field must be {expected}.")
    return value


def _is_kind(value: Any, kind: type) -> bool:
    """Return whether ``value`` has the type ``kind``. A JSON true is not a whole number."""
    return isinstance(value, kind) and not (kind is int and isinstance(value, bool))


def _field(data: Mapping[str, Any], key: str, kind: type, where: str) -> Any:
    """Return a field of an entry or of a package, refusing a missing one or one of another type."""
    if key not in data:
        raise _BadEntryError(f"{where} has no {key} field")
    value = data[key]
    if not _is_kind(value, kind):
        names = {str: "a text", int: "a whole number", bool: "true or false", list: "a list"}
        raise _BadEntryError(
            f"the {key} field of {where} must be {names.get(kind, 'of another type')}"
        )
    return value


def _entry(item: Any) -> MarketplaceEntry:
    """Read one plugin of the ``plugins`` list."""
    if not isinstance(item, dict):
        raise _BadEntryError("it is not an object")
    plugin_id = _field(item, "id", str, "an entry")
    problem = plugin_id_problem(plugin_id)
    if problem:
        raise _BadEntryError(problem)
    where = f"the entry {plugin_id}"
    versions = tuple(_version(value, where) for value in _field(item, "versions", list, where))
    return MarketplaceEntry(
        id=plugin_id,
        title=_field(item, "title", str, where),
        description=_field(item, "description", str, where),
        author=_field(item, "author", str, where),
        homepage=_field(item, "homepage", str, where),
        licence=_field(item, "licence", str, where),
        uses_network=_field(item, "uses_network", bool, where),
        versions=versions,
    )


def _version(item: Any, where: str) -> MarketplaceVersion:
    """Read one package of the ``versions`` list of an entry."""
    if not isinstance(item, dict):
        raise _BadEntryError(f"a package of {where} is not an object")
    version = _field(item, "version", str, where)
    try:
        Version(version)
    except InvalidVersion as error:
        raise _BadEntryError(
            f"the version {version!r} of {where} is not a version number"
        ) from error
    sha256 = _field(item, "sha256", str, where)
    if not _SHA256.fullmatch(sha256):
        raise _BadEntryError(f"the sha256 of {where} {version} is not 64 lowercase hex digits")
    size = _field(item, "size", int, where)
    if size < 0:
        raise _BadEntryError(f"the size of {where} {version} is negative")
    return MarketplaceVersion(
        version=version,
        api_version=_field(item, "api_version", int, where),
        python=_field(item, "python", str, where),
        platform=_field(item, "platform", str, where),
        url=_field(item, "url", str, where),
        sha256=sha256,
        size=size,
        released=_field(item, "released", str, where),
    )


def normalize_address(text: str) -> str:
    """Return the address of a marketplace as it is kept: ``owner/repo`` or an https URL.

    A GitHub page address (``https://github.com/owner/repo``) becomes ``owner/repo``. Raise
    ``MarketplaceError`` with one sentence for anything else.
    """
    address = text.strip()
    page = _GITHUB_PAGE.fullmatch(address)
    if page is not None:
        return page.group(1)
    if _GITHUB_REPO.fullmatch(address):
        return address
    parsed = urllib.parse.urlsplit(address)
    if parsed.scheme == "https" and parsed.netloc and " " not in address:
        return address
    raise MarketplaceError(
        "Enter a GitHub repository as owner/repo, or an https address of an index.json."
    )


def index_url(address: str) -> str:
    """Return the URL of the ``index.json`` of a marketplace address.

    ``owner/repo`` is the ``index.json`` at the root of the repository's default branch.
    """
    if address == OFFICIAL_ADDRESS:
        return INDEX_URL
    if _GITHUB_REPO.fullmatch(address):
        return f"https://raw.githubusercontent.com/{address}/HEAD/index.json"
    return address


def fetch_index(
    url: str = INDEX_URL, *, opener: Opener | None = None, timeout: float = 30
) -> MarketplaceIndex:
    """Download and read the plugin list at ``url``.

    ``opener`` replaces ``urllib.request.urlopen`` in tests. Raise ``MarketplaceError`` with one
    sentence on a network, HTTP, size or JSON problem.
    """
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(_request(url), timeout=timeout) as response:
            data = _read_limited(response)
    except (OSError, http.client.HTTPException) as error:
        raise MarketplaceError(f"{_UNREADABLE}: {_network_reason(error)}.") from error
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MarketplaceError(f"{_UNREADABLE}: it is not written in UTF-8.") from error
    return parse_index(text)


def _read_limited(response: Any) -> bytes:
    """Read a response, refusing more than ``MAX_INDEX_BYTES``."""
    data = bytearray()
    while chunk := response.read(_CHUNK_BYTES):
        data.extend(chunk)
        if len(data) > MAX_INDEX_BYTES:
            raise MarketplaceError(f"{_UNREADABLE}: it is larger than 2 MB.")
    return bytes(data)


def _network_reason(error: BaseException) -> str:
    """Return a short reason for a network or HTTP error, for the one-line message."""
    if isinstance(error, urllib.error.HTTPError):
        return f"the server answered HTTP {error.code}"
    if isinstance(error, TimeoutError):
        return "the connection timed out"
    if isinstance(error, http.client.HTTPException):
        return "the server reply was not understood"
    return "the connection failed"


def _request(url: str) -> urllib.request.Request:
    """Return a GET request that names MTEE and its version."""
    return urllib.request.Request(url, headers={"User-Agent": f"MTEE/{__version__}"})


def compatible_version(
    entry: MarketplaceEntry,
    *,
    mtee_version: str,
    api_versions: Collection[int],
    python: str,
    platform: str,
) -> MarketplaceVersion | None:
    """Return the highest package of ``entry`` that this MTEE can install, or ``None``.

    A package is compatible when its plugin interface is in ``api_versions``, its Python is
    ``python``, and its platform is ``"any"`` or ``platform``. ``mtee_version`` is accepted for
    the callers of the Marketplace; the index holds no MTEE range, so it is not compared here.
    The installer checks the ``mtee`` range of each package when it is inspected.
    """
    usable = [
        version
        for version in entry.versions
        if version.api_version in api_versions
        and version.python == python
        and version.platform in ("any", platform)
    ]
    if not usable:
        return None
    return max(usable, key=lambda version: Version(version.version))


def available_update(
    entry: MarketplaceEntry,
    installed_version: str,
    *,
    mtee_version: str,
    api_versions: Collection[int],
    python: str,
    platform: str,
) -> MarketplaceVersion | None:
    """Return the compatible package of ``entry`` when it is newer than ``installed_version``.

    An installed version that is not a version number has no update.
    """
    candidate = compatible_version(
        entry,
        mtee_version=mtee_version,
        api_versions=api_versions,
        python=python,
        platform=platform,
    )
    if candidate is None:
        return None
    try:
        installed = Version(installed_version)
    except InvalidVersion:
        return None
    return candidate if Version(candidate.version) > installed else None


def downloads_folder(data_dir: Path) -> Path:
    """Return the folder where downloaded packages wait until they are checked and installed."""
    return plugins_folder(data_dir) / DOWNLOADS_FOLDER


def download(
    entry: MarketplaceEntry,
    version: MarketplaceVersion,
    *,
    data_dir: Path,
    opener: Opener | None = None,
    timeout: float = 60,
    progress: ProgressCallback | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Download one package of ``entry`` into the downloads folder and return its path.

    The address must be a GitHub release address, checked before any request. The file is
    streamed to ``<id>-<version>.mteeplugin.part``; its size and SHA-256 must match the index, and
    its ``plugin.json`` must name the same plugin and version. Only then is it renamed to its
    final name. The package is not installed here. ``progress(done, size)`` is called after each
    chunk; ``cancelled()`` is asked before each chunk and stops the download.
    """
    label = f"{entry.title} {version.version}"
    if not _is_github_release(version.url):
        raise MarketplaceError(
            f"The download of {label} was refused: its address is not a GitHub release."
        )
    folder = downloads_folder(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{entry.id}-{version.version}{PACKAGE_SUFFIX}"
    partial = folder / f"{name}.part"
    # This call creates the .part file. A leftover from an interrupted download is replaced.
    sink = partial.open("wb")
    try:
        with sink:
            size, digest = _stream(
                _request(version.url),
                sink,
                label=label,
                size=version.size,
                opener=opener or urllib.request.urlopen,
                timeout=timeout,
                progress=progress,
                cancelled=cancelled,
            )
        _check_download(partial, entry, version, label, size, digest)
        final = folder / name
        os.replace(partial, final)
    except BaseException:
        # The .part file was created by this call (see above), so this call removes it.
        partial.unlink(missing_ok=True)
        raise
    return final


def _is_github_release(url: str) -> bool:
    """Return whether ``url`` is an https address on github.com under ``releases/download/``."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc.lower() != "github.com":
        return False
    segments = parts.path.split("/")
    # ["", owner, repo, "releases", "download", tag, file]; every name must be present.
    return (
        len(segments) == 7
        and segments[3:5] == ["releases", "download"]
        and all(segments[1:3] + segments[5:])
    )


def _stream(
    request: urllib.request.Request,
    sink: Any,
    *,
    label: str,
    size: int,
    opener: Opener,
    timeout: float,
    progress: ProgressCallback | None,
    cancelled: Callable[[], bool] | None,
) -> tuple[int, str]:
    """Write the response to ``sink``; return the bytes written and their SHA-256 in hex."""
    digest = hashlib.sha256()
    total = 0
    try:
        with opener(request, timeout=timeout) as response:
            while True:
                if cancelled is not None and cancelled():
                    raise MarketplaceCancelledError(f"The download of {label} was cancelled.")
                chunk = response.read(_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > size:
                    raise MarketplaceError(_size_sentence(label))
                sink.write(chunk)
                digest.update(chunk)
                if progress is not None:
                    progress(total, size)
    except (OSError, http.client.HTTPException) as error:
        raise MarketplaceError(
            f"The download of {label} failed: {_network_reason(error)}."
        ) from error
    return total, digest.hexdigest()


def _size_sentence(label: str) -> str:
    return f"The downloaded file of {label} does not match the plugin list (size)."


def _check_download(
    partial: Path,
    entry: MarketplaceEntry,
    version: MarketplaceVersion,
    label: str,
    size: int,
    digest: str,
) -> None:
    """Check the size, the SHA-256 and the ``plugin.json`` of a downloaded package."""
    if size != version.size:
        raise MarketplaceError(_size_sentence(label))
    if digest != version.sha256:
        raise MarketplaceError(
            f"The downloaded file of {label} does not match the plugin list (checksum)."
        )
    try:
        with zipfile.ZipFile(partial) as archive:
            text = archive.read(PLUGIN_JSON).decode("utf-8")
        description = PluginDescription.from_json(text)
    except (zipfile.BadZipFile, KeyError, OSError, UnicodeDecodeError, PackageError) as error:
        raise MarketplaceError(
            f"The downloaded file of {label} is not a readable plugin package."
        ) from error
    if description.id != entry.id or description.version != version.version:
        raise MarketplaceError(
            f"The downloaded package of {label} holds {description.id} {description.version}, "
            f"not {entry.id} {version.version}."
        )

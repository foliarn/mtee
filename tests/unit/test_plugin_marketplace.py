"""The Marketplace index, compatible versions and downloads (plan 123.4).

No test reaches the internet. Downloads and index reads use a fake opener, except one test that
serves the index from a local HTTP server on 127.0.0.1 and reads it with the real ``urlopen``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import http.client
import io
import json
import os
import threading
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from mtee.plugins import marketplace
from mtee.plugins.api import API_VERSION
from mtee.plugins.installer import plugins_folder
from mtee.plugins.marketplace import (
    MAX_INDEX_BYTES,
    MarketplaceCancelledError,
    MarketplaceEntry,
    MarketplaceError,
    MarketplaceVersion,
    available_update,
    compatible_version,
    download,
    fetch_index,
    parse_index,
)
from mtee.plugins.package import PluginDescription

GITHUB_URL = (
    "https://github.com/foliarn/mtee-plugins/releases/download/alpha-1.0.0/alpha-1.0.0.mteeplugin"
)
UNREADABLE = "The plugin list could not be read"


class FakeOpener:
    """Stands in for ``urlopen``: records each request and answers with ``body``."""

    def __init__(self, body: bytes = b"", *, error: BaseException | None = None) -> None:
        self.body = body
        self.error = error
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def __call__(self, request: urllib.request.Request, timeout: float = 0) -> Any:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.body)


def _write_package(folder: Path, plugin_id: str = "alpha", version: str = "1.0.0", **extra: bytes):
    """Write a minimal ``.mteeplugin`` with a ``plugin.json`` and return its path."""
    description = PluginDescription(
        id=plugin_id,
        title=f"Sample {plugin_id}",
        description="A sample plugin.",
        version=version,
        api_version=API_VERSION,
        author="",
        homepage="",
        licence="",
        uses_network=False,
        python="3.12",
        platform="any",
        mtee=">=0.1,<0.2",
        libraries=(),
        top_level_modules={},
    )
    path = folder / f"{plugin_id}-{version}.mteeplugin"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("plugin.json", description.to_json())
        archive.writestr(f"{plugin_id}/__init__.py", "VALUE = 1\n")
        for name, data in extra.items():
            archive.writestr(f"{plugin_id}/{name}", data)
    return path


def _version_of(
    path: Path,
    *,
    version: str = "1.0.0",
    api_version: int = API_VERSION,
    python: str = "3.12",
    platform: str = "any",
    url: str = GITHUB_URL,
) -> MarketplaceVersion:
    data = path.read_bytes()
    return MarketplaceVersion(
        version=version,
        api_version=api_version,
        python=python,
        platform=platform,
        url=url,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        released="2026-11-02",
    )


def _entry(
    versions: tuple[MarketplaceVersion, ...] = (), plugin_id: str = "alpha"
) -> MarketplaceEntry:
    return MarketplaceEntry(
        id=plugin_id,
        title="Alpha",
        description="A plugin.",
        author="",
        homepage="",
        licence="GPL-3.0-or-later",
        uses_network=False,
        versions=versions,
    )


def _version_dict(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "version": "1.0.0",
        "api_version": 1,
        "python": "3.12",
        "platform": "any",
        "url": GITHUB_URL,
        "sha256": "a" * 64,
        "size": 10,
        "released": "2026-11-02",
    }
    data.update(changes)
    return data


def _entry_dict(
    plugin_id: str = "alpha", *, versions: Any = None, **changes: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": plugin_id,
        "title": "Alpha",
        "description": "A plugin.",
        "author": "Someone",
        "homepage": "https://example.org/alpha",
        "licence": "GPL-3.0-or-later",
        "uses_network": False,
        "versions": [_version_dict()] if versions is None else versions,
    }
    data.update(changes)
    return data


def _index_text(*entries: dict[str, Any], schema: Any = 1) -> str:
    return json.dumps({"schema": schema, "plugins": list(entries)})


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


def _downloads(data_dir: Path) -> Path:
    return plugins_folder(data_dir) / marketplace.DOWNLOADS_FOLDER


# parse_index


def test_a_valid_index_gives_its_entries_and_versions() -> None:
    index = parse_index(_index_text(_entry_dict(), _entry_dict("gamma", title="Gamma")))

    assert index.schema == 1
    assert [entry.id for entry in index.entries] == ["alpha", "gamma"]
    alpha = index.entries[0]
    assert alpha.title == "Alpha"
    assert alpha.uses_network is False
    assert alpha.versions == (
        MarketplaceVersion(
            version="1.0.0",
            api_version=1,
            python="3.12",
            platform="any",
            url=GITHUB_URL,
            sha256="a" * 64,
            size=10,
            released="2026-11-02",
        ),
    )


def test_an_index_with_no_plugins_is_valid() -> None:
    index = parse_index('{"schema": 1, "plugins": []}')

    assert index.entries == ()


def test_an_unknown_schema_is_refused_with_one_sentence() -> None:
    with pytest.raises(MarketplaceError) as caught:
        parse_index(_index_text(schema=2))

    assert str(caught.value) == (f"{UNREADABLE}: it has schema 2, but this MTEE reads schema 1.")


def test_a_boolean_schema_is_not_a_whole_number() -> None:
    with pytest.raises(MarketplaceError, match="must be a whole number"):
        parse_index(_index_text(schema=True))


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("{", "it is not valid JSON"),
        ("[]", "it does not hold one JSON object"),
        ('{"schema": 1}', "it has no plugins field"),
        ('{"schema": 1, "plugins": {}}', "its plugins field must be a list"),
    ],
)
def test_a_bad_top_level_is_refused_with_one_readable_sentence(text: str, reason: str) -> None:
    with pytest.raises(MarketplaceError) as caught:
        parse_index(text)

    assert str(caught.value).startswith(UNREADABLE)
    assert reason in str(caught.value)
    assert str(caught.value).endswith(".")


def test_a_bad_entry_is_skipped_and_the_others_stay(caplog: pytest.LogCaptureFixture) -> None:
    bad = _entry_dict("beta", title=42)
    text = _index_text(_entry_dict("alpha"), bad, _entry_dict("gamma"))

    with caplog.at_level("WARNING", logger="mtee.plugins.marketplace"):
        index = parse_index(text)

    assert [entry.id for entry in index.entries] == ["alpha", "gamma"]
    assert "Plugin list entry 2 is skipped" in caplog.text
    assert "title" in caplog.text


@pytest.mark.parametrize(
    "bad_entry",
    [
        _entry_dict(id="../evil"),
        _entry_dict(id="Not-Snake"),
        _entry_dict(uses_network="yes"),
        _entry_dict(homepage=None),
        _entry_dict(versions={}),
        _entry_dict(versions=[_version_dict(api_version="1")]),
        _entry_dict(versions=[_version_dict(api_version=True)]),
        _entry_dict(versions=[_version_dict(size="10")]),
        _entry_dict(versions=[_version_dict(size=-1)]),
        _entry_dict(versions=[_version_dict(size=True)]),
        _entry_dict(versions=[_version_dict(version="not a version")]),
        _entry_dict(versions=[_version_dict(version="../../x")]),
        _entry_dict(versions=[_version_dict(sha256="A" * 64)]),
        _entry_dict(versions=[_version_dict(sha256="abc")]),
        _entry_dict(versions=[_version_dict(url=None)]),
        _entry_dict(versions=["1.0.0"]),
    ],
)
def test_an_entry_with_a_wrong_field_is_skipped(bad_entry: dict[str, Any]) -> None:
    index = parse_index(_index_text(bad_entry, _entry_dict("gamma")))

    assert [entry.id for entry in index.entries] == ["gamma"]


def test_a_missing_entry_field_is_skipped() -> None:
    entry = _entry_dict("alpha")
    del entry["licence"]

    assert parse_index(_index_text(entry)).entries == ()


# fetch_index


def test_fetch_index_reads_the_list_and_names_mtee_in_the_user_agent() -> None:
    opener = FakeOpener(_index_text(_entry_dict()).encode("utf-8"))

    index = fetch_index("https://example.org/index.json", opener=opener, timeout=7)

    assert [entry.id for entry in index.entries] == ["alpha"]
    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.full_url == "https://example.org/index.json"
    assert request.get_header("User-agent", "").startswith("MTEE/")
    assert opener.timeouts == [7]


def test_an_http_error_is_one_readable_sentence() -> None:
    error = urllib.error.HTTPError(
        "https://example.org/index.json", 404, "Not Found", http.client.HTTPMessage(), None
    )

    with pytest.raises(MarketplaceError) as caught:
        fetch_index("https://example.org/index.json", opener=FakeOpener(error=error))

    assert str(caught.value) == f"{UNREADABLE}: the server answered HTTP 404."


def test_a_network_error_is_one_readable_sentence() -> None:
    error = urllib.error.URLError("no route to host")

    with pytest.raises(MarketplaceError) as caught:
        fetch_index("https://example.org/index.json", opener=FakeOpener(error=error))

    assert str(caught.value) == f"{UNREADABLE}: the connection failed."


def test_a_timeout_is_one_readable_sentence() -> None:
    with pytest.raises(MarketplaceError, match="the connection timed out"):
        fetch_index("https://example.org/index.json", opener=FakeOpener(error=TimeoutError()))


def test_invalid_json_from_the_server_is_refused() -> None:
    with pytest.raises(MarketplaceError, match="it is not valid JSON"):
        fetch_index("https://example.org/index.json", opener=FakeOpener(b"{"))


def test_a_list_that_is_not_utf8_is_refused() -> None:
    with pytest.raises(MarketplaceError, match="not written in UTF-8"):
        fetch_index("https://example.org/index.json", opener=FakeOpener(b"\xff\xfe\x00"))


def test_a_list_larger_than_the_limit_is_refused() -> None:
    body = b" " * (MAX_INDEX_BYTES + 1)

    with pytest.raises(MarketplaceError, match="it is larger than 2 MB"):
        fetch_index("https://example.org/index.json", opener=FakeOpener(body))


@pytest.fixture
def index_server() -> Iterator[tuple[str, list[str]]]:
    """Serve ``/index.json`` on 127.0.0.1 and record the User-Agent of each request."""
    agents: list[str] = []
    body = _index_text(_entry_dict()).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            agents.append(self.headers.get("User-Agent", ""))
            if self.path != "/index.json":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", agents
    finally:
        server.shutdown()
        server.server_close()


def test_fetch_index_reads_a_local_server_with_the_real_opener(
    index_server: tuple[str, list[str]],
) -> None:
    base, agents = index_server

    index = fetch_index(f"{base}/index.json", timeout=5)

    assert [entry.id for entry in index.entries] == ["alpha"]
    assert agents[-1].startswith("MTEE/")


def test_fetch_index_reports_a_missing_file_on_a_local_server(
    index_server: tuple[str, list[str]],
) -> None:
    base, _ = index_server

    with pytest.raises(MarketplaceError, match="the server answered HTTP 404"):
        fetch_index(f"{base}/missing.json", timeout=5)


# compatible_version and available_update


def _choice_entry(tmp_path: Path) -> MarketplaceEntry:
    package = _write_package(tmp_path)
    return _entry(
        (
            _version_of(package, version="1.0.0"),
            _version_of(package, version="1.2.0", platform="win_amd64"),
            _version_of(package, version="1.1.0", api_version=API_VERSION + 1),
            _version_of(package, version="1.3.0", python="3.11"),
            _version_of(package, version="1.4.0", platform="darwin"),
        )
    )


def test_compatible_version_takes_the_highest_usable_package(tmp_path: Path) -> None:
    entry = _choice_entry(tmp_path)

    chosen = compatible_version(
        entry,
        mtee_version="0.1.0",
        api_versions={API_VERSION},
        python="3.12",
        platform="win_amd64",
    )

    assert chosen is not None
    assert chosen.version == "1.2.0"


def test_compatible_version_ignores_another_platform_api_or_python(tmp_path: Path) -> None:
    entry = _choice_entry(tmp_path)

    chosen = compatible_version(
        entry,
        mtee_version="0.1.0",
        api_versions={API_VERSION},
        python="3.12",
        platform="linux",
    )

    assert chosen is not None
    assert chosen.version == "1.0.0"


def test_compatible_version_is_none_when_nothing_fits(tmp_path: Path) -> None:
    entry = _choice_entry(tmp_path)

    assert (
        compatible_version(
            entry,
            mtee_version="0.1.0",
            api_versions={API_VERSION + 5},
            python="3.12",
            platform="win_amd64",
        )
        is None
    )
    assert (
        compatible_version(
            _entry(),
            mtee_version="0.1.0",
            api_versions={API_VERSION},
            python="3.12",
            platform="any",
        )
        is None
    )


def test_compatible_version_compares_versions_not_text(tmp_path: Path) -> None:
    package = _write_package(tmp_path)
    entry = _entry(
        (
            _version_of(package, version="1.10.0"),
            _version_of(package, version="1.9.0"),
        )
    )

    chosen = compatible_version(
        entry, mtee_version="0.1.0", api_versions={API_VERSION}, python="3.12", platform="any"
    )

    assert chosen is not None
    assert chosen.version == "1.10.0"


def test_available_update_offers_a_newer_compatible_package(tmp_path: Path) -> None:
    entry = _choice_entry(tmp_path)

    update = available_update(
        entry,
        "1.0.0",
        mtee_version="0.1.0",
        api_versions={API_VERSION},
        python="3.12",
        platform="win_amd64",
    )

    assert update is not None
    assert update.version == "1.2.0"


@pytest.mark.parametrize("installed", ["1.2.0", "1.3.0", "2.0.0"])
def test_available_update_is_none_when_equal_or_lower(tmp_path: Path, installed: str) -> None:
    entry = _choice_entry(tmp_path)

    assert (
        available_update(
            entry,
            installed,
            mtee_version="0.1.0",
            api_versions={API_VERSION},
            python="3.12",
            platform="win_amd64",
        )
        is None
    )


def test_available_update_is_none_for_an_installed_version_that_is_not_a_number(
    tmp_path: Path,
) -> None:
    entry = _choice_entry(tmp_path)

    assert (
        available_update(
            entry,
            "not a version",
            mtee_version="0.1.0",
            api_versions={API_VERSION},
            python="3.12",
            platform="win_amd64",
        )
        is None
    )


# download


def test_a_download_is_checked_and_renamed_into_the_downloads_folder(
    tmp_path: Path, data_dir: Path
) -> None:
    package = _write_package(tmp_path)
    version = _version_of(package)
    opener = FakeOpener(package.read_bytes())
    progress: list[tuple[int, int]] = []

    path = download(
        _entry(),
        version,
        data_dir=data_dir,
        opener=opener,
        progress=lambda d, t: progress.append((d, t)),
    )

    assert path == _downloads(data_dir) / "alpha-1.0.0.mteeplugin"
    assert path.read_bytes() == package.read_bytes()
    assert sorted(child.name for child in _downloads(data_dir).iterdir()) == [
        "alpha-1.0.0.mteeplugin"
    ]
    assert [request.full_url for request in opener.requests] == [GITHUB_URL]
    assert progress[-1] == (version.size, version.size)
    assert [done for done, _ in progress] == sorted(done for done, _ in progress)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/foliarn/mtee-plugins/releases/download/t/alpha-1.0.0.mteeplugin",
        "https://example.org/foliarn/mtee-plugins/releases/download/t/alpha-1.0.0.mteeplugin",
        "https://github.com.example.org/foliarn/mtee-plugins/releases/download/t/a.mteeplugin",
        "https://user@github.com/foliarn/mtee-plugins/releases/download/t/a.mteeplugin",
        "https://github.com:8443/foliarn/mtee-plugins/releases/download/t/a.mteeplugin",
        "https://api.github.com/foliarn/mtee-plugins/releases/download/t/a.mteeplugin",
        "https://github.com/foliarn/mtee-plugins/archive/refs/tags/t.zip",
        "https://github.com/foliarn/releases/download/t/a.mteeplugin",
        "https://github.com/foliarn/mtee-plugins/releases/download/t/",
        "https://raw.githubusercontent.com/foliarn/mtee-plugins/main/a.mteeplugin",
    ],
)
def test_a_download_from_another_address_is_refused_before_any_request(
    tmp_path: Path, data_dir: Path, url: str
) -> None:
    package = _write_package(tmp_path)
    version = _version_of(package, url=url)
    opener = FakeOpener(package.read_bytes())

    with pytest.raises(MarketplaceError) as caught:
        download(_entry(), version, data_dir=data_dir, opener=opener)

    assert str(caught.value) == (
        "The download of Alpha 1.0.0 was refused: its address is not a GitHub release."
    )
    assert opener.requests == []
    assert not _downloads(data_dir).exists()


def test_a_size_that_does_not_match_the_list_is_refused_and_nothing_is_kept(
    tmp_path: Path, data_dir: Path
) -> None:
    package = _write_package(tmp_path)
    real = _version_of(package)
    version = dataclasses.replace(real, size=real.size + 1)

    with pytest.raises(MarketplaceError) as caught:
        download(_entry(), version, data_dir=data_dir, opener=FakeOpener(package.read_bytes()))

    assert str(caught.value) == (
        "The downloaded file of Alpha 1.0.0 does not match the plugin list (size)."
    )
    assert list(_downloads(data_dir).iterdir()) == []


def test_a_checksum_that_does_not_match_the_list_is_refused_and_nothing_is_kept(
    tmp_path: Path, data_dir: Path
) -> None:
    package = _write_package(tmp_path)
    real = _version_of(package)
    version = dataclasses.replace(real, sha256="0" * 64)

    with pytest.raises(MarketplaceError) as caught:
        download(_entry(), version, data_dir=data_dir, opener=FakeOpener(package.read_bytes()))

    assert str(caught.value) == (
        "The downloaded file of Alpha 1.0.0 does not match the plugin list (checksum)."
    )
    assert list(_downloads(data_dir).iterdir()) == []


def test_more_bytes_than_the_list_says_are_refused_as_a_size_mismatch(
    tmp_path: Path, data_dir: Path
) -> None:
    package = _write_package(tmp_path)
    real = _version_of(package)
    version = dataclasses.replace(real, size=real.size - 10)

    with pytest.raises(MarketplaceError, match=r"\(size\)\.$"):
        download(_entry(), version, data_dir=data_dir, opener=FakeOpener(package.read_bytes()))

    assert list(_downloads(data_dir).iterdir()) == []


def test_a_cancel_midway_removes_the_partial_file(tmp_path: Path, data_dir: Path) -> None:
    package = _write_package(tmp_path, data=os.urandom(300_000))
    version = _version_of(package)
    seen: list[int] = []

    def progress(done: int, total: int) -> None:
        seen.append(done)

    with pytest.raises(MarketplaceCancelledError, match="was cancelled"):
        download(
            _entry(),
            version,
            data_dir=data_dir,
            opener=FakeOpener(package.read_bytes()),
            progress=progress,
            cancelled=lambda: bool(seen),
        )

    assert seen and seen[0] < version.size
    assert list(_downloads(data_dir).iterdir()) == []


def test_a_package_of_another_plugin_is_refused_and_removed(tmp_path: Path, data_dir: Path) -> None:
    package = _write_package(tmp_path, plugin_id="other")
    version = _version_of(package)

    with pytest.raises(MarketplaceError) as caught:
        download(
            _entry(plugin_id="alpha"),
            version,
            data_dir=data_dir,
            opener=FakeOpener(package.read_bytes()),
        )

    assert "holds other 1.0.0, not alpha 1.0.0" in str(caught.value)
    assert list(_downloads(data_dir).iterdir()) == []


def test_a_package_of_another_version_is_refused_and_removed(
    tmp_path: Path, data_dir: Path
) -> None:
    package = _write_package(tmp_path, version="2.0.0")
    version = _version_of(package, version="1.0.0")

    with pytest.raises(MarketplaceError, match=r"holds alpha 2.0.0, not alpha 1.0.0"):
        download(_entry(), version, data_dir=data_dir, opener=FakeOpener(package.read_bytes()))

    assert list(_downloads(data_dir).iterdir()) == []


def test_a_file_that_is_not_a_package_is_refused_and_removed(
    tmp_path: Path, data_dir: Path
) -> None:
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"not a zip")
    version = _version_of(junk)

    with pytest.raises(MarketplaceError, match="is not a readable plugin package"):
        download(_entry(), version, data_dir=data_dir, opener=FakeOpener(junk.read_bytes()))

    assert list(_downloads(data_dir).iterdir()) == []


def test_a_network_error_during_the_download_is_one_sentence_and_removes_the_partial(
    tmp_path: Path, data_dir: Path
) -> None:
    package = _write_package(tmp_path)
    version = _version_of(package)

    with pytest.raises(MarketplaceError) as caught:
        download(
            _entry(),
            version,
            data_dir=data_dir,
            opener=FakeOpener(error=urllib.error.URLError("reset")),
        )

    assert str(caught.value) == "The download of Alpha 1.0.0 failed: the connection failed."
    assert list(_downloads(data_dir).iterdir()) == []

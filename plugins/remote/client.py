"""HTTP client of MTEE Remote, on the standard library (``http.client``) only.

A new connection is opened for each request, so the client may be used from any thread. The
client never logs anything: the password and the token must not reach a log, and a message
that reaches the user names the cause only, never a secret.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.client
import json
import os
import socket
import ssl
import threading
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeGuard
from urllib.parse import quote, urlencode, urlsplit

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
# A download is read in chunks of this size; a chunk is also the unit of a resumed download.
DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 180.0
_HASH_CHUNK_BYTES = 1024 * 1024
_RANGE_NOT_SATISFIABLE = 416
_UNREADABLE = "The server answered with something MTEE cannot read."
_ADDRESS_MESSAGE = (
    "The server address must start with https://, for example https://music.example.net. "
    "Without https, only http://127.0.0.1:<port> and http://localhost:<port> are accepted."
)


class ApiError(Exception):
    """A refusal of the server, from its `{"error": {"code", "message"}}` body."""

    readable = True

    def __init__(
        self, status: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers: dict[str, str] = dict(headers or {})


class UploadOffsetError(Exception):
    """The server holds other bytes than the chunk starts at: the upload goes on at ``offset``."""

    readable = True

    def __init__(self, offset: int) -> None:
        super().__init__(f"The server holds {offset} bytes of this upload.")
        self.offset = offset


class NetworkError(Exception):
    """The server could not be reached: a connection, a timeout or a TLS failure."""

    readable = True


class DownloadError(Exception):
    """A downloaded file whose bytes are not the SHA-256 the server reported (it is discarded)."""

    readable = True


class _Cancellable(Protocol):
    """What a download needs of its job: the cancellation check and the progress."""

    def raise_if_cancelled(self) -> None: ...

    def report_progress(self, progress: float) -> None: ...


@dataclass(frozen=True)
class ChangePage:
    """One page of the change journal: the entries after the requested sequence number."""

    changes: tuple[dict[str, Any], ...]
    next: int
    more: bool


@dataclass(frozen=True)
class PlayEventPage:
    """One page of the play events; each has ``seq``, ``event_id``, ``device_id``, ``payload``."""

    events: tuple[dict[str, Any], ...]
    next: int
    more: bool


def normalize_base_url(base_url: str) -> str:
    """Return the server address without its trailing slash, or raise ``ValueError``.

    ``https://`` is required, except for ``127.0.0.1`` and ``localhost`` with a port (tests).
    Credentials, a query and a fragment are refused.
    """
    text = base_url.strip()
    parts = urlsplit(text)
    if parts.scheme not in ("https", "http"):
        raise ValueError(_ADDRESS_MESSAGE)
    if parts.username is not None or parts.password is not None:
        raise ValueError("The server address must not contain a user name or a password.")
    if parts.query or parts.fragment:
        raise ValueError("The server address must not contain a query or a fragment.")
    host = parts.hostname or ""
    if not host:
        raise ValueError("The server address has no host name, for example music.example.net.")
    if parts.scheme == "http" and (host not in LOCAL_HOSTS or parts.port is None):
        raise ValueError(_ADDRESS_MESSAGE)
    path = parts.path.rstrip("/")
    return f"{parts.scheme}://{parts.netloc}{path}"


def _api_error(status: int, data: bytes) -> ApiError:
    code = f"http_{status}"
    message = f"The server answered with an error ({status})."
    try:
        parsed: Any = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        raw_code = parsed["error"].get("code")
        raw_message = parsed["error"].get("message")
        if isinstance(raw_code, str) and raw_code:
            code = raw_code
        if isinstance(raw_message, str) and raw_message:
            message = raw_message
    return ApiError(status, code, message)


def _json_body(status: int, data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ApiError(
            status, "bad_response", "The server answered with something MTEE cannot read."
        ) from None


def _object(value: Any, status: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApiError(status, "bad_response", _UNREADABLE)
    return value


# A chunk of 8 MiB may take longer than the default timeout on a slow link; a commit hashes the
# whole file on the server before it answers.
CHUNK_TIMEOUT_S = 180.0
COMMIT_TIMEOUT_S = 900.0
# The tag parts of a tags-only transfer are sent in chunks of this size, and an upload that the
# server keeps answering with another offset is given up after this many tries in a row.
SPLICE_CHUNK_BYTES = 8 * 1024 * 1024
_SPLICE_STALLS = 3


class RemoteClient:
    """The calls MTEE makes to a MTEE Remote server; one method per route it uses."""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = normalize_base_url(base_url)
        self._parts = urlsplit(self.base_url)
        self._token = token or None
        self._timeout = timeout
        self._open: set[http.client.HTTPConnection] = set()
        self._open_lock = threading.Lock()
        self._sent_lock = threading.Lock()
        self._uploaded_bytes = 0

    @property
    def uploaded_bytes(self) -> int:
        """The upload bytes this client has sent so far (a counter for sizes and tests)."""
        with self._sent_lock:
            return self._uploaded_bytes

    def abort(self) -> None:
        """Close the connections in use, so a call waiting for the server ends at once.

        Used when a long poll must stop (Auto pull off, sign-out, unload). The call that is
        cut raises ``NetworkError``; a later call on this client opens a new connection.
        """
        with self._open_lock:
            connections = list(self._open)
        for connection in connections:
            sock = connection.sock
            if sock is not None:
                with contextlib.suppress(OSError):
                    sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                connection.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Send one request and return ``(status, headers, body)``.

        ``json`` is encoded as the body; give it or ``body``, not both. A status of 400 or more
        raises ``ApiError``; a failure to reach the server raises ``NetworkError``.
        """
        if json is not None and body is not None:
            raise ValueError("Give either json or body to a request, not both.")
        payload = body
        sent: dict[str, str] = dict(headers or {})
        if json is not None:
            payload = _encode(json)
            sent.setdefault("Content-Type", "application/json")
        sent.setdefault("Accept", "application/json")
        if self._token is not None:
            sent["Authorization"] = f"Bearer {self._token}"
        connection = self._connection(self._timeout if timeout is None else timeout)
        self._register(connection)
        try:
            connection.request(method, self._parts.path + path, body=payload, headers=sent)
            response = connection.getresponse()
            data = response.read()
            status = response.status
            response_headers = {name.lower(): value for name, value in response.getheaders()}
        except (OSError, http.client.HTTPException) as error:
            raise self._network_error(error) from None
        finally:
            self._unregister(connection)
            connection.close()
        if status >= 400:
            error = _api_error(status, data)
            error.headers = response_headers
            raise error
        return status, response_headers, data

    def health(self) -> dict[str, Any]:
        _, _, data = self.request("GET", "/health")
        return _object(_json_body(200, data), 200)

    def login(
        self, username: str, password: str, device_name: str, device_kind: str = "desktop"
    ) -> tuple[str, str]:
        """Sign in and register a device; return ``(device_id, token)``."""
        status, _, data = self.request(
            "POST",
            "/api/v1/auth/login",
            json={
                "username": username,
                "password": password,
                "device_name": device_name,
                "device_kind": device_kind,
            },
        )
        parsed = _object(_json_body(status, data), status)
        device_id = parsed.get("device_id")
        token = parsed.get("token")
        if not isinstance(device_id, str) or not isinstance(token, str) or not token:
            raise ApiError(status, "bad_response", "The server did not return a device token.")
        return device_id, token

    def logout(self) -> None:
        """Revoke this device on the server (the token stops working)."""
        self.request("POST", "/api/v1/auth/logout")

    def devices(self) -> list[dict[str, Any]]:
        status, _, data = self.request("GET", "/api/v1/devices")
        return _list_of(_object(_json_body(status, data), status), "devices", status)

    def revoke_device(self, device_id: str) -> None:
        self.request("DELETE", f"/api/v1/devices/{quote(device_id, safe='')}")

    def roots(self) -> list[dict[str, Any]]:
        status, _, data = self.request("GET", "/api/v1/roots")
        return _list_of(_object(_json_body(status, data), status), "roots", status)

    def library_status(self) -> dict[str, Any]:
        status, _, data = self.request("GET", "/api/v1/library/status")
        return _object(_json_body(status, data), status)

    def items(
        self,
        after: str | None = None,
        limit: int = 1000,
        *,
        root_id: str | None = None,
        prefix: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Return one page of the present items and the cursor of the next page (None: last).

        ``root_id`` and ``prefix`` filter the page as the server does: ``prefix`` keeps the paths
        that start with it (end it with ``/`` for a folder).
        """
        query: dict[str, str] = {"limit": str(limit)}
        if after is not None:
            query["after"] = after
        if root_id is not None:
            query["root_id"] = root_id
        if prefix:
            query["prefix"] = prefix
        status, _, data = self.request("GET", f"/api/v1/items?{urlencode(query)}")
        parsed = _object(_json_body(status, data), status)
        items = _list_of(parsed, "items", status)
        next_cursor = parsed.get("next")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return items, next_cursor

    def all_items(
        self, *, root_id: str | None = None, prefix: str | None = None
    ) -> list[dict[str, Any]]:
        """Return every present item of the filter, following ``next`` page by page."""
        collected: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            page, cursor = self.items(cursor, root_id=root_id, prefix=prefix)
            collected.extend(page)
            if cursor is None:
                return collected
            if cursor in seen:
                # A server that repeats its cursor would loop forever: refuse it.
                raise ApiError(200, "bad_response", _UNREADABLE)
            seen.add(cursor)

    def get_item(self, item_id: str) -> dict[str, Any]:
        status, _, data = self.request("GET", f"/api/v1/items/{quote(item_id, safe='')}")
        return _object(_json_body(status, data), status)

    # -- playback of server-only tracks (plan 127.5) -----------------------------------------
    def authorization_headers(self) -> dict[str, str]:
        """The header with this device's token: sent with a stream request, never in a URL."""
        if self._token is None:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    def stream_url(self, item_id: str, level: str, codecs: Sequence[str] = ()) -> str:
        """The address of an item's stream at a level. It names no token: send the headers too."""
        return f"{self.base_url}/api/v1/items/{quote(item_id, safe='')}/stream?" + _stream_query(
            level, codecs
        )

    def prepare_stream(self, item_id: str, level: str, codecs: Sequence[str] = ()) -> bool:
        """Start the transcode of an item at a level; return True when it is ready to stream."""
        status, _, data = self.request(
            "POST",
            f"/api/v1/items/{quote(item_id, safe='')}/prepare?" + _stream_query(level, codecs),
        )
        parsed = _object(_json_body(status, data), status)
        ready = parsed.get("ready")
        if not isinstance(ready, bool):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return ready

    def cover(self, item_id: str, size: str = "m") -> bytes | None:
        """The JPEG cover of an item at ``size`` (s, m or l); None when the item has no cover."""
        try:
            _, _, data = self.request(
                "GET", f"/api/v1/items/{quote(item_id, safe='')}/cover?size={size}"
            )
        except ApiError as error:
            if error.status == 404:
                return None
            raise
        return data

    def trash_item(self, item_id: str) -> str:
        """Move an item's file to the server trash and mark the item trashed; return the trash id.

        The server keeps the file in its trash until the administrator empties it. A 404 means the
        item is not present on the server any more; the caller decides what that means.
        """
        status, _, data = self.request("POST", f"/api/v1/items/{quote(item_id, safe='')}/trash")
        parsed = _object(_json_body(status, data), status)
        trash_id = parsed.get("trash_id")
        if not isinstance(trash_id, str) or not trash_id:
            raise ApiError(status, "bad_response", _UNREADABLE)
        return trash_id

    def move_item(self, item_id: str, relative_path: str) -> dict[str, Any]:
        """Move an item to another path of its root; return the item as the server now has it."""
        status, _, data = self.request(
            "POST",
            f"/api/v1/items/{quote(item_id, safe='')}/move",
            json={"relative_path": relative_path},
        )
        parsed = _object(_json_body(status, data), status)
        return _object(parsed.get("item"), status)

    def open_upload(
        self,
        *,
        root_id: str,
        relative_path: str,
        size_bytes: int,
        sha256: str,
        base_item_id: str | None = None,
        base_revision: int | None = None,
    ) -> dict[str, Any]:
        """Open an upload of one item; with a base item, it replaces that item's file."""
        body: dict[str, Any] = {
            "purpose": "item",
            "root_id": root_id,
            "relative_path": relative_path,
            "size_bytes": size_bytes,
            "sha256": sha256,
        }
        if base_item_id is not None:
            body["base_item_id"] = base_item_id
            body["base_revision"] = base_revision
        status, _, data = self.request("POST", "/api/v1/uploads", json=body)
        parsed = _object(_json_body(status, data), status)
        if not isinstance(parsed.get("upload_id"), str):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return parsed

    def open_splice_upload(
        self,
        *,
        root_id: str,
        relative_path: str,
        size_bytes: int,
        sha256: str,
        base_item_id: str,
        base_revision: int,
        span_length: int,
        span_sha256: str,
        prefix_size: int,
    ) -> dict[str, Any]:
        """Open a tags-only replacement of an item (plan 129.2).

        ``size_bytes`` and ``sha256`` describe the FINAL file. The server expects only the tag parts
        (``size_bytes - span_length`` bytes, the answer's ``size_bytes``) and rebuilds the file with
        the audio payload it already holds; it checks the payload against ``span_length`` and
        ``span_sha256`` when the upload is committed.
        """
        body: dict[str, Any] = {
            "purpose": "item",
            "mode": "splice",
            "root_id": root_id,
            "relative_path": relative_path,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "base_item_id": base_item_id,
            "base_revision": base_revision,
            "span_length": span_length,
            "span_sha256": span_sha256,
            "prefix_size": prefix_size,
        }
        status, _, data = self.request("POST", "/api/v1/uploads", json=body)
        parsed = _object(_json_body(status, data), status)
        if not isinstance(parsed.get("upload_id"), str):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return parsed

    def replace_with_tags(
        self,
        *,
        root_id: str,
        relative_path: str,
        size_bytes: int,
        sha256: str,
        base_item_id: str,
        base_revision: int,
        span_length: int,
        span_sha256: str,
        prefix: bytes,
        suffix: bytes,
        chunk_bytes: int = SPLICE_CHUNK_BYTES,
        before_chunk: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Replace an item by sending only the bytes around the audio payload; return the new item.

        The tag parts (``prefix`` + ``suffix``) go through the resumable upload, then the server
        rebuilds the file and keeps it only when its SHA-256 is ``sha256``. A refusal raises
        ``ApiError`` with the code ``splice_refused`` (the server discarded the upload and nothing
        changed; the caller sends the whole file instead), a stale ``base_revision`` raises the
        usual ``conflict``. The upload is cancelled on any failure. ``before_chunk`` runs before
        each chunk and may raise to stop the transfer.
        """
        opened = self.open_splice_upload(
            root_id=root_id,
            relative_path=relative_path,
            size_bytes=size_bytes,
            sha256=sha256,
            base_item_id=base_item_id,
            base_revision=base_revision,
            span_length=span_length,
            span_sha256=span_sha256,
            prefix_size=len(prefix),
        )
        upload_id = str(opened["upload_id"])
        parts = prefix + suffix
        try:
            offset = 0
            stalls = 0
            while offset < len(parts):
                if before_chunk is not None:
                    before_chunk()
                data = parts[offset : offset + chunk_bytes]
                try:
                    offset = self.upload_chunk(upload_id, offset, data, len(parts))
                    stalls = 0
                except UploadOffsetError as held:
                    stalls = stalls + 1 if held.offset == offset else 0
                    if stalls > _SPLICE_STALLS:
                        raise ApiError(
                            0, "stalled", "The server keeps refusing the bytes of this upload."
                        ) from None
                    offset = held.offset
            body = self.commit_upload(upload_id)
        except BaseException:
            with contextlib.suppress(ApiError, NetworkError):
                self.cancel_upload(upload_id)
            raise
        return _object(body.get("item"), 200)

    def upload_status(self, upload_id: str) -> dict[str, Any]:
        status, _, data = self.request("GET", _upload_path(upload_id))
        return _object(_json_body(status, data), status)

    def upload_chunk(self, upload_id: str, start: int, data: bytes, total: int) -> int:
        """Send ``data`` at offset ``start``; return the bytes the server holds after it.

        Raises ``UploadOffsetError`` when the server holds other bytes than ``start`` (HTTP 416).
        """
        if not data:
            raise ValueError("An upload chunk must not be empty.")
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Range": f"bytes {start}-{start + len(data) - 1}/{total}",
        }
        try:
            status, _, body = self.request(
                "PUT", _upload_path(upload_id), body=data, headers=headers, timeout=CHUNK_TIMEOUT_S
            )
        except ApiError as error:
            if error.status != 416:
                raise
            offset = _offset_header(error.headers)
            if offset is None:
                offset = _received(self.upload_status(upload_id))
            raise UploadOffsetError(offset) from None
        with self._sent_lock:
            self._uploaded_bytes += len(data)
        return _received(_object(_json_body(status, body), status))

    def commit_upload(self, upload_id: str, relative_path: str | None = None) -> dict[str, Any]:
        """Verify and place the upload; return ``{"item": ...}`` as the server answers."""
        body = None if relative_path is None else {"relative_path": relative_path}
        status, _, data = self.request(
            "POST", f"{_upload_path(upload_id)}/commit", json=body, timeout=COMMIT_TIMEOUT_S
        )
        return _object(_json_body(status, data), status)

    def cancel_upload(self, upload_id: str) -> None:
        """Drop an upload that is not committed yet, and the bytes it holds on the server."""
        self.request("DELETE", _upload_path(upload_id))

    # -- change journal, cursor and downloads (plan 126.4) -----------------------------------
    def changes(self, since: int, limit: int = 500, wait: float = 0) -> ChangePage:
        """Return the journal entries after ``since``; with ``wait`` the server holds the answer.

        ``wait`` (seconds, 0 to 30) makes the server answer as soon as an entry newer than
        ``since`` exists, or when the wait ends with none.
        """
        query: dict[str, str] = {"since": str(since), "limit": str(limit)}
        timeout = self._timeout
        if wait > 0:
            query["wait"] = f"{wait:g}"
            timeout = wait + self._timeout
        status, _, data = self.request(
            "GET", f"/api/v1/changes?{urlencode(query)}", timeout=timeout
        )
        parsed = _object(_json_body(status, data), status)
        raw = _list_of(parsed, "changes", status)
        next_seq = parsed.get("next")
        more = parsed.get("more")
        if not _is_count(next_seq) or not isinstance(more, bool):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return ChangePage(tuple(raw), int(next_seq), more)

    def get_cursor(self) -> int:
        """The sequence number this device has read up to on the server (0 when none)."""
        status, _, data = self.request("GET", "/api/v1/devices/me/cursor")
        seq = _object(_json_body(status, data), status).get("seq")
        if not _is_count(seq):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return int(seq)

    def put_cursor(self, seq: int) -> None:
        """Store the sequence number this device has read up to on the server."""
        self.request("PUT", "/api/v1/devices/me/cursor", json={"seq": seq})

    def download(
        self,
        item_id: str,
        target: Path,
        *,
        expected_sha256: str,
        chunk: int = DOWNLOAD_CHUNK_BYTES,
        job: _Cancellable | None = None,
    ) -> Path:
        """Download the original of an item to ``target``, verified against ``expected_sha256``.

        The bytes go to ``target + ".part"``; a part left by an earlier run is resumed with a
        ``Range`` request. A complete download is hashed and renamed to ``target``. A hash that
        does not match deletes the part and raises ``DownloadError``. Runs on a job thread.
        """
        return self._download(
            f"/api/v1/items/{quote(item_id, safe='')}/file",
            target,
            expected_sha256=expected_sha256,
            chunk=chunk,
            job=job,
        )

    def _download(
        self,
        path: str,
        target: Path,
        *,
        expected_sha256: str,
        chunk: int = DOWNLOAD_CHUNK_BYTES,
        job: _Cancellable | None = None,
    ) -> Path:
        """The download of any file route (an item, a backup): see ``download``."""
        destination = Path(target)
        part = destination.with_name(destination.name + ".part")
        destination.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(2):
            offset = part.stat().st_size if part.is_file() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            with self._stream(path, headers) as response:
                if response.status == _RANGE_NOT_SATISFIABLE and offset > 0:
                    # The part is not a prefix of the file any more: start it again.
                    part.unlink(missing_ok=True)
                    continue
                if response.status >= 400:
                    raise _api_error(response.status, self._read_stream(response))
                if response.status == 200:
                    mode = "wb"  # the server sent the whole file, whatever was asked
                elif response.status == 206:
                    mode = "ab"
                else:
                    raise ApiError(response.status, "bad_response", _UNREADABLE)
                with open(part, mode) as handle:
                    while True:
                        if job is not None:
                            job.raise_if_cancelled()
                        data = self._read_stream(response, chunk)
                        if not data:
                            break
                        handle.write(data)
            break
        if _sha256_of(part) != expected_sha256.lower():
            part.unlink(missing_ok=True)
            raise DownloadError(
                "A downloaded file did not match the SHA-256 the server reported, so it was "
                "discarded. Try again."
            )
        os.replace(part, destination)
        return destination

    # -- database backups (plan 126.8) --------------------------------------------------------
    def open_backup_upload(
        self, *, size_bytes: int, sha256: str, kind: str, label: str | None = None
    ) -> dict[str, Any]:
        """Open an upload of a database backup; ``kind`` is ``manual`` or ``automatic``.

        The bytes then go through ``upload_chunk`` and ``commit_upload``, as for an item.
        """
        body: dict[str, Any] = {
            "purpose": "backup",
            "size_bytes": size_bytes,
            "sha256": sha256,
            "kind": kind,
        }
        if label is not None:
            body["label"] = label
        status, _, data = self.request("POST", "/api/v1/uploads", json=body)
        parsed = _object(_json_body(status, data), status)
        if not isinstance(parsed.get("upload_id"), str):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return parsed

    def backups(self) -> list[dict[str, Any]]:
        """The present backups of the account, newest first."""
        status, _, data = self.request("GET", "/api/v1/backups")
        return _list_of(_object(_json_body(status, data), status), "backups", status)

    def download_backup(
        self,
        backup_id: str,
        target: Path,
        *,
        expected_sha256: str,
        chunk: int = DOWNLOAD_CHUNK_BYTES,
        job: _Cancellable | None = None,
    ) -> Path:
        """Download a backup to ``target``, verified and resumed like ``download``."""
        return self._download(
            f"/api/v1/backups/{quote(backup_id, safe='')}/file",
            target,
            expected_sha256=expected_sha256,
            chunk=chunk,
            job=job,
        )

    def delete_backup(self, backup_id: str) -> None:
        """Move a backup to the server's trash (it leaves the list at once)."""
        self.request("DELETE", f"/api/v1/backups/{quote(backup_id, safe='')}")

    def backup_settings(self) -> dict[str, int]:
        """How many daily and weekly backups the account keeps: ``{"daily", "weekly"}``."""
        status, _, data = self.request("GET", "/api/v1/settings/backups")
        return self._backup_counts(_object(_json_body(status, data), status), status)

    def put_backup_settings(self, daily: int, weekly: int) -> dict[str, int]:
        """Set how many daily (0 to 365) and weekly (0 to 104) backups are kept."""
        status, _, data = self.request(
            "PUT", "/api/v1/settings/backups", json={"daily": daily, "weekly": weekly}
        )
        parsed = _object(_json_body(status, data), status)
        return self._backup_counts(parsed, status)

    @staticmethod
    def _backup_counts(parsed: dict[str, Any], status: int) -> dict[str, int]:
        daily = parsed.get("daily")
        weekly = parsed.get("weekly")
        if not _is_count(daily) or not _is_count(weekly):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return {"daily": int(daily), "weekly": int(weekly)}

    # -- records (plan 126.7): play log, playlists, track data, synced settings ---------------
    def post_play_events(self, events: Sequence[dict[str, Any]]) -> dict[str, Any]:
        """Send a batch of play events of this device; the server skips the ones it has."""
        status, _, data = self.request(
            "POST", "/api/v1/records/play-events", json={"events": list(events)}
        )
        return _object(_json_body(status, data), status)

    def play_events(self, since: int, limit: int = 500) -> PlayEventPage:
        """The play events stored after the sequence number ``since``, oldest first."""
        query = urlencode({"since": str(since), "limit": str(limit)})
        status, _, data = self.request("GET", f"/api/v1/records/play-events?{query}")
        parsed = _object(_json_body(status, data), status)
        events = _list_of(parsed, "events", status)
        next_seq = parsed.get("next")
        more = parsed.get("more")
        if not _is_count(next_seq) or not isinstance(more, bool):
            raise ApiError(status, "bad_response", _UNREADABLE)
        return PlayEventPage(tuple(events), int(next_seq), more)

    def playlists(self) -> list[dict[str, Any]]:
        """Every playlist of the account without its entries; deleted ones are included."""
        status, _, data = self.request("GET", "/api/v1/records/playlists")
        return _list_of(_object(_json_body(status, data), status), "playlists", status)

    def playlist(self, playlist_id: str) -> dict[str, Any]:
        """One playlist with its entries."""
        status, _, data = self.request("GET", _playlist_path(playlist_id))
        return _object(_json_body(status, data), status)

    def put_playlist(
        self,
        playlist_id: str,
        name: str,
        entries: Sequence[dict[str, Any]],
        base_revision: int | None,
    ) -> dict[str, Any]:
        """Create or replace a whole playlist; ``base_revision`` None creates it.

        A 409 (``conflict``) means the playlist moved on since ``base_revision``.
        """
        body: dict[str, Any] = {"name": name, "entries": list(entries)}
        if base_revision is not None:
            body["base_revision"] = base_revision
        status, _, data = self.request("PUT", _playlist_path(playlist_id), json=body)
        return _object(_json_body(status, data), status)

    def delete_playlist(self, playlist_id: str, base_revision: int) -> dict[str, Any]:
        """Mark a playlist deleted on the server; ``base_revision`` must be its revision."""
        query = urlencode({"base_revision": str(base_revision)})
        status, _, data = self.request("DELETE", f"{_playlist_path(playlist_id)}?{query}")
        return _object(_json_body(status, data), status)

    def track_data(self, item_id: str) -> dict[str, Any]:
        """The layers the server holds for an item: ``analysis``, ``loudness``, ``corrections``."""
        status, _, data = self.request("GET", _track_data_path(item_id))
        parsed = _object(_json_body(status, data), status)
        return _object(parsed.get("layers"), status)

    def put_track_data(self, item_id: str, layers: dict[str, Any]) -> dict[str, Any]:
        """Set the given layers of an item; the others keep their value."""
        status, _, data = self.request("PUT", _track_data_path(item_id), json=layers)
        parsed = _object(_json_body(status, data), status)
        return _object(parsed.get("layers"), status)

    def records_settings(self) -> dict[str, Any]:
        """Every synced setting of the account, as ``key: value``."""
        status, _, data = self.request("GET", "/api/v1/records/settings")
        parsed = _object(_json_body(status, data), status)
        return _object(parsed.get("settings"), status)

    def put_records_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        """Set the given synced settings; the server answers with all of them."""
        status, _, data = self.request("PUT", "/api/v1/records/settings", json=values)
        parsed = _object(_json_body(status, data), status)
        return _object(parsed.get("settings"), status)

    @contextlib.contextmanager
    def _stream(self, path: str, headers: dict[str, str]) -> Iterator[http.client.HTTPResponse]:
        """Open a GET whose body is read by the caller, in chunks."""
        sent = dict(headers)
        sent.setdefault("Accept", "application/octet-stream")
        if self._token is not None:
            sent["Authorization"] = f"Bearer {self._token}"
        connection = self._connection(DOWNLOAD_TIMEOUT_S)
        self._register(connection)
        try:
            try:
                connection.request("GET", self._parts.path + path, headers=sent)
                response = connection.getresponse()
            except (OSError, http.client.HTTPException) as error:
                raise self._network_error(error) from None
            # Only the request is wrapped: an error of the caller's own file while it writes the
            # body is not a network error.
            yield response
        finally:
            self._unregister(connection)
            connection.close()

    def _read_stream(self, response: http.client.HTTPResponse, amount: int = -1) -> bytes:
        try:
            return response.read(amount) if amount > 0 else response.read()
        except (OSError, http.client.HTTPException) as error:
            raise self._network_error(error) from None

    def _register(self, connection: http.client.HTTPConnection) -> None:
        with self._open_lock:
            self._open.add(connection)

    def _unregister(self, connection: http.client.HTTPConnection) -> None:
        with self._open_lock:
            self._open.discard(connection)

    def _network_error(self, error: BaseException) -> NetworkError:
        """The readable error for a connection that failed: TLS, timeout or unreachable."""
        if isinstance(error, ssl.SSLError):
            return NetworkError(
                f"The secure connection to {self.base_url} failed. Check the server address "
                "and its certificate."
            )
        if isinstance(error, TimeoutError):
            return NetworkError(
                f"The server at {self.base_url} did not answer in time. Check your connection "
                "and try again."
            )
        return NetworkError(
            f"The server at {self.base_url} cannot be reached. Check the address and your "
            "connection."
        )

    def _connection(self, timeout: float) -> http.client.HTTPConnection:
        host = self._parts.hostname or ""
        if self._parts.scheme == "https":
            return http.client.HTTPSConnection(
                host, self._parts.port, timeout=timeout, context=ssl.create_default_context()
            )
        return http.client.HTTPConnection(host, self._parts.port, timeout=timeout)


def _stream_query(level: str, codecs: Sequence[str]) -> str:
    query = f"level={quote(level, safe='')}"
    if codecs:
        query += f"&codecs={quote(','.join(codecs), safe=',')}"
    return query


def _playlist_path(playlist_id: str) -> str:
    return f"/api/v1/records/playlists/{quote(playlist_id, safe='')}"


def _track_data_path(item_id: str) -> str:
    return f"/api/v1/records/track-data/{quote(item_id, safe='')}"


def _upload_path(upload_id: str) -> str:
    return f"/api/v1/uploads/{quote(upload_id, safe='')}"


def _offset_header(headers: dict[str, str]) -> int | None:
    raw = headers.get("upload-offset", "")
    return int(raw) if raw.isdigit() else None


def _received(parsed: dict[str, Any]) -> int:
    received = parsed.get("received_bytes")
    if not isinstance(received, int) or isinstance(received, bool) or received < 0:
        raise ApiError(200, "bad_response", _UNREADABLE)
    return received


def _is_count(value: Any) -> TypeGuard[int]:
    """True for a whole number zero or more (a sequence number, a count)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _encode(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _list_of(parsed: dict[str, Any], key: str, status: int) -> list[dict[str, Any]]:
    items = parsed.get(key)
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ApiError(status, "bad_response", _UNREADABLE)
    return items

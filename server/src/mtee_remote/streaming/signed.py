"""Signed stream URLs for players that cannot send the device token header (plan 127.2).

A token is `base64url(json(claims))` + "." + `base64url(HMAC-SHA256(secret, first part))`, with
no padding. The claims are `i` (item id), `u` (user id), `d` (device id), `l` (level), `c` (sorted
codecs) and `e` (expiry, Unix seconds). The secret is 32 random bytes in `<data>/stream-secret.bin`,
created on first use and kept in memory after its first read.

Verifying a token checks the signature and the expiry only. The route checks that the user and
the device still exist and are allowed, and that the item is theirs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtee_remote import clock

SECRET_BYTES = 32


@dataclass(frozen=True, slots=True)
class Claims:
    item_id: str
    user_id: str
    device_id: str
    level: str
    codecs: frozenset[str]
    expires: int


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SignedUrls:
    """Signs and verifies stream tokens with the server secret."""

    def __init__(self, secret_path: Path) -> None:
        self._path = secret_path
        self._secret: bytes | None = None
        self._lock = threading.Lock()

    def secret(self) -> bytes:
        """Return the secret, creating the file on first use (worker thread)."""
        with self._lock:
            if self._secret is None:
                self._secret = _read_or_create(self._path)
            return self._secret

    def sign(self, claims: Claims) -> str:
        payload: dict[str, Any] = {
            "i": claims.item_id,
            "u": claims.user_id,
            "d": claims.device_id,
            "l": claims.level,
            "c": sorted(claims.codecs),
            "e": claims.expires,
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        part = _b64(body)
        return f"{part}.{_b64(self._mac(part))}"

    def verify(self, token: str) -> Claims | None:
        """Return the claims of a valid, unexpired token, or None (worker thread)."""
        part, dot, given = token.partition(".")
        if not dot or not part or not given or "." in given:
            return None
        expected = _b64(self._mac(part)).encode("ascii")
        if not hmac.compare_digest(expected, given.encode("ascii", errors="replace")):
            return None
        try:
            payload: Any = json.loads(_unb64(part))
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None
        claims = _claims_from(payload)
        if claims is None or claims.expires <= int(clock.utc_now().timestamp()):
            return None
        return claims

    def _mac(self, part: str) -> bytes:
        return hmac.new(self.secret(), part.encode("ascii"), hashlib.sha256).digest()


def _claims_from(payload: dict[str, Any]) -> Claims | None:
    item_id = payload.get("i")
    user_id = payload.get("u")
    device_id = payload.get("d")
    level = payload.get("l")
    codecs = payload.get("c")
    expires = payload.get("e")
    if not (
        isinstance(item_id, str)
        and isinstance(user_id, str)
        and isinstance(device_id, str)
        and isinstance(level, str)
    ):
        return None
    if not isinstance(codecs, list) or not all(isinstance(code, str) for code in codecs):
        return None
    if isinstance(expires, bool) or not isinstance(expires, int):
        return None
    return Claims(
        item_id=item_id,
        user_id=user_id,
        device_id=device_id,
        level=level,
        codecs=frozenset(codecs),
        expires=expires,
    )


def _read_or_create(path: Path) -> bytes:
    """Return the secret in `path`, creating it with owner-only permissions if missing."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        data = secrets.token_bytes(SECRET_BYTES)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # Another thread or process created it first: use its secret.
            return path.read_bytes()
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return data
    if len(data) != SECRET_BYTES:
        raise RuntimeError(f"The stream secret in {path} is damaged; delete it to make a new one.")
    return data

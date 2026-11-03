"""Streaming settings: the server's (admin) and each user's default levels (plan 127.3).

Server settings live in `server_settings` under `streaming.<name>`; the API and this module
use the short names (`max_transcodes`, ...). A user's settings live in `user_settings` under
the key `streaming`, as one JSON object.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mtee_remote.db import Transaction
from mtee_remote.errors import ApiError
from mtee_remote.streaming.types import LEVELS

SERVER_PREFIX = "streaming."
USER_KEY = "streaming"

SERVER_DEFAULTS: dict[str, Any] = {
    "max_transcodes": 2,
    "cache_limit_gb": 20,
    "wav_to_flac": True,
    "lossless_cap": None,
}
USER_DEFAULTS: dict[str, str] = {
    "default_level_wifi": "lossless",
    "default_level_mobile": "320",
}

_MAX_TRANSCODES = (1, 8)
_CACHE_LIMIT_GB = (1, 1000)
_CAP_SAMPLE_RATE = (8000, 384000)
_CAP_BIT_DEPTHS = (16, 24, 32)


# -- server ----------------------------------------------------------------------------


def server_streaming_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    """The server's streaming settings, the defaults for every key that is not stored."""
    result = dict(SERVER_DEFAULTS)
    for name in SERVER_DEFAULTS:
        row = conn.execute(
            "SELECT value_json FROM server_settings WHERE key = ?", (SERVER_PREFIX + name,)
        ).fetchone()
        if row is not None:
            result[name] = json.loads(row[0])
    return result


def put_server_streaming_settings(tx: Transaction, values: dict[str, Any]) -> dict[str, Any]:
    """Validate and store the given settings (a partial object); return the full settings.

    Raises `bad_request` naming the first key that is unknown or has a value out of range.
    """
    checked = _validated_server(values)
    for name, value in checked.items():
        tx.conn.execute(
            "INSERT INTO server_settings(key, value_json) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
            (SERVER_PREFIX + name, json.dumps(value, separators=(",", ":"))),
        )
    return server_streaming_settings(tx.conn)


def _validated_server(values: dict[str, Any]) -> dict[str, Any]:
    for key in values:
        if key not in SERVER_DEFAULTS:
            raise ApiError("bad_request", f"Unknown setting '{key}'.")
    checked: dict[str, Any] = {}
    if "max_transcodes" in values:
        checked["max_transcodes"] = _whole_number(values, "max_transcodes", _MAX_TRANSCODES)
    if "cache_limit_gb" in values:
        checked["cache_limit_gb"] = _whole_number(values, "cache_limit_gb", _CACHE_LIMIT_GB)
    if "wav_to_flac" in values:
        checked["wav_to_flac"] = _boolean(values, "wav_to_flac")
    if "lossless_cap" in values:
        checked["lossless_cap"] = _lossless_cap(values["lossless_cap"])
    return checked


def _whole_number(values: dict[str, Any], key: str, bounds: tuple[int, int]) -> int:
    value = values[key]
    low, high = bounds
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ApiError(
            "bad_request", f"The field '{key}' must be a whole number from {low} to {high}."
        )
    return value


def _boolean(values: dict[str, Any], key: str) -> bool:
    value = values[key]
    if not isinstance(value, bool):
        raise ApiError("bad_request", f"The field '{key}' must be true or false.")
    return value


def _lossless_cap(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"sample_rate", "bit_depth"}:
        raise ApiError(
            "bad_request",
            "The field 'lossless_cap' must be null or an object with 'sample_rate' and"
            " 'bit_depth'.",
        )
    rate = value["sample_rate"]
    low, high = _CAP_SAMPLE_RATE
    if isinstance(rate, bool) or not isinstance(rate, int) or not low <= rate <= high:
        raise ApiError(
            "bad_request",
            f"The field 'lossless_cap.sample_rate' must be a whole number from {low} to {high}.",
        )
    depth = value["bit_depth"]
    if isinstance(depth, bool) or depth not in _CAP_BIT_DEPTHS:
        allowed = ", ".join(str(depth_bits) for depth_bits in _CAP_BIT_DEPTHS)
        raise ApiError(
            "bad_request", f"The field 'lossless_cap.bit_depth' must be one of {allowed}."
        )
    return {"sample_rate": rate, "bit_depth": depth}


# -- per user --------------------------------------------------------------------------


def user_streaming_settings(conn: sqlite3.Connection, user_id: str) -> dict[str, str]:
    """The user's default levels for Wi-Fi and mobile data, defaults where not stored."""
    row = conn.execute(
        "SELECT value_json FROM user_settings WHERE user_id = ? AND key = ?",
        (user_id, USER_KEY),
    ).fetchone()
    result = dict(USER_DEFAULTS)
    if row is not None:
        stored: dict[str, Any] = json.loads(row[0])
        for name in USER_DEFAULTS:
            if name in stored:
                result[name] = stored[name]
    return result


def put_user_streaming_settings(
    tx: Transaction, user_id: str, values: dict[str, Any]
) -> dict[str, str]:
    """Validate and store the given default levels (a partial object); return the full set."""
    checked = _validated_user(values)
    current = user_streaming_settings(tx.conn, user_id)
    current.update(checked)
    tx.conn.execute(
        "INSERT INTO user_settings(user_id, key, value_json) VALUES (?,?,?)"
        " ON CONFLICT(user_id, key) DO UPDATE SET value_json = excluded.value_json",
        (user_id, USER_KEY, json.dumps(current, separators=(",", ":"))),
    )
    return current


def _validated_user(values: dict[str, Any]) -> dict[str, str]:
    checked: dict[str, str] = {}
    for key, value in values.items():
        if key not in USER_DEFAULTS:
            raise ApiError("bad_request", f"Unknown setting '{key}'.")
        if not isinstance(value, str) or value not in LEVELS:
            raise ApiError(
                "bad_request",
                f"The field '{key}' must be one of: {', '.join(LEVELS)}.",
            )
        checked[key] = value
    return checked

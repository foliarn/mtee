"""Shared fixtures for the server tests."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from mtee_remote import clock
from mtee_remote.app import create_app
from mtee_remote.config import Settings
from mtee_remote.ids import new_id
from mtee_remote.security import hash_token, new_token

REPO_ROOT = Path(__file__).resolve().parents[2]

MakeUser = Callable[..., dict[str, Any]]
MakeDevice = Callable[..., dict[str, Any]]


@pytest.fixture(scope="session", autouse=True)
def _ffmpeg_from_vendor() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Use the repository's pinned ffmpeg when none is installed."""
    vendored = REPO_ROOT / "vendor" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if (
        shutil.which("ffmpeg") is None
        and not os.environ.get("MTEE_REMOTE_FFMPEG")
        and vendored.is_file()
    ):
        os.environ["MTEE_REMOTE_FFMPEG"] = str(vendored)
        yield
        os.environ.pop("MTEE_REMOTE_FFMPEG", None)
    else:
        yield


@pytest.fixture(scope="session", autouse=True)
def _ffprobe_from_vendor() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Use the repository's pinned ffprobe when none is installed."""
    vendored = REPO_ROOT / "vendor" / "ffmpeg" / "bin" / "ffprobe.exe"
    if (
        shutil.which("ffprobe") is None
        and not os.environ.get("MTEE_REMOTE_FFPROBE")
        and vendored.is_file()
    ):
        os.environ["MTEE_REMOTE_FFPROBE"] = str(vendored)
        yield
        os.environ.pop("MTEE_REMOTE_FFPROBE", None)
    else:
        yield


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    return Settings(data_dir=data_dir, music_dir=music_dir)


@pytest.fixture
def app(settings: Settings) -> Starlette:
    return create_app(settings)


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _make_user(
    app: Starlette,
    username: str = "alice",
    *,
    is_admin: bool = False,
    quota_bytes: int | None = None,
) -> dict[str, Any]:
    """Insert a user row directly and create the library folder."""
    user_id = new_id()
    settings: Settings = app.state.settings
    (settings.music_dir / username).mkdir(parents=True, exist_ok=True)
    with app.state.db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO users(user_id, username, password_hash, is_admin, disabled,"
            " quota_bytes, library_dir, created_at_utc) VALUES (?,?,?,?,?,?,?,?)",
            (
                user_id,
                username,
                "!test",
                int(is_admin),
                0,
                quota_bytes,
                username,
                clock.to_iso(clock.utc_now()),
            ),
        )
    return {"user_id": user_id, "username": username, "library_dir": username}


def _make_device(
    app: Starlette, user: dict[str, Any], *, name: str = "test", kind: str = "desktop"
) -> dict[str, Any]:
    """Insert a device for `user` with a fresh token."""
    device_id = new_id()
    token = new_token()
    with app.state.db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO devices(device_id, user_id, name, kind, token_hash, created_at_utc)"
            " VALUES (?,?,?,?,?,?)",
            (
                device_id,
                user["user_id"],
                name,
                kind,
                hash_token(token),
                clock.to_iso(clock.utc_now()),
            ),
        )
    return {
        "device_id": device_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
def make_user() -> MakeUser:
    return _make_user


@pytest.fixture
def make_device() -> MakeDevice:
    return _make_device

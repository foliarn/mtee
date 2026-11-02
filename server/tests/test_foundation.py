"""Small modules: settings, ids, clock, errors, request helpers, audio helper, command line."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from mtee.services.metadata_reader import MetadataReader
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from helpers import make_audio
from mtee_remote import cli, clock
from mtee_remote.config import Settings
from mtee_remote.errors import ApiError
from mtee_remote.http import get_bool, get_int, get_str, json_ok, read_json
from mtee_remote.ids import new_id


def test_settings_from_env() -> None:
    settings = Settings.from_env(
        {
            "MTEE_REMOTE_DATA": "/data",
            "MTEE_REMOTE_MUSIC": "/music",
            "MTEE_REMOTE_PUBLIC_URL": "https://music.example.org",
            "MTEE_REMOTE_SCAN_INTERVAL": "60",
            "MTEE_REMOTE_TRUSTED_PROXIES": "10.0.0.0/8",
        }
    )
    assert settings == Settings(
        data_dir=Path("/data"),
        music_dir=Path("/music"),
        public_url="https://music.example.org",
        scan_interval_s=60,
        trusted_proxies="10.0.0.0/8",
    )


def test_settings_defaults() -> None:
    settings = Settings.from_env({"MTEE_REMOTE_DATA": "/d", "MTEE_REMOTE_MUSIC": "/m"})
    assert settings.public_url is None
    assert settings.scan_interval_s == 0
    assert settings.trusted_proxies == "127.0.0.1"


@pytest.mark.parametrize("missing", ["MTEE_REMOTE_DATA", "MTEE_REMOTE_MUSIC"])
def test_settings_missing_required(missing: str) -> None:
    env = {"MTEE_REMOTE_DATA": "/d", "MTEE_REMOTE_MUSIC": "/m"}
    del env[missing]
    with pytest.raises(ValueError, match=missing):
        Settings.from_env(env)


def test_settings_bad_interval() -> None:
    env = {"MTEE_REMOTE_DATA": "/d", "MTEE_REMOTE_MUSIC": "/m", "MTEE_REMOTE_SCAN_INTERVAL": "x"}
    with pytest.raises(ValueError, match="MTEE_REMOTE_SCAN_INTERVAL"):
        Settings.from_env(env)


def test_new_id_is_32_hex_characters() -> None:
    value = new_id()
    assert re.fullmatch(r"[0-9a-f]{32}", value)
    assert new_id() != value


def test_clock_format() -> None:
    moment = datetime(2026, 10, 31, 7, 18, 24, 123456, tzinfo=UTC)
    assert clock.to_iso(moment) == "2026-10-31T07:18:24.123456Z"
    paris = moment.astimezone(timezone(timedelta(hours=1)))
    assert clock.to_iso(paris) == "2026-10-31T07:18:24.123456Z"
    assert clock.utc_now().tzinfo is not None
    with pytest.raises(ValueError):
        clock.to_iso(datetime(2026, 1, 1))


async def _echo(request: Request) -> JSONResponse:
    body = await read_json(request)
    return json_ok(
        {
            "name": get_str(body, "name", max_len=5),
            "note": get_str(body, "note", required=False),
            "n": get_int(body, "n", minimum=1),
            "m": get_int(body, "m", required=False),
            "flag": get_bool(body, "flag", True),
        },
        status=201,
    )


@pytest.fixture
def echo_client(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> Any:
    app.router.routes.append(Route("/api/v1/_echo", _echo, methods=["POST"]))
    device = make_device(app, make_user(app, "alice"))
    with TestClient(app) as client:
        client.headers.update(device["headers"])
        yield client


def test_http_helpers_accept_good_input(echo_client: TestClient) -> None:
    response = echo_client.post("/api/v1/_echo", json={"name": "abc", "n": 3, "flag": False})
    assert response.status_code == 201
    assert response.json() == {"name": "abc", "note": None, "n": 3, "m": None, "flag": False}


@pytest.mark.parametrize(
    ("body", "word"),
    [
        ({"n": 1}, "name"),
        ({"name": "", "n": 1}, "name"),
        ({"name": "toolong", "n": 1}, "name"),
        ({"name": 4, "n": 1}, "name"),
        ({"name": "a"}, "n"),
        ({"name": "a", "n": "1"}, "n"),
        ({"name": "a", "n": True}, "n"),
        ({"name": "a", "n": 0}, "n"),
        ({"name": "a", "n": 1, "m": 1.5}, "m"),
        ({"name": "a", "n": 1, "flag": "yes"}, "flag"),
    ],
)
def test_http_helpers_reject_bad_input(
    echo_client: TestClient, body: dict[str, Any], word: str
) -> None:
    response = echo_client.post("/api/v1/_echo", json=body)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "bad_request"
    assert f"'{word}'" in error["message"]


@pytest.mark.parametrize("raw", [b"", b"nope", b"[1]", b'"text"', b"\xff\xfe"])
def test_read_json_rejects_non_objects(echo_client: TestClient, raw: bytes) -> None:
    response = echo_client.post("/api/v1/_echo", content=raw)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_starlette_errors_use_the_error_shape(echo_client: TestClient) -> None:
    missing = echo_client.get("/api/v1/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    wrong_method = echo_client.get("/api/v1/_echo")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "bad_request"
    assert "POST" in wrong_method.headers["allow"]


def test_api_error_handler(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> None:
    async def boom(request: Request) -> JSONResponse:
        raise ApiError("path_taken", "That path is taken.")

    app.router.routes.append(Route("/api/v1/_boom", boom))
    device = make_device(app, make_user(app, "alice"))
    with TestClient(app) as client:
        response = client.get("/api/v1/_boom", headers=device["headers"])
    assert response.status_code == 409
    assert response.json() == {"error": {"code": "path_taken", "message": "That path is taken."}}


def test_app_creates_its_data_folders(settings: Settings, app: Starlette) -> None:
    for name in ("db-backups", "uploads", "trash", "backups"):
        assert (settings.data_dir / name).is_dir()
    assert (settings.data_dir / "mtee-remote.db").is_file()
    assert app.state.settings is settings
    assert app.state.db.on_commit == app.state.notifier.notify


@pytest.mark.parametrize("fmt", ["flac", "mp3", "wav", "m4a", "ogg", "opus", "aiff"])
def test_make_audio_and_mtee_reader(tmp_path: Path, fmt: str) -> None:
    path = make_audio(tmp_path / f"tone.{fmt}", fmt, seconds=0.5, title="Tone")
    assert path.stat().st_size > 0
    snapshot = MetadataReader().read(path)
    assert snapshot.status == "readable"
    if fmt != "wav":  # WAV titles are RIFF INFO chunks, which MTEE's reader does not read
        assert snapshot.title == ("Tone",)
    assert snapshot.technical.duration_us == pytest.approx(500_000, abs=150_000)


def test_cli_serve_needs_its_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MTEE_REMOTE_DATA", raising=False)
    assert cli.main(["serve"]) == 2
    assert "MTEE_REMOTE_DATA" in capsys.readouterr().err

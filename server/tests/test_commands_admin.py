"""`mtee-remote admin ...`: the JSON commands of the setup TUI."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from mtee_remote import cli
from mtee_remote.app import create_app
from mtee_remote.config import Settings

GIB = 1024**3


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    music = tmp_path / "music"
    music.mkdir()
    monkeypatch.setenv("MTEE_REMOTE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("MTEE_REMOTE_MUSIC", str(music))
    monkeypatch.delenv("MTEE_REMOTE_ADMIN_PASSWORD", raising=False)
    return Settings.from_env()


def admin(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    stdin: str = "",
) -> tuple[int, dict[str, Any]]:
    """Run `mtee-remote admin <args>` and return its exit code and its JSON."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = cli.main(["admin", *args])
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_create_list_and_sign_in_with_a_password_from_stdin(
    env: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, created = admin(
        capsys, monkeypatch, "user-create", "--username", "Boss", "--admin",
        "--password-stdin", stdin="a long password\n",
    )  # fmt: skip
    assert code == 0
    assert created["user"]["username"] == "boss"
    assert created["user"]["is_admin"] is True

    code, listed = admin(capsys, monkeypatch, "users")
    assert code == 0
    (user,) = listed["users"]
    assert (user["username"], user["devices"], user["used_bytes"]) == ("boss", 0, 0)
    assert "password_hash" not in user

    with TestClient(create_app(Settings.from_env())) as client:
        body = {"username": "boss", "device_name": "pc", "device_kind": "desktop"}
        signed = client.post("/api/v1/auth/login", json={**body, "password": "a long password"})
        assert signed.status_code == 201


def test_a_short_password_is_refused_in_json(
    env: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, answer = admin(
        capsys, monkeypatch, "user-create", "--username", "ana", "--password-stdin", stdin="x\n"
    )
    assert code == 1
    assert "error" in answer and "password" in answer["error"].lower()


def test_quota_disabled_admin_and_the_last_admin_is_kept(
    env: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, flags in (("boss", ["--admin"]), ("ana", [])):
        admin(
            capsys, monkeypatch, "user-create", "--username", name, *flags,
            "--password-stdin", stdin="a long password\n",
        )  # fmt: skip

    code, changed = admin(
        capsys, monkeypatch, "user-set", "--username", "ana", "--quota-gb", "2",
        "--disabled", "yes",
    )  # fmt: skip
    assert code == 0
    assert changed["user"]["quota_bytes"] == 2 * GIB
    assert changed["user"]["disabled"] is True
    code, changed = admin(
        capsys, monkeypatch, "user-set", "--username", "ana", "--quota-gb", "none"
    )
    assert changed["user"]["quota_bytes"] is None

    code, refused = admin(capsys, monkeypatch, "user-set", "--username", "boss", "--admin", "no")
    assert code == 1
    assert "last active administrator" in refused["error"]
    code, refused = admin(capsys, monkeypatch, "user-set", "--username", "nobody", "--admin", "no")
    assert code == 1 and "no account named nobody" in refused["error"]


def test_a_new_password_signs_the_devices_out(
    env: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    admin(
        capsys, monkeypatch, "user-create", "--username", "ana", "--password-stdin",
        stdin="a long password\n",
    )  # fmt: skip
    with TestClient(create_app(Settings.from_env())) as client:
        body = {"username": "ana", "device_name": "pc", "device_kind": "desktop"}
        client.post("/api/v1/auth/login", json={**body, "password": "a long password"})

    code, devices = admin(capsys, monkeypatch, "devices", "--username", "ana")
    assert code == 0
    (device,) = devices["devices"]
    assert device["active"] is True and device["name"] == "pc"

    code, answer = admin(
        capsys, monkeypatch, "user-password", "--username", "ana", "--password-stdin",
        stdin="another long password\n",
    )  # fmt: skip
    assert code == 0 and answer["signed_out"] == 1
    code, devices = admin(capsys, monkeypatch, "devices")
    assert devices["devices"][0]["active"] is False


def test_delete_needs_the_name_again_and_keeps_the_music_folder(
    env: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, flags in (("boss", ["--admin"]), ("ana", [])):
        admin(
            capsys, monkeypatch, "user-create", "--username", name, *flags,
            "--password-stdin", stdin="a long password\n",
        )  # fmt: skip
    song = env.music_dir / "ana" / "song.flac"
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b"music")

    code, refused = admin(capsys, monkeypatch, "user-delete", "--username", "ana", "--confirm", "x")
    assert code == 1 and "Type the user name" in refused["error"]
    code, done = admin(capsys, monkeypatch, "user-delete", "--username", "ana", "--confirm", "ana")
    assert code == 0 and done["library_folder_kept"] == "ana"
    assert song.read_bytes() == b"music"
    code, refused = admin(
        capsys, monkeypatch, "user-delete", "--username", "boss", "--confirm", "boss"
    )
    assert code == 1 and "last administrator" in refused["error"]


def test_status_roots_and_streaming_settings(
    env: Settings, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, status = admin(capsys, monkeypatch, "status")
    assert code == 0
    assert status["users"] == 0 and status["items"] == 0
    assert set(status["hashes"]) == {"pending", "done", "error"}

    code, roots = admin(capsys, monkeypatch, "roots")
    assert code == 0 and roots == {"roots": []}

    code, settings = admin(capsys, monkeypatch, "settings")
    assert settings["streaming"]["max_transcodes"] == 2
    code, saved = admin(
        capsys, monkeypatch, "settings-set", "max_transcodes=3", "wav_to_flac=false"
    )
    assert code == 0
    assert saved["streaming"]["max_transcodes"] == 3
    assert saved["streaming"]["wav_to_flac"] is False
    code, refused = admin(capsys, monkeypatch, "settings-set", "max_transcodes=99")
    assert code == 1 and "max_transcodes" in refused["error"]
    code, refused = admin(capsys, monkeypatch, "settings-set", "nonsense")
    assert code == 1 and "name=value" in refused["error"]

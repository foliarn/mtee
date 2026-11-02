"""The account commands: create-admin, create-user, reset-password (milestone 124.3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from mtee_remote import cli
from mtee_remote.app import create_app
from mtee_remote.config import Settings
from mtee_remote.passwords import verify_password

GIB = 1024**3


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    data = tmp_path / "data"
    music = tmp_path / "music"
    music.mkdir()
    monkeypatch.setenv("MTEE_REMOTE_DATA", str(data))
    monkeypatch.setenv("MTEE_REMOTE_MUSIC", str(music))
    monkeypatch.setenv("MTEE_REMOTE_ADMIN_PASSWORD", "first password")
    return Settings.from_env()


def test_create_admin_then_log_in_with_the_new_password(
    env: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["create-admin", "--username", "boss"]) == 0
    assert capsys.readouterr().out.strip() == "Admin boss created."

    monkeypatch.setenv("MTEE_REMOTE_ADMIN_PASSWORD", "second password")
    assert cli.main(["reset-password", "--username", "boss"]) == 0
    assert "Password changed; 0 devices signed out." in capsys.readouterr().out

    app = create_app(Settings.from_env())
    with TestClient(app) as client:
        body = {"username": "boss", "device_name": "pc", "device_kind": "desktop"}
        old = client.post("/api/v1/auth/login", json={**body, "password": "first password"})
        assert old.status_code == 401
        new = client.post("/api/v1/auth/login", json={**body, "password": "second password"})
        assert new.status_code == 201
        assert new.json()["user"]["is_admin"] is True


def test_a_duplicate_admin_is_refused(env: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["create-admin", "--username", "boss"]) == 0
    capsys.readouterr()
    assert cli.main(["create-admin", "--username", "BOSS"]) == 1
    assert "already taken" in capsys.readouterr().err


def test_create_user_with_admin_flag_and_quota(
    env: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["create-user", "--username", "carol", "--admin", "--quota-gb", "2"]) == 0
    assert capsys.readouterr().out.strip() == "Admin carol created."

    app = create_app(env)
    row = app.state.db.conn().execute("SELECT * FROM users WHERE username = 'carol'").fetchone()
    assert row["is_admin"] == 1
    assert row["quota_bytes"] == 2 * GIB
    assert row["library_dir"] == "carol"
    assert verify_password(row["password_hash"], "first password")
    assert (env.music_dir / "carol").is_dir()


def test_create_user_without_quota_or_admin(
    env: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["create-user", "--username", "dave"]) == 0
    assert capsys.readouterr().out.strip() == "User dave created."
    row = (
        create_app(env)
        .state.db.conn()
        .execute("SELECT is_admin, quota_bytes FROM users WHERE username = 'dave'")
        .fetchone()
    )
    assert row["is_admin"] == 0
    assert row["quota_bytes"] is None


def test_a_short_password_is_refused(
    env: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MTEE_REMOTE_ADMIN_PASSWORD", "short")
    assert cli.main(["create-admin", "--username", "boss"]) == 1
    assert "at least 8 characters" in capsys.readouterr().err


def test_a_bad_user_name_is_refused(env: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["create-admin", "--username", "../boss"]) == 1
    assert "A user name" in capsys.readouterr().err


def test_reset_password_signs_out_the_users_devices(
    env: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["create-admin", "--username", "boss"]) == 0
    app = create_app(env)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "username": "boss",
                "password": "first password",
                "device_name": "pc",
                "device_kind": "desktop",
            },
        )
        assert login.status_code == 201
        token = {"Authorization": f"Bearer {login.json()['token']}"}
        assert client.get("/api/v1/devices", headers=token).status_code == 200

        monkeypatch.setenv("MTEE_REMOTE_ADMIN_PASSWORD", "second password")
        capsys.readouterr()
        assert cli.main(["reset-password", "--username", "boss"]) == 0
        assert "Password changed; 1 devices signed out." in capsys.readouterr().out
        assert client.get("/api/v1/devices", headers=token).status_code == 401


def test_reset_password_for_an_unknown_user_fails(
    env: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["reset-password", "--username", "ghost"]) == 1
    assert "No account named ghost." in capsys.readouterr().err


def test_missing_settings_exit_with_2(
    env: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MTEE_REMOTE_DATA", raising=False)
    assert cli.main(["create-admin", "--username", "boss"]) == 2
    assert "MTEE_REMOTE_DATA" in capsys.readouterr().err

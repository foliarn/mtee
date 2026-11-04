"""The interface, driven by Textual's pilot, with a fake Docker that records every call."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from textual.widgets import DataTable, Input, Static

from mtee_remote_admin import app as app_module
from mtee_remote_admin.app import AdminApp, SetupScreen
from mtee_remote_admin.compose import Compose
from mtee_remote_admin.envfile import EnvFile
from mtee_remote_admin.paths import Layout
from mtee_remote_admin.screens import PasswordScreen, TextScreen

USERS = [
    {
        "username": "ana",
        "is_admin": True,
        "disabled": False,
        "quota_bytes": None,
        "used_bytes": 3 * 1024**3,
        "devices": 2,
    }
]


class FakeDocker:
    """The calls the interface makes, with the answers of a running server."""

    def __init__(self, state: str = "running") -> None:
        self.calls: list[tuple[str, ...]] = []
        self.passwords: list[str | None] = []
        self._state = state

    def state(self) -> str:
        return self._state

    def build(self) -> str:
        self.calls.append(("build",))
        return ""

    def up(self) -> str:
        self.calls.append(("up",))
        self._state = "running"
        return ""

    def stop(self) -> str:
        self.calls.append(("stop",))
        return ""

    def restart(self) -> str:
        self.calls.append(("restart",))
        return ""

    def logs(self, lines: int = 200) -> str:
        return "server started\n"

    def server_command(self, *args: str) -> str:
        self.calls.append(("server", *args))
        return "Adopted."

    def admin(self, *args: str, password: str | None = None) -> dict[str, Any]:
        self.calls.append(("admin", *args))
        self.passwords.append(password)
        answers: dict[str, dict[str, Any]] = {
            "status": {
                "users": 1, "devices": 2, "items": 1200, "library_bytes": 5 * 1024**3,
                "hashes": {"pending": 10, "done": 1190, "error": 0}, "database_bytes": 2 * 1024**2,
            },
            "users": {"users": USERS},
            "devices": {"devices": []},
            "roots": {"roots": [
                {"root_id": "r1", "username": "ana", "name": "music", "relative_dir": "",
                 "items": 1200, "bytes": 5 * 1024**3, "pending": 10},
            ]},
            "settings": {"streaming": {
                "max_transcodes": 2, "cache_limit_gb": 20, "wav_to_flac": True,
                "lossless_cap": None,
            }},
        }  # fmt: skip
        return answers.get(args[0], {"message": "Done."})


@pytest.fixture
def where(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Layout:
    monkeypatch.setattr(app_module, "health", lambda host, port: (True, "0.1.0"))
    monkeypatch.setattr(app_module, "docker_available", lambda: None)
    return Layout(tmp_path / "home", tmp_path / "config")


def configured(where: Layout, tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir(exist_ok=True)
    env = EnvFile()
    for key, value in {
        "ADMIN_USER": "ana", "MUSIC_DIR": str(music), "DATA_DIR": str(tmp_path / "data"),
        "PORT": "8080", "BIND_ADDRESS": "127.0.0.1", "UID": "1000", "GID": "1000",
        "SCAN_INTERVAL": "0",
    }.items():  # fmt: skip
        env.set(key, value)
    env.write(where.env_file)


def text_of(app: AdminApp, selector: str) -> str:
    return str(app.query_one(selector, Static).render())


async def test_the_status_and_the_tables_show_what_the_server_says(
    where: Layout, tmp_path: Path
) -> None:
    configured(where, tmp_path)
    docker = FakeDocker()
    app = AdminApp(where, cast(Compose, docker))
    async with app.run_test(size=(140, 45)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        status = text_of(app, "#status-text")
        assert "running" in status and "version 0.1.0" in status
        assert "1,200 tracks" in status and "10 waiting" in status
        users = app.query_one("#user-table", DataTable)
        assert users.row_count == 1
        assert users.get_row_at(0)[:4] == ["ana", "yes", "", "no limit"]
        assert app.query_one("#root-table", DataTable).row_count == 1
        assert app.query_one("#stream-max_transcodes", Input).value == "2"


async def test_without_settings_the_setup_comes_first_and_installs(
    where: Layout, tmp_path: Path
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    docker = FakeDocker(state="absent")
    app = AdminApp(where, cast(Compose, docker))
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SetupScreen)
        screen.query_one("#setup-ADMIN_USER", Input).value = "ana"
        screen.query_one("#setup-MUSIC_DIR", Input).value = str(music)
        screen.query_one("#setup-password", Input).value = "a long password"
        screen.query_one("#setup-password-again", Input).value = "a long password"
        screen.go()
        await app.workers.wait_for_complete()
        await pilot.pause()

        values = EnvFile.read(where.env_file).values()
        assert values["ADMIN_USER"] == "ana"
        assert values["DATA_DIR"] == str(where.default_data_dir)
        assert where.default_data_dir.is_dir()
        assert docker.calls[:3] == [
            ("build",),
            ("up",),
            ("admin", "user-create", "--username", "ana", "--admin", "--password-stdin"),
        ]
        assert ("server", "adopt-root", "--user", "ana", "--path", "/music/ana", "--name",
                "music") in docker.calls  # fmt: skip
        assert "a long password" in docker.passwords
        assert not isinstance(app.screen, SetupScreen)


async def test_the_setup_refuses_bad_values_and_runs_nothing(where: Layout, tmp_path: Path) -> None:
    docker = FakeDocker(state="absent")
    app = AdminApp(where, cast(Compose, docker))
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SetupScreen)
        screen.query_one("#setup-ADMIN_USER", Input).value = "A"
        screen.query_one("#setup-MUSIC_DIR", Input).value = "/nowhere/at/all"
        screen.query_one("#setup-password", Input).value = "short"
        screen.go()
        await pilot.pause()
        assert "2 to 32 characters" in str(
            screen.query_one("#setup-problem-ADMIN_USER", Static).render()
        )
        assert "does not exist" in str(
            screen.query_one("#setup-problem-MUSIC_DIR", Static).render()
        )
        assert "At least 8" in str(screen.query_one("#setup-problem-password", Static).render())
        assert docker.calls == []
        assert not where.env_file.exists()


async def test_settings_are_checked_saved_and_applied_on_request(
    where: Layout, tmp_path: Path
) -> None:
    configured(where, tmp_path)
    docker = FakeDocker()
    app = AdminApp(where, cast(Compose, docker))
    async with app.run_test(size=(140, 45)) as pilot:
        await app.workers.wait_for_complete()
        app.query_one("#env-PORT", Input).value = "not a port"
        app.save_settings()
        await pilot.pause()
        assert "1 to 65535" in text_of(app, "#problem-PORT")
        assert EnvFile.read(where.env_file).get("PORT") == "8080", "nothing saved"

        app.query_one("#env-PORT", Input).value = "9000"
        app.query_one("#env-BIND_ADDRESS", Input).value = "192.168.1.29"
        await pilot.pause()
        assert "unencrypted" in text_of(app, "#warning-BIND_ADDRESS")
        app.save_settings()
        await pilot.pause()
        assert EnvFile.read(where.env_file).get("PORT") == "9000"
        await pilot.click("#yes")  # Restart now
        await app.workers.wait_for_complete()
        assert ("restart",) in docker.calls
        assert ("build",) not in docker.calls, "only UID and GID need a rebuild"


async def test_a_new_account_sends_its_password_on_stdin(where: Layout, tmp_path: Path) -> None:
    configured(where, tmp_path)
    docker = FakeDocker()
    app = AdminApp(where, cast(Compose, docker))
    async with app.run_test(size=(140, 45)) as pilot:
        await app.workers.wait_for_complete()
        app.add_user()
        await pilot.pause()
        assert isinstance(app.screen, TextScreen)
        app.screen.dismiss("bob")
        await pilot.pause()
        assert isinstance(app.screen, PasswordScreen)
        app.screen.query_one("#first", Input).value = "a long password"
        app.screen.query_one("#second", Input).value = "a long password"
        await pilot.click("#yes")
        await app.workers.wait_for_complete()
        index = docker.calls.index(
            ("admin", "user-create", "--username", "bob", "--password-stdin")
        )
        assert docker.passwords[index] == "a long password"
        assert all("a long password" not in part for call in docker.calls for part in call)


async def test_the_setup_warns_about_plain_http_while_typing(where: Layout) -> None:
    app = AdminApp(where, cast(Compose, FakeDocker(state="absent")))
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = app.screen
        warning = screen.query_one("#setup-warning-BIND_ADDRESS", Static)
        assert warning.display is False
        screen.query_one("#setup-BIND_ADDRESS", Input).value = "192.168.1.29"
        await pilot.pause()
        assert warning.display is True
        assert "unencrypted" in str(warning.render())
        await pilot.press("s")  # Start does nothing before the setup is done
        await pilot.pause()
        assert app.docker.calls == []  # type: ignore[attr-defined]

"""Administration routes: users, quotas, deletion keeps the library folder (124.3, 124.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from helpers import make_audio
from mtee_remote.library import scanner
from test_scanner import add_root


@pytest.fixture
def admin(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> dict[str, Any]:
    user = make_user(app, "boss", is_admin=True)
    return {**user, "headers": make_device(app, user)["headers"]}


@pytest.fixture
def plain(app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> dict[str, Any]:
    user = make_user(app, "alice")
    return {**user, "headers": make_device(app, user)["headers"]}


def _settings_music(app: Starlette) -> Path:
    music: Path = app.state.settings.music_dir
    return music


def test_non_admin_is_refused_on_every_admin_route(
    client: TestClient, plain: dict[str, Any], admin: dict[str, Any]
) -> None:
    headers = plain["headers"]
    target = f"/api/v1/admin/users/{admin['user_id']}"
    calls = [
        ("GET", "/api/v1/admin/users", None),
        ("POST", "/api/v1/admin/users", {"username": "carol", "password": "long enough"}),
        ("PATCH", target, {"disabled": True}),
        ("DELETE", target + "?confirm=boss", None),
    ]
    for method, path, body in calls:
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 403, f"{method} {path}"
        assert response.json()["error"]["code"] == "forbidden"


def test_admin_routes_need_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/admin/users").status_code == 401


def test_list_users(client: TestClient, admin: dict[str, Any], plain: dict[str, Any]) -> None:
    response = client.get("/api/v1/admin/users", headers=admin["headers"])
    assert response.status_code == 200
    users = response.json()["users"]
    assert [u["username"] for u in users] == ["alice", "boss"]
    assert set(users[0]) == {
        "user_id",
        "username",
        "is_admin",
        "disabled",
        "quota_bytes",
        "created_at_utc",
    }
    assert users[1]["is_admin"] is True


def test_create_user_then_log_in_as_them(
    client: TestClient, app: Starlette, admin: dict[str, Any]
) -> None:
    response = client.post(
        "/api/v1/admin/users",
        json={"username": "Carol", "password": "carol password", "quota_bytes": 5000},
        headers=admin["headers"],
    )
    assert response.status_code == 201
    created = response.json()
    assert created["username"] == "carol"
    assert created["is_admin"] is False
    assert created["disabled"] is False
    assert created["quota_bytes"] == 5000
    assert (_settings_music(app) / "carol").is_dir()

    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": "carol",
            "password": "carol password",
            "device_name": "phone",
            "device_kind": "phone",
        },
    )
    assert login.status_code == 201


def test_create_user_refuses_a_taken_name_and_a_short_password(
    client: TestClient, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    taken = client.post(
        "/api/v1/admin/users",
        json={"username": "ALICE", "password": "long enough"},
        headers=admin["headers"],
    )
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "conflict"

    short = client.post(
        "/api/v1/admin/users",
        json={"username": "dave", "password": "short"},
        headers=admin["headers"],
    )
    assert short.status_code == 400


def test_patch_quota_and_clear_it(
    client: TestClient, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    path = f"/api/v1/admin/users/{plain['user_id']}"
    set_quota = client.patch(path, json={"quota_bytes": 1000}, headers=admin["headers"])
    assert set_quota.status_code == 200
    assert set_quota.json()["quota_bytes"] == 1000

    cleared = client.patch(path, json={"quota_bytes": None}, headers=admin["headers"])
    assert cleared.json()["quota_bytes"] is None

    negative = client.patch(path, json={"quota_bytes": -1}, headers=admin["headers"])
    assert negative.status_code == 400


def test_patch_disable_stops_the_users_token_and_login(
    client: TestClient, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    response = client.patch(
        f"/api/v1/admin/users/{plain['user_id']}",
        json={"disabled": True},
        headers=admin["headers"],
    )
    assert response.status_code == 200
    assert response.json()["disabled"] is True
    assert client.get("/api/v1/devices", headers=plain["headers"]).status_code == 401


def test_patch_can_promote_and_demote_another_admin(
    client: TestClient, app: Starlette, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    path = f"/api/v1/admin/users/{plain['user_id']}"
    promoted = client.patch(path, json={"is_admin": True}, headers=admin["headers"])
    assert promoted.json()["is_admin"] is True
    demoted = client.patch(path, json={"is_admin": False}, headers=admin["headers"])
    assert demoted.json()["is_admin"] is False


def test_an_admin_cannot_disable_or_demote_themselves(
    client: TestClient, admin: dict[str, Any]
) -> None:
    path = f"/api/v1/admin/users/{admin['user_id']}"
    disable = client.patch(path, json={"disabled": True}, headers=admin["headers"])
    assert disable.status_code == 400
    demote = client.patch(path, json={"is_admin": False}, headers=admin["headers"])
    assert demote.status_code == 400
    # Setting a harmless value on oneself is fine.
    quota = client.patch(path, json={"quota_bytes": 10}, headers=admin["headers"])
    assert quota.status_code == 200


def test_patch_validates_the_body(
    client: TestClient, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    path = f"/api/v1/admin/users/{plain['user_id']}"
    assert client.patch(path, json={}, headers=admin["headers"]).status_code == 400
    assert client.patch(path, json={"disabled": "yes"}, headers=admin["headers"]).status_code == 400
    assert client.patch(path, json={"disabled": None}, headers=admin["headers"]).status_code == 400


def test_patch_unknown_user_is_404(client: TestClient, admin: dict[str, Any]) -> None:
    response = client.patch(
        "/api/v1/admin/users/" + "0" * 32, json={"disabled": True}, headers=admin["headers"]
    )
    assert response.status_code == 404


def test_delete_keeps_the_folder_where_it_is_and_stops_the_token(
    client: TestClient, app: Starlette, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    music = _settings_music(app)
    (music / "alice" / "song.txt").write_text("keep me", encoding="utf-8")
    (music / "alice" / ".mtee-trash").mkdir()
    (music / "alice" / ".mtee-trash" / "kept.txt").write_text("also kept", encoding="utf-8")

    response = client.delete(
        f"/api/v1/admin/users/{plain['user_id']}?confirm=alice", headers=admin["headers"]
    )
    assert response.status_code == 200
    assert response.json() == {"library_folder_kept": "alice"}
    assert (music / "alice" / "song.txt").read_text(encoding="utf-8") == "keep me"
    assert (music / "alice" / ".mtee-trash" / "kept.txt").read_text(encoding="utf-8") == "also kept"
    assert not (music / ".trash").exists()

    assert client.get("/api/v1/devices", headers=plain["headers"]).status_code == 401
    names = [
        u["username"]
        for u in client.get("/api/v1/admin/users", headers=admin["headers"]).json()["users"]
    ]
    assert names == ["boss"]


def test_delete_with_items_and_roots_removes_the_rows_but_no_file(
    client: TestClient, app: Starlette, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    root_id, folder = add_root(app, plain)
    make_audio(folder / "a.flac", "flac")
    scanner.scan_root(app.state.db, app.state.settings, root_id)
    response = client.delete(
        f"/api/v1/admin/users/{plain['user_id']}?confirm=alice", headers=admin["headers"]
    )
    assert response.status_code == 200
    assert (folder / "a.flac").is_file()
    conn = app.state.db.conn()
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM roots").fetchone()[0] == 0


def test_delete_without_a_library_folder_keeps_nothing(
    client: TestClient, app: Starlette, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    (_settings_music(app) / "alice").rmdir()
    response = client.delete(
        f"/api/v1/admin/users/{plain['user_id']}?confirm=alice", headers=admin["headers"]
    )
    assert response.status_code == 200
    assert response.json() == {"library_folder_kept": None}


def test_delete_needs_the_user_name_as_confirmation(
    client: TestClient, app: Starlette, admin: dict[str, Any], plain: dict[str, Any]
) -> None:
    path = f"/api/v1/admin/users/{plain['user_id']}"
    assert client.delete(path, headers=admin["headers"]).status_code == 400
    assert client.delete(path + "?confirm=bob", headers=admin["headers"]).status_code == 400
    assert (_settings_music(app) / "alice").is_dir()
    assert client.get("/api/v1/devices", headers=plain["headers"]).status_code == 200


def test_an_admin_cannot_delete_themselves(client: TestClient, admin: dict[str, Any]) -> None:
    response = client.delete(
        f"/api/v1/admin/users/{admin['user_id']}?confirm=boss", headers=admin["headers"]
    )
    assert response.status_code == 400
    assert client.get("/api/v1/devices", headers=admin["headers"]).status_code == 200


def test_delete_unknown_user_is_404(client: TestClient, admin: dict[str, Any]) -> None:
    response = client.delete(
        "/api/v1/admin/users/" + "0" * 32 + "?confirm=ghost", headers=admin["headers"]
    )
    assert response.status_code == 404

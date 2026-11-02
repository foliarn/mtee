"""Login, logout, password hashing, the login limiter and usernames (milestone 124.3)."""

from __future__ import annotations

from typing import Any

import pytest
from argon2 import PasswordHasher
from starlette.applications import Starlette
from starlette.testclient import TestClient

from mtee_remote.errors import ApiError
from mtee_remote.passwords import (
    MIN_PASSWORD_LENGTH,
    check_new_password,
    hash_password,
    needs_rehash,
    verify_password,
)
from mtee_remote.ratelimit import LoginLimiter
from mtee_remote.users import check_username, create_user_row, user_public

PASSWORD = "correct horse battery"
UNAUTHORIZED = "Wrong user name or password."


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _create_user(app: Starlette, username: str = "alice", *, password: str = PASSWORD) -> str:
    """Create a user with a real password through the same code the CLI uses."""
    settings = app.state.settings
    with app.state.db.transaction() as tx:
        return create_user_row(
            tx,
            settings,
            username=username,
            password=password,
            is_admin=False,
            quota_bytes=None,
        )


def _login(
    client: TestClient,
    username: str = "alice",
    password: str = PASSWORD,
    *,
    device_name: str = "laptop",
    device_kind: str = "desktop",
) -> Any:
    return client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": password,
            "device_name": device_name,
            "device_kind": device_kind,
        },
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# -- passwords -----------------------------------------------------------------------


def test_password_round_trip_and_argon2id() -> None:
    stored = hash_password(PASSWORD)
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, PASSWORD) is True
    assert verify_password(stored, "wrong password") is False


def test_verify_password_is_false_for_invalid_hashes() -> None:
    assert verify_password("!test", PASSWORD) is False
    assert verify_password("", PASSWORD) is False


def test_needs_rehash() -> None:
    assert needs_rehash(hash_password(PASSWORD)) is False
    weaker = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(PASSWORD)
    assert needs_rehash(weaker) is True
    assert needs_rehash("!test") is False


def test_check_new_password_refuses_short_passwords() -> None:
    check_new_password("x" * MIN_PASSWORD_LENGTH)
    with pytest.raises(ApiError) as caught:
        check_new_password("x" * (MIN_PASSWORD_LENGTH - 1))
    assert caught.value.code == "bad_request"


# -- usernames -----------------------------------------------------------------------


def test_check_username_lowercases_and_validates() -> None:
    assert check_username("Alice.Smith-2") == "alice.smith-2"
    for bad in ("a", "../etc", ".trash", "_x", "with space", "x" * 33, "naïve"):
        with pytest.raises(ApiError) as caught:
            check_username(bad)
        assert caught.value.code == "bad_request"


# -- limiter (fake clock) ------------------------------------------------------------


def test_limiter_first_four_failures_have_no_wait() -> None:
    limiter = LoginLimiter(now=FakeClock())
    for _ in range(4):
        limiter.failure(["user:alice"])
    assert limiter.retry_after(["user:alice"]) is None


def test_fifth_failure_locks_for_30_seconds_then_releases() -> None:
    clock_fake = FakeClock()
    limiter = LoginLimiter(now=clock_fake)
    for _ in range(5):
        limiter.failure(["user:alice"])
    assert limiter.retry_after(["user:alice"]) == pytest.approx(30.0)
    clock_fake.now += 10
    assert limiter.retry_after(["user:alice"]) == pytest.approx(20.0)
    clock_fake.now += 20
    assert limiter.retry_after(["user:alice"]) is None


def test_lock_doubles_and_is_capped_at_one_hour() -> None:
    clock_fake = FakeClock()
    limiter = LoginLimiter(now=clock_fake)
    for _ in range(4):
        limiter.failure(["k"])
    expected = [30, 60, 120, 240, 480, 960, 1920, 3600, 3600, 3600]
    for failure, wait in enumerate(expected, start=5):
        limiter.failure(["k"])
        assert limiter.retry_after(["k"]) == pytest.approx(wait), f"failure {failure}"
        clock_fake.now += wait + 1


def test_success_resets_the_keys() -> None:
    limiter = LoginLimiter(now=FakeClock())
    for _ in range(6):
        limiter.failure(["user:alice", "addr:1.2.3.4"])
    assert limiter.retry_after(["user:alice"]) is not None
    limiter.success(["user:alice", "addr:1.2.3.4"])
    assert limiter.retry_after(["user:alice", "addr:1.2.3.4"]) is None
    for _ in range(4):
        limiter.failure(["user:alice"])
    assert limiter.retry_after(["user:alice"]) is None


def test_a_locked_key_blocks_the_whole_request() -> None:
    limiter = LoginLimiter(now=FakeClock())
    for _ in range(5):
        limiter.failure(["addr:1.2.3.4"])
    assert limiter.retry_after(["user:alice", "addr:1.2.3.4"]) == pytest.approx(30.0)
    assert limiter.retry_after(["user:bob", "addr:9.9.9.9"]) is None


# -- login over HTTP -----------------------------------------------------------------


def test_login_returns_a_token_that_works(app: Starlette, client: TestClient) -> None:
    user_id = _create_user(app)
    response = _login(client, device_name="Laptop", device_kind="desktop")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"device_id", "token", "user"}
    assert body["user"] == user_public(
        app.state.db.conn().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    )
    assert body["user"]["is_admin"] is False
    assert body["user"]["disabled"] is False

    devices = client.get("/api/v1/devices", headers=_bearer(body["token"]))
    assert devices.status_code == 200
    assert [d["device_id"] for d in devices.json()["devices"]] == [body["device_id"]]


def test_token_is_stored_only_as_a_hash(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    body = _login(client).json()
    stored = app.state.db.conn().execute("SELECT token_hash FROM devices").fetchone()
    assert stored["token_hash"] != body["token"]
    assert len(stored["token_hash"]) == 64


def test_login_username_is_case_insensitive(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    assert _login(client, username="ALICE").status_code == 201


def test_wrong_password_unknown_user_and_disabled_user_look_the_same(
    app: Starlette, client: TestClient
) -> None:
    _create_user(app, "alice")
    _create_user(app, "bob")
    app.state.db.conn().execute("UPDATE users SET disabled = 1 WHERE username = 'bob'")

    responses = [
        _login(client, "alice", "not the password"),
        _login(client, "nobody", PASSWORD),
        _login(client, "bob", PASSWORD),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.json() == {"error": {"code": "unauthorized", "message": UNAUTHORIZED}}


def test_login_rejects_an_unknown_device_kind(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    response = _login(client, device_kind="tablet")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_login_rejects_a_device_name_longer_than_100(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    assert _login(client, device_name="d" * 101).status_code == 400


def test_sixth_wrong_attempt_is_rate_limited(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    for _ in range(5):
        assert _login(client, password="wrong password").status_code == 401

    blocked = _login(client, password="wrong password")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 30

    # The right password is refused too while the lock lasts.
    assert _login(client).status_code == 429


def test_a_successful_login_resets_the_failures(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    for _ in range(4):
        assert _login(client, password="wrong password").status_code == 401
    assert _login(client).status_code == 201
    for _ in range(4):
        assert _login(client, password="wrong password").status_code == 401


def test_the_limiter_is_shared_by_the_application(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    for _ in range(5):
        _login(client, password="wrong password")
    assert app.state.login_limiter.retry_after(["user:alice", "addr:testclient"]) is not None


def test_logout_revokes_the_token(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    token = _login(client).json()["token"]
    assert client.post("/api/v1/auth/logout", headers=_bearer(token)).status_code == 204
    assert client.get("/api/v1/devices", headers=_bearer(token)).status_code == 401


def test_logout_needs_a_token(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_disabled_user_cannot_use_an_existing_token(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    token = _login(client).json()["token"]
    app.state.db.conn().execute("UPDATE users SET disabled = 1 WHERE username = 'alice'")
    assert client.get("/api/v1/devices", headers=_bearer(token)).status_code == 401


def test_login_rehashes_an_outdated_password_hash(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    weaker = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(PASSWORD)
    app.state.db.conn().execute(
        "UPDATE users SET password_hash = ? WHERE username = 'alice'", (weaker,)
    )
    assert _login(client).status_code == 201
    stored = app.state.db.conn().execute("SELECT password_hash FROM users").fetchone()
    assert stored["password_hash"] != weaker
    assert needs_rehash(stored["password_hash"]) is False
    assert verify_password(stored["password_hash"], PASSWORD) is True


def test_login_needs_all_fields(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "alice"})
    assert response.status_code == 400


def test_login_is_public_but_other_routes_are_not(client: TestClient) -> None:
    assert client.get("/api/v1/devices").status_code == 401
    assert client.post("/api/v1/auth/login", content=b"not json").status_code == 400


def test_each_login_opens_a_new_device(app: Starlette, client: TestClient) -> None:
    _create_user(app)
    first = _login(client).json()
    second = _login(client).json()
    assert first["device_id"] != second["device_id"]
    assert first["token"] != second["token"]

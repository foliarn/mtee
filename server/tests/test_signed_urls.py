"""Signed stream URLs: minting, verifying, revocation and the route checks (plan 127.2)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette

from helpers import make_audio
from mtee_remote import clock
from mtee_remote.streaming.signed import SECRET_BYTES, Claims, SignedUrls
from test_uploads import Env
from test_uploads import env as env
from test_uploads import other as other


@pytest.fixture
def song(env: Env, tmp_path: Path) -> tuple[Env, dict[str, Any], bytes]:
    data = make_audio(tmp_path / "song.flac", "flac").read_bytes()
    return env, env.upload("rock/song.flac", data), data


def mint(env: Env, item: dict[str, Any], **body: Any) -> dict[str, Any]:
    response = env.client.post(
        f"/api/v1/items/{item['item_id']}/stream-url", json=body, headers=env.headers
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def _now() -> int:
    return int(clock.utc_now().timestamp())


def _signer(app: Starlette) -> SignedUrls:
    signer: SignedUrls = app.state.stream_urls
    return signer


def _split(url: str) -> tuple[str, str]:
    """The payload part and the signature part of a signed URL."""
    part, _dot, signature = url.rsplit("/", 1)[1].partition(".")
    return part, signature


def _encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(part: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    return data


# -- minting and using a URL ----------------------------------------------------------


def test_the_url_plays_without_a_header(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, data = song
    minted = mint(env, item)
    assert minted["url"].startswith("/api/v1/s/")
    response = env.client.get(minted["url"])
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["Content-Type"] == "audio/flac"
    assert response.headers["X-MTEE-Codec"] == "flac"


def test_the_default_ttl_is_six_hours(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, _data = song
    minted = mint(env, item)
    expires = datetime.strptime(minted["expires_at_utc"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=UTC
    )
    remaining = (expires - clock.utc_now()).total_seconds()
    assert 21600 - 120 <= remaining <= 21600


def test_the_level_in_the_url_is_the_one_delivered(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, _data = song
    minted = mint(env, item, level="320", codecs=["alac", "aac"])
    response = env.client.get(minted["url"])
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "audio/mp4"
    assert response.headers["X-MTEE-Codec"] == "aac"


def test_the_secret_is_created_on_first_use_and_reused(
    song: tuple[Env, dict[str, Any], bytes], app: Starlette
) -> None:
    env, item, _data = song
    secret_file = app.state.settings.data_dir / "stream-secret.bin"
    assert not secret_file.exists()
    minted = mint(env, item)
    assert len(secret_file.read_bytes()) == SECRET_BYTES
    # A second signer on the same file accepts the same URL.
    assert SignedUrls(secret_file).verify(minted["url"].rsplit("/", 1)[1]) is not None


@pytest.mark.parametrize("ttl", [59, 86401, 0, True, "21600"])
def test_ttl_outside_the_limits_is_refused(
    song: tuple[Env, dict[str, Any], bytes], ttl: Any
) -> None:
    env, item, _data = song
    response = env.client.post(
        f"/api/v1/items/{item['item_id']}/stream-url",
        json={"ttl_seconds": ttl},
        headers=env.headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


@pytest.mark.parametrize("ttl", [60, 86400])
def test_ttl_at_the_limits_is_accepted(song: tuple[Env, dict[str, Any], bytes], ttl: int) -> None:
    env, item, _data = song
    minted = mint(env, item, ttl_seconds=ttl)
    assert minted["url"].startswith("/api/v1/s/")


def test_a_missing_item_has_no_url(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, _item, _data = song
    response = env.client.post(
        "/api/v1/items/no-such-item/stream-url", json={}, headers=env.headers
    )
    assert response.status_code == 404


def test_an_unknown_body_field_is_refused(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, _data = song
    response = env.client.post(
        f"/api/v1/items/{item['item_id']}/stream-url", json={"speed": 2}, headers=env.headers
    )
    assert response.status_code == 400


# -- refusals -------------------------------------------------------------------------


def test_an_expired_token_is_refused(
    song: tuple[Env, dict[str, Any], bytes], app: Starlette
) -> None:
    env, item, _data = song
    token = _signer(app).sign(
        Claims(
            item_id=item["item_id"],
            user_id=env.user_id,
            device_id=_device_of(env),
            level="original",
            codecs=frozenset(),
            expires=_now() - 5,
        )
    )
    response = env.client.get(f"/api/v1/s/{token}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_a_tampered_payload_is_refused(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, _data = song
    minted = mint(env, item)
    part, signature = _split(minted["url"])
    claims = _decode(part)
    claims["l"] = "128"
    response = env.client.get(f"/api/v1/s/{_encode(claims)}.{signature}")
    assert response.status_code == 401


def test_a_tampered_signature_is_refused(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, _data = song
    minted = mint(env, item)
    part, signature = _split(minted["url"])
    flipped = signature[:-1] + ("A" if signature[-1] != "A" else "B")
    response = env.client.get(f"/api/v1/s/{part}.{flipped}")
    assert response.status_code == 401


@pytest.mark.parametrize("token", ["abc", "abc.def", "a.b.c", "eyJ9.AAAA"])
def test_garbage_tokens_are_refused(song: tuple[Env, dict[str, Any], bytes], token: str) -> None:
    env, _item, _data = song
    response = env.client.get(f"/api/v1/s/{token}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_a_revoked_device_stops_the_url(
    song: tuple[Env, dict[str, Any], bytes], app: Starlette
) -> None:
    env, item, _data = song
    minted = mint(env, item)
    assert env.client.get(minted["url"]).status_code == 200
    with app.state.db.transaction() as tx:
        tx.conn.execute(
            "UPDATE devices SET revoked_at_utc = ? WHERE device_id = ?",
            (clock.to_iso(clock.utc_now()), _device_of(env)),
        )
    assert env.client.get(minted["url"]).status_code == 401


def test_a_disabled_user_stops_the_url(
    song: tuple[Env, dict[str, Any], bytes], app: Starlette
) -> None:
    env, item, _data = song
    minted = mint(env, item)
    with app.state.db.transaction() as tx:
        tx.conn.execute("UPDATE users SET disabled = 1 WHERE user_id = ?", (env.user_id,))
    assert env.client.get(minted["url"]).status_code == 401


def test_a_token_for_another_users_item_is_refused(
    song: tuple[Env, dict[str, Any], bytes], other: Env, app: Starlette, tmp_path: Path
) -> None:
    env, _item, _data = song
    theirs = other.upload("rock/theirs.flac", make_audio(tmp_path / "t.flac", "flac").read_bytes())
    token = _signer(app).sign(
        Claims(
            item_id=theirs["item_id"],
            user_id=env.user_id,
            device_id=_device_of(env),
            level="original",
            codecs=frozenset(),
            expires=_now() + 600,
        )
    )
    response = env.client.get(f"/api/v1/s/{token}")
    assert response.status_code == 401


def test_a_device_of_another_user_is_refused(
    song: tuple[Env, dict[str, Any], bytes], other: Env, app: Starlette
) -> None:
    env, item, _data = song
    token = _signer(app).sign(
        Claims(
            item_id=item["item_id"],
            user_id=env.user_id,
            device_id=_device_of(other),
            level="original",
            codecs=frozenset(),
            expires=_now() + 600,
        )
    )
    assert env.client.get(f"/api/v1/s/{token}").status_code == 401


def test_a_dummy_token_with_a_header_is_still_401(song: tuple[Env, dict[str, Any], bytes]) -> None:
    env, _item, _data = song
    response = env.client.get("/api/v1/s/x", headers=env.headers)
    assert response.status_code == 401


def _device_of(env: Env) -> str:
    row = (
        env.app.state.db.conn()
        .execute("SELECT device_id FROM devices WHERE user_id = ?", (env.user_id,))
        .fetchone()
    )
    device_id: str = row["device_id"]
    return device_id

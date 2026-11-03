"""The prepare route: background transcodes that are cached before the stream asks (plan 127.4)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from helpers import make_audio
from mtee_remote.streaming import transcode
from mtee_remote.streaming.transcode import TranscodeError
from mtee_remote.streaming.types import DeliveryPlan
from test_uploads import Env
from test_uploads import env as env
from test_uploads import other as other

POLL_LIMIT_S = 30


def audio(tmp_path: Path, name: str, fmt: str, seconds: float = 1.0) -> bytes:
    return make_audio(tmp_path / name, fmt, seconds=seconds).read_bytes()


def prepare_path(item: dict[str, Any], query: str = "") -> str:
    suffix = f"?{query}" if query else ""
    return f"/api/v1/items/{item['item_id']}/prepare{suffix}"


def stream_path(item: dict[str, Any], query: str = "") -> str:
    suffix = f"?{query}" if query else ""
    return f"/api/v1/items/{item['item_id']}/stream{suffix}"


@pytest.fixture
def ffmpeg_runs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The plan key of every ffmpeg transcode run, in order."""
    runs: list[str] = []
    real = transcode.run_transcode

    def counting(ffmpeg: str, source: Path, plan: Any, output: Path, **kwargs: Any) -> None:
        runs.append(plan.key)
        real(ffmpeg, source, plan, output, **kwargs)

    monkeypatch.setattr(transcode, "run_transcode", counting)
    return runs


def test_the_original_needs_no_transcode(env: Env, tmp_path: Path) -> None:
    item = env.upload("rock/song.flac", audio(tmp_path, "song.flac", "flac"))
    response = env.client.post(prepare_path(item), headers=env.headers)
    assert response.status_code == 200
    assert response.json() == {"ready": True, "transcode": False}


def test_a_prepared_transcode_is_ready_and_then_served_from_the_cache(
    env: Env, tmp_path: Path, ffmpeg_runs: list[str]
) -> None:
    item = env.upload("rock/take.wav", audio(tmp_path, "take.wav", "wav"))
    query = "level=320&codecs=aac"

    started = env.client.post(prepare_path(item, query), headers=env.headers)
    assert started.status_code == 202
    assert started.json() == {"ready": False, "transcode": True}

    deadline = time.monotonic() + POLL_LIMIT_S
    while True:
        polled = env.client.post(prepare_path(item, query), headers=env.headers)
        if polled.status_code == 200:
            break
        assert polled.status_code == 202
        assert time.monotonic() < deadline, "the prepared transcode did not finish in time"
        time.sleep(0.05)
    assert polled.json() == {"ready": True, "transcode": True}
    assert ffmpeg_runs == ["aac-320"]

    streamed = env.client.get(stream_path(item, query), headers=env.headers)
    assert streamed.status_code == 200
    assert streamed.headers["X-MTEE-Codec"] == "aac"
    assert ffmpeg_runs == ["aac-320"]


def test_a_stream_right_after_a_prepare_joins_the_same_transcode(
    env: Env, tmp_path: Path, ffmpeg_runs: list[str]
) -> None:
    item = env.upload("rock/take.wav", audio(tmp_path, "take.wav", "wav"))
    query = "level=320&codecs=aac"

    started = env.client.post(prepare_path(item, query), headers=env.headers)
    assert started.status_code == 202
    streamed = env.client.get(stream_path(item, query), headers=env.headers)
    assert streamed.status_code == 200
    assert streamed.headers["X-MTEE-Codec"] == "aac"
    assert ffmpeg_runs == ["aac-320"]


def test_a_pending_hash_is_a_conflict(env: Env, tmp_path: Path, ffmpeg_runs: list[str]) -> None:
    item = env.upload("rock/take.wav", audio(tmp_path, "take.wav", "wav"))
    with env.app.state.db.transaction() as tx:
        tx.conn.execute("UPDATE items SET sha256 = NULL WHERE item_id = ?", (item["item_id"],))
    response = env.client.post(prepare_path(item, "level=320&codecs=aac"), headers=env.headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert ffmpeg_runs == []


def test_another_users_item_is_not_found(env: Env, other: Env, tmp_path: Path) -> None:
    item = env.upload("rock/take.wav", audio(tmp_path, "take.wav", "wav"))
    response = other.client.post(prepare_path(item, "level=320"), headers=other.headers)
    assert response.status_code == 404


def test_no_token_is_refused(env: Env, tmp_path: Path) -> None:
    item = env.upload("rock/take.wav", audio(tmp_path, "take.wav", "wav"))
    response = env.client.post(prepare_path(item, "level=320"))
    assert response.status_code == 401


def test_the_ninth_pending_prepare_of_one_user_is_rate_limited(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()

    def stuck(
        ffmpeg: str,
        source: Path,
        plan: DeliveryPlan,
        output: Path,
        *,
        timeout: float = 0,
        cancel: threading.Event | None = None,
    ) -> None:
        assert cancel is not None
        release.wait(POLL_LIMIT_S)
        raise TranscodeError("stopped in the test")

    monkeypatch.setattr(transcode, "run_transcode", stuck)
    items = [
        env.upload(
            f"rock/take{index}.wav", audio(tmp_path, f"take{index}.wav", "wav", 1 + index / 10)
        )
        for index in range(9)
    ]
    try:
        for item in items[:8]:
            response = env.client.post(
                prepare_path(item, "level=320&codecs=aac"), headers=env.headers
            )
            assert response.status_code == 202
        refused = env.client.post(
            prepare_path(items[8], "level=320&codecs=aac"), headers=env.headers
        )
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "rate_limited"
    finally:
        release.set()

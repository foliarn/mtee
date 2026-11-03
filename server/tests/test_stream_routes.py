"""The stream route: levels, delivered headers, Range, the transcode cache, access (plan 127.2)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from helpers import make_audio
from mtee_remote import tools
from mtee_remote.routes import media
from mtee_remote.streaming import transcode
from mtee_remote.streaming.cache import TranscodeCache
from mtee_remote.streaming.transcode import TranscodeError
from mtee_remote.streaming.types import DeliveryPlan
from test_uploads import Env
from test_uploads import env as env
from test_uploads import other as other


def audio(tmp_path: Path, name: str, fmt: str, seconds: float = 1.0) -> bytes:
    return make_audio(tmp_path / name, fmt, seconds=seconds).read_bytes()


def probe(tmp_path: Path, data: bytes, suffix: str) -> dict[str, Any]:
    """The first audio stream of `data`, as ffprobe reports it."""
    path = tmp_path / f"probe{suffix}"
    path.write_bytes(data)
    result = subprocess.run(
        [
            tools.ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,bits_per_raw_sample",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    streams: list[dict[str, Any]] = json.loads(result.stdout)["streams"]
    return streams[0]


def stream_path(item: dict[str, Any], query: str = "") -> str:
    suffix = f"?{query}" if query else ""
    return f"/api/v1/items/{item['item_id']}/stream{suffix}"


@pytest.fixture
def flac_item(env: Env, tmp_path: Path) -> tuple[Env, dict[str, Any], bytes]:
    data = audio(tmp_path, "song.flac", "flac")
    return env, env.upload("rock/song.flac", data), data


def _noise_upload(env: Env, tmp_path: Path, channels: int) -> tuple[Env, dict[str, Any], bytes]:
    """White noise in FLAC with `channels` channels: a bitrate far above 320 kbps.

    A plain sine is only about 190 kbps as FLAC, and the level rules never send a lossy output
    above the source's bitrate, so the cap under test would not apply to it.
    """
    target = tmp_path / "noise.flac"
    subprocess.run(
        [
            tools.ffmpeg_path(),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=d=1:c=white:r=44100:a=0.9",
            "-ac",
            str(channels),
            "-c:a",
            "flac",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    data = target.read_bytes()
    return env, env.upload("rock/noise.flac", data), data


@pytest.fixture
def noisy_flac_item(env: Env, tmp_path: Path) -> tuple[Env, dict[str, Any], bytes]:
    """Stereo white noise in FLAC, above 320 kbps."""
    return _noise_upload(env, tmp_path, 2)


@pytest.fixture
def noisy_mono_flac_item(env: Env, tmp_path: Path) -> tuple[Env, dict[str, Any], bytes]:
    """Mono white noise in FLAC, above 256 kbps: the Opus cap is what applies at level 320."""
    return _noise_upload(env, tmp_path, 1)


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


# -- original and Range ---------------------------------------------------------------


def test_original_is_the_file_with_headers(flac_item: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, data = flac_item
    response = env.client.get(stream_path(item), headers=env.headers)
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["Content-Type"] == "audio/flac"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert response.headers["Content-Length"] == str(len(data))
    assert response.headers["ETag"] == f'"{item["sha256"]}-original"'
    assert response.headers["Cache-Control"] == "private, max-age=86400"
    assert response.headers["X-MTEE-Codec"] == "flac"


def test_range_from_the_start(flac_item: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, data = flac_item
    response = env.client.get(stream_path(item), headers={**env.headers, "Range": "bytes=0-"})
    assert response.status_code == 206
    assert response.content == data
    assert response.headers["Content-Range"] == f"bytes 0-{len(data) - 1}/{len(data)}"


def test_range_in_the_middle(flac_item: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, data = flac_item
    response = env.client.get(stream_path(item), headers={**env.headers, "Range": "bytes=100-199"})
    assert response.status_code == 206
    assert response.content == data[100:200]
    assert response.headers["Content-Length"] == "100"


def test_suffix_range(flac_item: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, data = flac_item
    response = env.client.get(stream_path(item), headers={**env.headers, "Range": "bytes=-100"})
    assert response.status_code == 206
    assert response.content == data[-100:]


def test_unsatisfiable_range_is_416(flac_item: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, data = flac_item
    response = env.client.get(
        stream_path(item),
        headers={**env.headers, "Range": f"bytes={len(data) + 1000}-"},
    )
    assert response.status_code == 416
    assert response.headers["Content-Range"] == f"bytes */{len(data)}"


# -- transcodes -----------------------------------------------------------------------


def test_lossless_wav_becomes_flac(env: Env, tmp_path: Path) -> None:
    wav = audio(tmp_path, "take.wav", "wav")
    item = env.upload("rock/take.wav", wav)
    response = env.client.get(stream_path(item, "level=lossless"), headers=env.headers)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "audio/flac"
    assert response.headers["X-MTEE-Codec"] == "flac"
    assert response.headers["X-MTEE-Sample-Rate"] == "44100"
    assert response.headers["ETag"] == f'"{item["sha256"]}-lossless-flac"'
    assert response.content[:4] == b"fLaC"
    assert probe(tmp_path, response.content, ".flac")["codec_name"] == "flac"


def test_320_from_flac_is_aac_for_apple_clients(
    noisy_flac_item: tuple[Env, dict[str, Any], bytes], tmp_path: Path
) -> None:
    env, item, _data = noisy_flac_item
    response = env.client.get(stream_path(item, "level=320&codecs=alac,aac"), headers=env.headers)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "audio/mp4"
    assert response.headers["X-MTEE-Codec"] == "aac"
    assert response.headers["X-MTEE-Bitrate"] == "320000"
    assert response.headers["X-MTEE-Sample-Rate"] == "44100"
    assert "X-MTEE-Bit-Depth" not in response.headers
    assert probe(tmp_path, response.content, ".m4a")["codec_name"] == "aac"


def test_320_from_flac_is_opus_for_other_clients(
    noisy_flac_item: tuple[Env, dict[str, Any], bytes], tmp_path: Path
) -> None:
    env, item, _data = noisy_flac_item
    response = env.client.get(stream_path(item, "level=320&codecs=flac,opus"), headers=env.headers)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "audio/ogg"
    assert response.headers["X-MTEE-Codec"] == "opus"
    assert response.headers["X-MTEE-Bitrate"] == "256000"
    assert response.headers["X-MTEE-Sample-Rate"] == "48000"
    assert probe(tmp_path, response.content, ".opus")["codec_name"] == "opus"


def test_320_from_a_mono_flac_is_opus_at_256(
    noisy_mono_flac_item: tuple[Env, dict[str, Any], bytes], tmp_path: Path
) -> None:
    """libopus refuses 320 kbps for mono, so level 320 is capped at 256 kbps Opus."""
    env, item, _data = noisy_mono_flac_item
    response = env.client.get(stream_path(item, "level=320&codecs=flac,opus"), headers=env.headers)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "audio/ogg"
    assert response.headers["X-MTEE-Codec"] == "opus"
    assert response.headers["X-MTEE-Bitrate"] == "256000"
    assert response.headers["X-MTEE-Sample-Rate"] == "48000"
    assert probe(tmp_path, response.content, ".opus")["codec_name"] == "opus"


def test_an_mp3_at_128_is_never_upscaled_to_320(env: Env, tmp_path: Path) -> None:
    mp3 = audio(tmp_path, "old.mp3", "mp3")
    item = env.upload("rock/old.mp3", mp3)
    response = env.client.get(stream_path(item, "level=320&codecs=mp3,aac"), headers=env.headers)
    assert response.status_code == 200
    assert response.content == mp3
    assert response.headers["Content-Type"] == "audio/mpeg"
    assert response.headers["X-MTEE-Codec"] == "mp3"


def test_a_lossy_source_the_client_cannot_take_is_transcoded_at_its_own_rate(
    env: Env, tmp_path: Path
) -> None:
    """MP3 is not in the default codec set, so the 128 kbps file becomes Opus at 128 kbps.

    AAC is chosen only for clients that take AAC and not Opus, or that also take ALAC.
    """
    mp3 = audio(tmp_path, "old.mp3", "mp3")
    item = env.upload("rock/old.mp3", mp3)
    response = env.client.get(stream_path(item, "level=320"), headers=env.headers)
    assert response.status_code == 200
    assert response.headers["X-MTEE-Codec"] == "opus"
    assert response.headers["X-MTEE-Bitrate"] == "128000"


def test_second_request_is_served_from_the_cache(
    env: Env, tmp_path: Path, ffmpeg_runs: list[str]
) -> None:
    wav = audio(tmp_path, "take.wav", "wav")
    item = env.upload("rock/take.wav", wav)
    first = env.client.get(stream_path(item, "level=320&codecs=aac"), headers=env.headers)
    second = env.client.get(stream_path(item, "level=320&codecs=aac"), headers=env.headers)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert ffmpeg_runs == ["aac-320"]


def test_range_works_on_a_transcode(env: Env, tmp_path: Path) -> None:
    wav = audio(tmp_path, "take.wav", "wav")
    item = env.upload("rock/take.wav", wav)
    full = env.client.get(stream_path(item, "level=lossless"), headers=env.headers)
    part = env.client.get(
        stream_path(item, "level=lossless"),
        headers={**env.headers, "Range": "bytes=10-19"},
    )
    assert part.status_code == 206
    assert part.content == full.content[10:20]


# -- access and errors ----------------------------------------------------------------


def test_another_users_item_is_not_found(
    flac_item: tuple[Env, dict[str, Any], bytes], other: Env
) -> None:
    _env, item, _data = flac_item
    response = other.client.get(stream_path(item), headers=other.headers)
    assert response.status_code == 404


def test_no_token_is_refused(flac_item: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, _data = flac_item
    response = env.client.get(stream_path(item))
    assert response.status_code == 401


def test_a_pending_hash_refuses_a_transcode_but_not_the_original(
    flac_item: tuple[Env, dict[str, Any], bytes], ffmpeg_runs: list[str]
) -> None:
    env, item, _data = flac_item
    with env.app.state.db.transaction() as tx:
        tx.conn.execute("UPDATE items SET sha256 = NULL WHERE item_id = ?", (item["item_id"],))
    refused = env.client.get(stream_path(item, "level=320&codecs=aac"), headers=env.headers)
    assert refused.status_code == 409
    assert refused.json()["error"]["message"] == (
        "The file is still being analysed; try again in a moment."
    )
    assert ffmpeg_runs == []
    original = env.client.get(stream_path(item), headers=env.headers)
    assert original.status_code == 200
    assert "-original" not in original.headers.get("ETag", "")


def test_a_missing_file_is_not_found(flac_item: tuple[Env, dict[str, Any], bytes]) -> None:
    env, item, _data = flac_item
    (env.folder / "rock" / "song.flac").unlink()
    response = env.client.get(stream_path(item), headers=env.headers)
    assert response.status_code == 404


@pytest.mark.parametrize("query", ["level=loud", "level=", "codecs=mp3x", "codecs=flac,wma"])
def test_bad_values_are_bad_requests(
    flac_item: tuple[Env, dict[str, Any], bytes], query: str
) -> None:
    env, item, _data = flac_item
    response = env.client.get(stream_path(item, query), headers=env.headers)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_the_lifespan_starts_one_cache_with_the_default_settings(app: Starlette) -> None:
    with TestClient(app):
        assert isinstance(app.state.transcodes, TranscodeCache)
        assert app.state.streaming_settings["max_transcodes"] == 2
        assert app.state.streaming_settings["cache_limit_gb"] == 20


def test_a_client_that_leaves_cancels_its_transcode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route stops waiting and the transcode is cancelled once no request waits for it."""
    started = threading.Event()
    finished = threading.Event()
    stopped_by_cancel: list[bool] = []

    def slow(
        ffmpeg: str,
        source: Path,
        plan: DeliveryPlan,
        output: Path,
        *,
        timeout: float = 0,
        cancel: threading.Event | None = None,
    ) -> None:
        assert cancel is not None
        started.set()
        cancel.wait(30)
        stopped_by_cancel.append(cancel.is_set())
        finished.set()
        raise TranscodeError("cancelled in the test")

    monkeypatch.setattr(transcode, "run_transcode", slow)
    cache = TranscodeCache(tmp_path / "cache", max_concurrent=1, limit_bytes=1 << 30)
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF")
    plan = DeliveryPlan(send_original=False, codec="flac", ext="flac", key="flac")

    class GoneClient:
        app = SimpleNamespace(state=SimpleNamespace(transcodes=cache))

        async def is_disconnected(self) -> bool:
            return True

    async def run() -> None:
        with pytest.raises(media._ClientGoneError):  # pyright: ignore[reportPrivateUsage]
            await media._cached(  # pyright: ignore[reportPrivateUsage]
                cast(Any, GoneClient()), source, "a" * 64, plan
            )

    asyncio.run(run())
    assert started.is_set()
    assert finished.wait(10)
    assert stopped_by_cancel == [True]

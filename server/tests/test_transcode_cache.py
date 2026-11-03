"""The transcode cache: hits, single-flight, concurrency, failures, cancel, eviction."""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import make_audio
from mtee_remote.streaming import transcode
from mtee_remote.streaming.cache import PART_MIN_AGE_S, TranscodeCache
from mtee_remote.streaming.transcode import TranscodeError
from mtee_remote.streaming.types import DeliveryPlan

FLAC_16 = DeliveryPlan(send_original=False, codec="flac", bit_depth=16, ext="flac", key="flac16")
OPUS_128 = DeliveryPlan(
    send_original=False, codec="opus", bitrate=128000, ext="opus", key="opus128"
)
AAC_320 = DeliveryPlan(send_original=False, codec="aac", bitrate=320000, ext="m4a", key="aac320")
SHA = hashlib.sha256(b"a source").hexdigest()
MB = 1024 * 1024

Body = Callable[[Path, threading.Event | None], None]


def _cache(
    tmp_path: Path, *, max_concurrent: int = 2, limit_bytes: int = 1 << 40
) -> TranscodeCache:
    return TranscodeCache(
        tmp_path / "cache",
        max_concurrent=max_concurrent,
        limit_bytes=limit_bytes,
        music_dir=tmp_path / "music",
    )


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _write(path: Path, size: int, mtime: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture(scope="module")
def long_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Half an hour of tone: an Opus encode of it is still running when the test closes."""
    folder = tmp_path_factory.mktemp("long")
    return make_audio(folder / "long.flac", "flac", seconds=1800.0)


def _replace_runner(monkeypatch: pytest.MonkeyPatch, body: Body) -> None:
    """Replace ffmpeg by `body(output, cancel)`; the cache code itself is unchanged."""

    def runner(
        ffmpeg: str,
        source: Path,
        plan: DeliveryPlan,
        output: Path,
        *,
        timeout: float = 0,
        cancel: threading.Event | None = None,
    ) -> None:
        body(output, cancel)

    monkeypatch.setattr(transcode, "run_transcode", runner)


def _count_real_runs(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Count the real ffmpeg runs; each entry is the output path of one run."""
    runs: list[Path] = []
    real = transcode.run_transcode

    def counting(
        ffmpeg: str,
        source: Path,
        plan: DeliveryPlan,
        output: Path,
        *,
        timeout: float = transcode.RUN_TIMEOUT_S,
        cancel: threading.Event | None = None,
    ) -> None:
        runs.append(output)
        real(ffmpeg, source, plan, output, timeout=timeout, cancel=cancel)

    monkeypatch.setattr(transcode, "run_transcode", counting)
    return runs


# ---- layout and validation ----------------------------------------------------------------


def test_path_for_is_sharded_by_hash_and_named_by_key(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    assert cache.path_for(SHA, FLAC_16) == tmp_path / "cache" / SHA[:2] / SHA / "flac16.flac"


def test_path_for_rejects_a_value_that_is_not_a_sha256(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _cache(tmp_path).path_for("../../etc/passwd", FLAC_16)


def test_the_original_is_never_cached(tmp_path: Path) -> None:
    source = make_audio(tmp_path / "a.flac", "flac")
    original = DeliveryPlan.original("audio/flac", "flac")
    with pytest.raises(ValueError):
        asyncio.run(_cache(tmp_path).ensure(source, SHA, original))


def test_the_filesystem_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        TranscodeCache(Path(Path.cwd().anchor), max_concurrent=1, limit_bytes=MB)


def test_a_music_folder_inside_the_cache_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        TranscodeCache(
            tmp_path / "cache",
            max_concurrent=1,
            limit_bytes=MB,
            music_dir=tmp_path / "cache" / "music",
        )


def test_the_cache_inside_the_music_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        TranscodeCache(
            tmp_path / "music" / "cache",
            max_concurrent=1,
            limit_bytes=MB,
            music_dir=tmp_path / "music",
        )


def test_zero_concurrency_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        TranscodeCache(tmp_path / "cache", max_concurrent=0, limit_bytes=MB)


# ---- ensure with real ffmpeg --------------------------------------------------------------


def test_second_ensure_is_a_cache_hit_and_runs_no_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_audio(tmp_path / "a.flac", "flac", seconds=1.0)
    runs = _count_real_runs(monkeypatch)
    cache = _cache(tmp_path)

    async def scenario() -> tuple[Path, Path]:
        return await cache.ensure(source, SHA, FLAC_16), await cache.ensure(source, SHA, FLAC_16)

    first, second = asyncio.run(scenario())
    assert first == second == cache.path_for(SHA, FLAC_16)
    assert first.is_file()
    assert len(runs) == 1
    assert _files(tmp_path / "cache") == [first]


def test_a_hit_touches_the_mtime(tmp_path: Path) -> None:
    source = make_audio(tmp_path / "a.flac", "flac", seconds=1.0)
    cache = _cache(tmp_path)
    path = asyncio.run(cache.ensure(source, SHA, FLAC_16))
    os.utime(path, (1_000_000, 1_000_000))
    asyncio.run(cache.ensure(source, SHA, FLAC_16))
    assert path.stat().st_mtime > 1_000_000


def test_concurrent_ensure_for_one_key_runs_one_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_audio(tmp_path / "a.flac", "flac", seconds=1.0)
    runs = _count_real_runs(monkeypatch)
    cache = _cache(tmp_path)

    async def scenario() -> list[Path]:
        return list(await asyncio.gather(*(cache.ensure(source, SHA, OPUS_128) for _ in range(5))))

    results = asyncio.run(scenario())
    assert len(runs) == 1
    assert set(results) == {cache.path_for(SHA, OPUS_128)}


def test_a_failing_source_raises_and_leaves_no_file(tmp_path: Path) -> None:
    bad = tmp_path / "notes.flac"
    bad.write_text("this is not audio")
    cache = _cache(tmp_path)
    with pytest.raises(TranscodeError):
        asyncio.run(cache.ensure(bad, SHA, FLAC_16))
    assert _files(tmp_path / "cache") == []


def test_close_stops_a_real_ffmpeg_and_leaves_no_part(tmp_path: Path, long_source: Path) -> None:
    cache = _cache(tmp_path)

    def parts() -> list[Path]:
        return [path for path in _files(tmp_path / "cache") if ".part-" in path.name]

    async def scenario() -> None:
        task = asyncio.create_task(cache.ensure(long_source, SHA, OPUS_128))
        for _ in range(1000):
            if parts():
                break
            await asyncio.sleep(0.01)
        assert parts(), "ffmpeg should be writing a part file"
        await cache.close()
        with pytest.raises(TranscodeError):
            await task
        assert not cache._live

    asyncio.run(scenario())
    assert _files(tmp_path / "cache") == []


def test_a_caller_that_leaves_cancels_the_transcode_nobody_waits_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    stopped = threading.Event()

    def body(output: Path, cancel: threading.Event | None) -> None:
        assert cancel is not None
        output.write_bytes(b"partial")
        started.set()
        cancel.wait(5)
        output.unlink()
        stopped.set()
        raise TranscodeError("cancelled by the test")

    _replace_runner(monkeypatch, body)
    cache = _cache(tmp_path)
    source = tmp_path / "source.bin"
    source.write_bytes(b"not used")

    async def scenario() -> None:
        task = asyncio.create_task(cache.ensure(source, SHA, FLAC_16))
        while not started.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        for _ in range(1000):
            if not cache._live:
                break
            await asyncio.sleep(0.01)
        assert not cache._live

    asyncio.run(scenario())
    assert stopped.is_set()
    assert _files(tmp_path / "cache") == []


def test_a_new_request_after_everyone_left_starts_a_fresh_transcode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    calls: list[int] = []

    def body(output: Path, cancel: threading.Event | None) -> None:
        assert cancel is not None
        calls.append(1)
        if len(calls) == 1:
            output.write_bytes(b"partial")
            started.set()
            cancel.wait(5)
            output.unlink()
            raise TranscodeError("cancelled by the test")
        output.write_bytes(b"complete")

    _replace_runner(monkeypatch, body)
    cache = _cache(tmp_path)
    source = tmp_path / "source.bin"
    source.write_bytes(b"not used")

    async def scenario() -> Path:
        task = asyncio.create_task(cache.ensure(source, SHA, FLAC_16))
        while not started.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return await cache.ensure(source, SHA, FLAC_16)

    final = asyncio.run(scenario())
    assert len(calls) == 2
    assert final.read_bytes() == b"complete"


def test_close_during_a_fake_transcode_leaves_no_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()

    def body(output: Path, cancel: threading.Event | None) -> None:
        assert cancel is not None
        output.write_bytes(b"partial")
        started.set()
        cancel.wait(5)
        output.unlink()
        raise TranscodeError("cancelled by the test")

    _replace_runner(monkeypatch, body)
    cache = _cache(tmp_path)
    source = tmp_path / "source.bin"
    source.write_bytes(b"not used")

    async def scenario() -> None:
        task = asyncio.create_task(cache.ensure(source, SHA, FLAC_16))
        while not started.is_set():
            await asyncio.sleep(0.01)
        await cache.close()
        with pytest.raises(TranscodeError):
            await task

    asyncio.run(scenario())
    assert _files(tmp_path / "cache") == []


def test_close_refuses_new_requests(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"not used")

    async def scenario() -> None:
        cache = _cache(tmp_path)
        await cache.close()
        with pytest.raises(RuntimeError):
            await cache.ensure(source, SHA, FLAC_16)

    asyncio.run(scenario())


def test_max_concurrent_one_never_runs_two_transcodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def body(output: Path, cancel: threading.Event | None) -> None:
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.15)
        output.write_bytes(b"fake")
        with lock:
            state["active"] -= 1

    _replace_runner(monkeypatch, body)
    cache = _cache(tmp_path, max_concurrent=1)
    source = tmp_path / "source.bin"
    source.write_bytes(b"not used")

    async def scenario() -> None:
        await asyncio.gather(
            cache.ensure(source, SHA, FLAC_16),
            cache.ensure(source, SHA, OPUS_128),
            cache.ensure(source, SHA, AAC_320),
        )

    asyncio.run(scenario())
    assert state["peak"] == 1
    assert len(_files(tmp_path / "cache")) == 3


def test_clear_stale_parts_removes_only_part_files(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    now = time.time()
    final = _write(tmp_path / "cache" / "ab" / SHA / "flac16.flac", 10, now)
    _write(tmp_path / "cache" / "ab" / SHA / "flac16.flac.part-1234", 10, now)
    assert cache.clear_stale_parts() == 1
    assert _files(tmp_path / "cache") == [final]


# ---- eviction -----------------------------------------------------------------------------


def test_evict_removes_the_least_recently_used_until_under_the_limit(tmp_path: Path) -> None:
    now = time.time()
    cache = _cache(tmp_path, limit_bytes=250)
    oldest = _write(tmp_path / "cache" / "aa" / "1" / "k.flac", 100, now - 5000)
    old = _write(tmp_path / "cache" / "bb" / "2" / "k.flac", 100, now - 4000)
    newer = _write(tmp_path / "cache" / "cc" / "3" / "k.flac", 100, now - 3000)
    newest = _write(tmp_path / "cache" / "dd" / "4" / "k.flac", 100, now - 100)
    assert cache.evict() == 200
    assert not oldest.exists()
    assert not old.exists()
    assert _files(tmp_path / "cache") == sorted([newer, newest])


def test_evict_does_nothing_under_the_limit(tmp_path: Path) -> None:
    cache = _cache(tmp_path, limit_bytes=10 * MB)
    _write(tmp_path / "cache" / "aa" / "1" / "k.flac", 100, time.time() - 9999)
    assert cache.evict() == 0
    assert len(_files(tmp_path / "cache")) == 1


def test_evict_skips_young_parts_and_deletes_old_ones(tmp_path: Path) -> None:
    now = time.time()
    cache = _cache(tmp_path, limit_bytes=150)
    final = _write(tmp_path / "cache" / "aa" / "1" / "k.flac", 100, now - 100)
    young = _write(tmp_path / "cache" / "aa" / "1" / "k.flac.part-young", 100, now - 60)
    old = _write(
        tmp_path / "cache" / "aa" / "1" / "k.flac.part-old",
        100,
        now - PART_MIN_AGE_S - 60,
    )
    assert cache.evict() == 200
    assert young.exists()
    assert not old.exists()
    assert not final.exists()


def test_evict_never_deletes_the_file_just_made(tmp_path: Path) -> None:
    now = time.time()
    cache = _cache(tmp_path, limit_bytes=0)
    kept = _write(tmp_path / "cache" / "aa" / "1" / "k.flac", 100, now - 9000)
    gone = _write(tmp_path / "cache" / "bb" / "2" / "k.flac", 100, now - 8000)
    cache.evict(keep=kept)
    assert kept.exists()
    assert not gone.exists()


def test_evict_never_touches_files_outside_the_cache(tmp_path: Path) -> None:
    now = time.time()
    music = _write(tmp_path / "music" / "song.flac", 500, now - 99999)
    outside = _write(tmp_path / "elsewhere.bin", 500, now - 99999)
    cache = _cache(tmp_path, limit_bytes=0)
    _write(tmp_path / "cache" / "aa" / "1" / "k.flac", 100, now - 9999)
    cache.evict()
    assert music.exists()
    assert outside.exists()
    assert _files(tmp_path / "cache") == []


def test_evict_removes_empty_folders_but_keeps_the_root(tmp_path: Path) -> None:
    cache = _cache(tmp_path, limit_bytes=0)
    _write(tmp_path / "cache" / "aa" / "1" / "k.flac", 100, time.time() - 9999)
    cache.evict()
    assert (tmp_path / "cache").is_dir()
    assert not (tmp_path / "cache" / "aa").exists()


def test_evict_keeps_the_folder_of_a_running_transcode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()

    def body(output: Path, cancel: threading.Event | None) -> None:
        started.set()
        release.wait(5)
        output.write_bytes(b"done")

    _replace_runner(monkeypatch, body)
    cache = _cache(tmp_path, limit_bytes=0)
    source = tmp_path / "source.bin"
    source.write_bytes(b"not used")

    async def scenario() -> Path:
        task = asyncio.create_task(cache.ensure(source, SHA, FLAC_16))
        while not started.is_set():
            await asyncio.sleep(0.01)
        cache.evict()
        assert cache.path_for(SHA, FLAC_16).parent.is_dir()
        release.set()
        return await task

    final = asyncio.run(scenario())
    # The file just made is the one eviction keeps, even with a limit of zero.
    assert final.read_bytes() == b"done"

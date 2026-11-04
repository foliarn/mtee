"""The hashes of the local tracks (plan 126.2): the audio hash equals the server's, tags aside.

The server tests run against the real server of the session (``conftest.py``); the files are copies
in temporary folders, made by the pinned ffmpeg. Nothing here writes to a music file of the user.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import cast

import mutagen.flac
import pytest
from mtee.plugins.remote import hashing  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.hashing import (  # pyright: ignore[reportMissingImports]
    audio_hash,
    file_sha256,
    hash_tracks,
)
from tests.plugins.remote.conftest import RemoteServer
from tests.plugins.remote.helpers import (
    FakeJob,
    FakeLibrary,
    copy_of,
    fake_job,
    make_context,
    make_sine,
    pinned_ffmpeg,
    publish,
    track,
)

from mtee.plugins.api import JobContext


def tagged_copy(source: Path, destination: Path, title: str) -> Path:
    """A copy of a FLAC with another title: the tags change, the audio does not."""
    copy_of(source, destination)
    audio = mutagen.flac.FLAC(destination)
    audio["title"] = title
    audio.save()
    return destination


def test_the_file_sha256_is_the_hash_of_the_whole_file(tmp_path: Path) -> None:
    sample = make_sine(tmp_path / "tone.flac")
    assert file_sha256(sample) == hashlib.sha256(sample.read_bytes()).hexdigest()


def test_a_tag_edit_keeps_the_audio_hash_and_changes_the_sha256(tmp_path: Path) -> None:
    pinned_ffmpeg()
    original = make_sine(tmp_path / "source" / "tone.flac")
    edited = tagged_copy(original, tmp_path / "copy" / "tone.flac", "Another title")

    assert file_sha256(edited) != file_sha256(original)
    ffmpeg = pinned_ffmpeg()
    assert audio_hash(ffmpeg, edited) == audio_hash(ffmpeg, original)
    assert audio_hash(ffmpeg, original) is not None


def test_a_file_ffmpeg_cannot_read_has_a_sha256_and_no_audio_hash(tmp_path: Path) -> None:
    text = tmp_path / "notes.flac"
    text.write_bytes(b"this is not audio at all\n" * 20)
    ffmpeg = pinned_ffmpeg()
    assert audio_hash(ffmpeg, text) is None
    assert len(file_sha256(text)) == 64


def test_the_audio_hash_equals_the_one_the_server_computes(
    tmp_path: Path, remote_server: RemoteServer, make_user
) -> None:
    username, password = make_user()
    sample = make_sine(tmp_path / "local" / "Album" / "tone.flac", frequency=523)
    client, root_id = publish(remote_server, username, password, {"Album/tone.flac": sample})
    (item,) = client.all_items(root_id=root_id)

    assert item["sha256"] == file_sha256(sample)
    assert item["audio_hash"] == audio_hash(pinned_ffmpeg(), sample)
    assert item["audio_hash"] is not None


def test_hash_tracks_reads_each_track_under_its_lease_and_reports_progress(tmp_path: Path) -> None:
    first = make_sine(tmp_path / "music" / "one.flac", frequency=300)
    second = make_sine(tmp_path / "music" / "two.flac", frequency=600)
    library = FakeLibrary([tmp_path / "music"], [track("t1", first), track("t2", second)])
    context = make_context(tmp_path, library)
    job = FakeJob()

    report = hash_tracks(context, ["t1", "t2"], cast(JobContext, job))

    assert report.skipped == {}
    assert report.hashes["t1"].sha256 == file_sha256(first)
    assert report.hashes["t2"].audio_hash == audio_hash(pinned_ffmpeg(), second)
    assert report.hashed == 2
    assert report.cached == 0
    assert job.progress == [0.5, 1.0]


def test_the_cache_avoids_a_second_hash_of_an_unchanged_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sample = make_sine(tmp_path / "music" / "tone.flac")
    past_ns = time.time_ns() - 10_000_000_000
    os.utime(sample, ns=(past_ns, past_ns))  # 10 s old: outside the racy window
    library = FakeLibrary([tmp_path / "music"], [track("t1", sample)])
    context = make_context(tmp_path, library)
    calls = {"sha": 0, "audio": 0}
    real_sha = hashing.file_sha256
    real_audio = hashing.audio_hash

    def counted_sha(path: Path) -> str:
        calls["sha"] += 1
        return real_sha(path)

    def counted_audio(ffmpeg: Path, path: Path) -> str | None:
        calls["audio"] += 1
        return real_audio(ffmpeg, path)

    monkeypatch.setattr(hashing, "file_sha256", counted_sha)
    monkeypatch.setattr(hashing, "audio_hash", counted_audio)

    first = hash_tracks(context, ["t1"], fake_job())
    second = hash_tracks(context, ["t1"], fake_job())

    assert calls == {"sha": 1, "audio": 1}
    assert first.hashed == 1
    assert second.cached == 1 and second.hashed == 0
    assert second.hashes == first.hashes


def test_a_changed_file_is_hashed_again(tmp_path: Path) -> None:
    sample = make_sine(tmp_path / "music" / "tone.flac", seconds=1.0)
    library = FakeLibrary([tmp_path / "music"], [track("t1", sample)])
    context = make_context(tmp_path, library)
    first = hash_tracks(context, ["t1"], fake_job())

    make_sine(sample, seconds=1.5)  # another file at the same path: size and time change

    second = hash_tracks(context, ["t1"], fake_job())
    assert second.hashed == 1
    assert second.hashes["t1"].sha256 != first.hashes["t1"].sha256


def test_an_edit_in_the_same_clock_tick_is_hashed_again(tmp_path: Path) -> None:
    """Two contents of the same size and the same modification time: the cache must not serve one
    hash for both (the racy entry of the cache is hashed again)."""
    sample = make_sine(tmp_path / "music" / "tone.flac")
    library = FakeLibrary([tmp_path / "music"], [track("t1", sample)])
    context = make_context(tmp_path, library)
    now_ns = time.time_ns()
    os.utime(sample, ns=(now_ns, now_ns))
    first = hash_tracks(context, ["t1"], fake_job())

    original = sample.read_bytes()
    sample.write_bytes(original[:-1] + bytes([original[-1] ^ 0xFF]))  # same size, other content
    os.utime(sample, ns=(now_ns, now_ns))  # same modification time
    assert sample.stat().st_size == len(original)

    second = hash_tracks(context, ["t1"], fake_job())

    assert second.hashed == 1 and second.cached == 0
    assert second.hashes["t1"].sha256 == file_sha256(sample)
    assert second.hashes["t1"].sha256 != first.hashes["t1"].sha256


@pytest.mark.parametrize(
    ("age_s", "from_cache"),
    [(0.0, False), (3.0, True)],
    ids=["fresh_file_is_hashed_again", "file_older_than_2s_is_served_from_cache"],
)
def test_a_cache_entry_is_trusted_only_when_the_file_is_older_than_the_racy_margin(
    tmp_path: Path, age_s: float, from_cache: bool
) -> None:
    sample = make_sine(tmp_path / "music" / "tone.flac")
    past_ns = time.time_ns() - int(age_s * 1_000_000_000)
    os.utime(sample, ns=(past_ns, past_ns))
    library = FakeLibrary([tmp_path / "music"], [track("t1", sample)])
    context = make_context(tmp_path, library)

    first = hash_tracks(context, ["t1"], fake_job())
    second = hash_tracks(context, ["t1"], fake_job())

    assert first.hashed == 1
    assert second.cached == (1 if from_cache else 0)
    assert second.hashed == (0 if from_cache else 1)
    assert second.hashes == first.hashes


def test_missing_files_and_tracks_without_a_file_are_skipped_and_counted(tmp_path: Path) -> None:
    present = make_sine(tmp_path / "music" / "here.flac")
    library = FakeLibrary(
        [tmp_path / "music"],
        [track("here", present), track("gone", tmp_path / "music" / "gone.flac")],
    )
    context = make_context(tmp_path, library)

    report = hash_tracks(context, ["here", "gone", "unknown"], fake_job())

    assert set(report.hashes) == {"here"}
    assert report.skipped == {"gone": "missing", "unknown": "unknown"}


def test_several_files_are_hashed_at_once_and_the_workers_open_no_database_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = [
        make_sine(tmp_path / "music" / f"{index}.flac", frequency=200 + 100 * index)
        for index in range(6)
    ]
    for path in files:  # older than the racy margin, so the cache can answer the second call
        os.utime(path, (time.time() - 3600, time.time() - 3600))
    library = FakeLibrary(
        [tmp_path / "music"], [track(f"t{index}", path) for index, path in enumerate(files)]
    )
    context = make_context(tmp_path, library)
    context.database.connection()  # this thread's connection, as a job thread has one
    connections_before = len(context.database._connections)
    running = 0
    most = 0
    guard = threading.Lock()
    real = hashing.audio_hash

    def slow(ffmpeg: Path, path: Path) -> str | None:
        nonlocal running, most
        with guard:
            running += 1
            most = max(most, running)
        time.sleep(0.2)
        try:
            return real(ffmpeg, path)
        finally:
            with guard:
                running -= 1

    monkeypatch.setattr(hashing, "audio_hash", slow)
    job = FakeJob()

    report = hash_tracks(context, [f"t{index}" for index in range(6)], cast(JobContext, job))

    assert report.hashed == 6 and report.skipped == {}
    assert most == hashing.HASH_WORKERS
    assert job.progress == [index / 6 for index in range(1, 7)]
    assert len(context.database._connections) == connections_before, "workers read files only"
    # Stored on this thread: the next call answers from the cache.
    assert hash_tracks(context, ["t0"], cast(JobContext, FakeJob())).cached == 1

"""Detection of the ordinary modifications of a source file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mtee.domain.tracks import SourceRevision, TrackId, sha256_of_file


def _write(path: Path, content: bytes, mtime_ns: int) -> None:
    path.write_bytes(content)
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_two_copies_of_the_same_audio_own_two_identifiers() -> None:
    first = TrackId.new()
    second = TrackId.new()

    assert first != second
    assert TrackId.parse(str(first)) == first


def test_parse_refuses_a_text_that_is_not_an_identifier() -> None:
    with pytest.raises(ValueError):
        TrackId.parse("not-a-uuid")


def test_an_unchanged_file_matches_its_revision(tmp_path: Path) -> None:
    track = tmp_path / "track.flac"
    _write(track, b"audio", 1_700_000_000_000_000_000)
    recorded = SourceRevision.observe(track)

    assert recorded.matches(SourceRevision.observe(track))
    assert not recorded.looks_modified(SourceRevision.observe(track))


def test_a_rewritten_file_looks_modified(tmp_path: Path) -> None:
    track = tmp_path / "track.flac"
    _write(track, b"audio", 1_700_000_000_000_000_000)
    recorded = SourceRevision.observe(track)

    _write(track, b"audio-edited", 1_700_000_500_000_000_000)

    assert recorded.looks_modified(SourceRevision.observe(track))


def test_a_file_rewritten_at_the_same_size_and_date_is_not_detected(tmp_path: Path) -> None:
    """The revision is an observation, not a proof of content: SHA-256 decides."""
    track = tmp_path / "track.flac"
    _write(track, b"aaaaa", 1_700_000_000_000_000_000)
    recorded = SourceRevision.observe(track)
    first_digest = sha256_of_file(track)

    _write(track, b"bbbbb", 1_700_000_000_000_000_000)

    assert recorded.matches(SourceRevision.observe(track))
    assert first_digest != sha256_of_file(track)


def test_file_id_difference_is_a_modification_when_both_are_known() -> None:
    recorded = SourceRevision(size_bytes=10, mtime_ns=5, file_id="C:1")
    moved = SourceRevision(size_bytes=10, mtime_ns=5, file_id="C:2")

    assert recorded.looks_modified(moved)


def test_missing_file_id_does_not_invent_a_modification() -> None:
    recorded = SourceRevision(size_bytes=10, mtime_ns=5, file_id="C:1")
    without_id = SourceRevision(size_bytes=10, mtime_ns=5, file_id=None)

    assert recorded.matches(without_id)


def test_generation_records_our_own_mutations_and_not_the_bytes() -> None:
    recorded = SourceRevision(size_bytes=10, mtime_ns=5, file_id="C:1")

    bumped = recorded.bumped()

    assert bumped.generation == recorded.generation + 1
    assert recorded.matches(bumped)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size_bytes": -1, "mtime_ns": 0},
        {"size_bytes": 0, "mtime_ns": -1},
        {"size_bytes": 0, "mtime_ns": 0, "generation": -1},
        {"size_bytes": 0, "mtime_ns": 0, "file_id": ""},
    ],
)
def test_an_impossible_observation_is_refused(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SourceRevision(**kwargs)  # type: ignore[arg-type]


def test_observing_a_missing_file_reports_the_system_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SourceRevision.observe(tmp_path / "absent.flac")

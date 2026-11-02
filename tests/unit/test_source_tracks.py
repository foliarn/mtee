"""The value types of tracks without a file, and how the mpv backend writes their headers."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.domain.source_tracks import (
    NonFileTrackError,
    PlayableSource,
    SourceTrack,
    is_non_file_row,
    non_file_message,
    require_file_track,
    row_is_available,
)
from mtee.services.mpv_backend import _header_list, _target_of


def test_a_source_track_normalizes_its_values_and_converts_to_a_tag_snapshot() -> None:
    track = SourceTrack(
        " key-1 ",
        " Song ",
        artists="Ann",  # type: ignore[arg-type]
        album="Album",
        track_number=4,
        duration_us=61_000_000,
        genre=["Dub", " ", "Roots"],  # type: ignore[arg-type]
        year=2020,
    )
    assert track.source_key == "key-1" and track.title == "Song"
    assert track.artists == ("Ann",) and track.genre == ("Dub", "Roots")
    snapshot = track.snapshot()
    assert snapshot.title == ("Song",) and snapshot.artist == ("Ann",)
    assert snapshot.date == ("2020",) and snapshot.track_number == ("4",)
    assert snapshot.technical.duration_us == 61_000_000
    assert SourceTrack.from_snapshot("key-1", snapshot, "") == track


@pytest.mark.parametrize(
    "arguments",
    [
        {"source_key": "", "title": "x"},
        {"source_key": "   ", "title": "x"},
        {"source_key": "k" * 513, "title": "x"},
        {"source_key": "k", "title": "x" * 2001},
        {"source_key": "k", "title": "x", "duration_us": -1},
        {"source_key": "k", "title": "x", "track_number": -2},
        {"source_key": "k", "title": "x", "year": True},
    ],
)
def test_an_invalid_source_track_is_refused(arguments: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        SourceTrack(**arguments)  # type: ignore[arg-type]


def test_a_playable_source_is_a_path_or_a_url() -> None:
    assert PlayableSource(path=Path("a.flac")).path == Path("a.flac")
    source = PlayableSource(
        url="https://example.test/a.flac", headers={"Authorization": "Bearer x"}
    )
    assert source.headers == {"Authorization": "Bearer x"}
    with pytest.raises(ValueError):
        PlayableSource()
    with pytest.raises(ValueError):
        PlayableSource(path=Path("a"), url="http://example.test/a")
    with pytest.raises(ValueError, match="Headers go with a url"):
        PlayableSource(path=Path("a"), headers={"X-A": "b"})


@pytest.mark.parametrize(
    "url",
    ["ftp://example.test/a", "file:///C:/a.flac", "example.test/a", "http:///a", "http://a\nb/"],
)
def test_only_http_and_https_urls_are_accepted(url: str) -> None:
    with pytest.raises(ValueError):
        PlayableSource(url=url)


@pytest.mark.parametrize(
    "headers",
    [
        {"Bad Name": "x"},
        {"X-A": "line\r\nInjected: yes"},
        {"X-A": "tab\there"},
        {"X-A": "ends with a backslash \\"},
        {"": "x"},
    ],
)
def test_unsafe_headers_are_refused(headers: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        PlayableSource(url="http://example.test/a", headers=headers)


def test_the_repr_never_shows_a_secret() -> None:
    source = PlayableSource(
        url="https://user:pw@example.test/a.flac?token=SECRET",
        headers={"Authorization": "Bearer SECRET"},
    )
    text = repr(source)
    assert "SECRET" not in text and "pw" not in text
    assert "Authorization" in text and "example.test" in text


def test_a_track_row_without_a_file_is_recognized() -> None:
    row = {"sourcePluginId": "remote", "sourceKey": "k", "status": "readable"}
    assert is_non_file_row(row) and row_is_available(row)
    assert not row_is_available({**row, "status": "unreadable"})
    assert not is_non_file_row({"path": "C:/a.wav", "status": "readable"})
    assert not row_is_available({"path": "C:/a.wav", "status": "readable"})
    with pytest.raises(NonFileTrackError, match="Remote"):
        require_file_track(row, "moved", "Remote")
    require_file_track({"path": "C:/a.wav"}, "moved")  # a file track passes
    assert non_file_message("Remote", "moved") == (
        "This track is provided by Remote and has no file on this computer, so it cannot be moved."
    )


# --- what libmpv receives, measured on the pinned runtime (see _header_list) -------------------


def test_a_file_or_a_url_is_what_loadfile_opens() -> None:
    assert _target_of(Path("C:/music/a.flac")) == str(Path("C:/music/a.flac"))
    assert _target_of(PlayableSource(path=Path("a.flac"))) == "a.flac"
    assert _target_of(PlayableSource(url="http://h/a.flac")) == "http://h/a.flac"


def test_a_source_without_headers_has_an_empty_header_list() -> None:
    assert _header_list(Path("a.flac")) == ""
    assert _header_list(PlayableSource(path=Path("a.flac"))) == ""
    assert _header_list(PlayableSource(url="http://h/a.flac")) == ""


def test_headers_are_a_comma_list_with_commas_in_values_escaped() -> None:
    source = PlayableSource(
        url="http://h/a.flac",
        headers={"Authorization": "Bearer abc.def-1", "X-Test": "ü, b; c=d", "X-Back": "a\\b"},
    )
    # Colons and semicolons need no care; a comma is written \, and a backslash stays as it is.
    assert _header_list(source) == (
        "Authorization: Bearer abc.def-1,X-Test: ü\\, b; c=d,X-Back: a\\b"
    )

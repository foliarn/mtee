"""What the server knows about a file (plan 127.0): MTEE's metadata, else ffprobe."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import make_audio
from mtee_remote import tools
from mtee_remote.library.hashing import read_metadata
from mtee_remote.streaming.source_info import from_metadata, is_lossless, probe, source_info
from mtee_remote.streaming.types import SourceInfo


def _technical(**fields: object) -> str:
    return json.dumps({"technical": fields})


# -- real files: the metadata and ffprobe agree --------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "codec", "rate", "depth"),
    [
        ("flac", "flac", 44100, 16),
        ("wav", "pcm_s16le", 44100, 16),
        ("aiff", "pcm_s16be", 44100, 16),
        ("mp3", "mp3", 44100, None),
        ("ogg", "vorbis", 44100, None),
        ("opus", "opus", 48000, None),
    ],
)
def test_metadata_and_probe_agree(
    tmp_path: Path, fmt: str, codec: str, rate: int, depth: int | None
) -> None:
    path = make_audio(tmp_path / f"tone.{fmt}", fmt)
    text, _ = read_metadata(path)
    from_tags = from_metadata(text)
    probed = probe(path)
    assert from_tags is not None
    assert from_tags.codec == probed.codec == codec
    assert from_tags.lossless == probed.lossless == is_lossless(codec)
    assert from_tags.sample_rate == probed.sample_rate == rate
    assert from_tags.bit_depth == probed.bit_depth == depth
    assert probed.channels == 1


def test_mp4_is_left_to_the_probe(tmp_path: Path) -> None:
    # MTEE reports "MP4" for AAC and ALAC alike, so the metadata does not name the codec.
    path = make_audio(tmp_path / "tone.m4a", "m4a")
    text, _ = read_metadata(path)
    assert from_metadata(text) is None
    assert source_info(path, text).codec == "aac"
    assert source_info(path, text).lossless is False


def test_metadata_is_used_before_the_probe(tmp_path: Path) -> None:
    # The file does not exist: an answer can only come from the metadata.
    text = _technical(codec="FLAC", bits_per_sample=24, sample_rate=96000, bitrate=4_600_000)
    found = source_info(tmp_path / "missing.flac", text)
    assert found.codec == "flac"
    assert found.bit_depth == 24


def test_the_probe_is_the_fallback(tmp_path: Path) -> None:
    path = make_audio(tmp_path / "tone.flac", "flac")
    assert source_info(path, None) == probe(path)


# -- from_metadata ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codec", "bits", "expected"),
    [
        ("FLAC", 24, "flac"),
        ("EasyMP3", None, "mp3"),
        ("OggVorbis", None, "vorbis"),
        ("OggOpus", None, "opus"),
        ("AAC", None, "aac"),
        ("WavPack", None, "wavpack"),
        ("TrueAudio", 16, "tta"),
        ("MonkeysAudio", 16, "ape"),
        ("WAVE", 16, "pcm_s16le"),
        ("WAVE", 24, "pcm_s24le"),
        ("WAVE", 8, "pcm_u8"),
        ("WAVE", 32, None),  # integer or float: the probe decides
        ("AIFF", 24, "pcm_s24be"),
        ("AIFF", 8, "pcm_s8"),
        ("WAVE", None, None),
        ("EasyMP4", 24, None),  # AAC or ALAC: the probe decides
        ("Musepack", None, None),
        ("", None, None),
    ],
)
def test_codec_names_map_to_ffmpeg_names(
    codec: str, bits: int | None, expected: str | None
) -> None:
    found = from_metadata(_technical(codec=codec, bits_per_sample=bits, sample_rate=44100))
    if expected is None:
        assert found is None
    else:
        assert found is not None
        assert found.codec == expected
        assert found.lossless is is_lossless(expected)


def test_zero_and_missing_numbers_are_none() -> None:
    found = from_metadata(_technical(codec="EasyMP3", bits_per_sample=0, sample_rate=0, bitrate=0))
    assert found == SourceInfo("mp3", False, None, None, None, None)


def test_opus_gets_its_48_kilohertz_rate_when_the_metadata_has_none() -> None:
    found = from_metadata(_technical(codec="OggOpus", bitrate=128_000))
    assert found == SourceInfo("opus", False, 48000, None, 128_000, None)


def test_a_tag_file_without_technical_part_gives_none() -> None:
    assert from_metadata(None) is None
    assert from_metadata("") is None
    assert from_metadata("not json") is None
    assert from_metadata("[]") is None
    assert from_metadata('{"technical": 3}') is None


# -- probe -----------------------------------------------------------------------------------


def test_probe_refuses_a_file_that_is_not_audio(tmp_path: Path) -> None:
    path = tmp_path / "notes.flac"
    path.write_text("this is not audio", encoding="utf-8")
    with pytest.raises(RuntimeError):
        probe(path)


def test_probe_reads_the_bitrate_from_the_format_when_the_stream_has_none(tmp_path: Path) -> None:
    path = make_audio(tmp_path / "tone.flac", "flac")
    found = probe(path)
    assert found.bitrate is not None and found.bitrate > 0


# -- ffprobe location -------------------------------------------------------------------------


def test_the_environment_names_ffprobe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MTEE_REMOTE_FFPROBE", str(tmp_path / "custom-probe"))
    assert tools.ffprobe_path() == str(tmp_path / "custom-probe")


def test_ffprobe_is_found_next_to_ffmpeg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = tmp_path / "bin"
    folder.mkdir()
    ffmpeg = folder / "ffmpeg.exe"
    ffprobe = folder / "ffprobe.exe"
    ffmpeg.write_bytes(b"")
    ffprobe.write_bytes(b"")
    monkeypatch.delenv("MTEE_REMOTE_FFPROBE", raising=False)
    monkeypatch.setenv("MTEE_REMOTE_FFMPEG", str(ffmpeg))
    assert tools.ffprobe_path() == str(ffprobe)


def test_a_missing_ffprobe_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MTEE_REMOTE_FFPROBE", raising=False)
    monkeypatch.delenv("MTEE_REMOTE_FFMPEG", raising=False)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(RuntimeError):
        tools.ffprobe_path()

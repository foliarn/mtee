"""The audio payload parser: the span stays the same when only the tags change.

Real small files are made by the bundled ffmpeg (one second of sine wave) and retagged with
mutagen on copies in a temporary folder. A format is skipped when ffmpeg is not available.
"""

from __future__ import annotations

import hashlib
import struct
import subprocess
from pathlib import Path

import pytest
from mutagen.aiff import AIFF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, COMM, TIT2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE

from mtee.services.audio_payload import (
    MAX_TAG_BYTES,
    Span,
    payload_span,
    read_tag_parts,
    span_sha256,
    tag_bytes_size,
)
from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError

LONG_COMMENT = "A long comment about this track. " * 3000  # about 96 KB
FAKE_COVER = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 200  # about 50 KB

# format -> (encoder arguments, ffmpeg muxer, extra output arguments)
_FORMATS: dict[str, tuple[list[str], str, list[str]]] = {
    "flac": (["-c:a", "flac"], "flac", []),
    "mp3": (["-c:a", "libmp3lame", "-b:a", "128k"], "mp3", []),
    "wav": (["-c:a", "pcm_s16le"], "wav", []),
    "aiff": (["-c:a", "pcm_s16be", "-write_id3v2", "1"], "aiff", []),
    # The moov atom first, so a longer tag moves the mdat atom.
    "m4a": (["-c:a", "aac", "-b:a", "128k"], "ipod", ["-movflags", "+faststart"]),
}


def _ffmpeg() -> str:
    try:
        return str(FfmpegRuntime().executable("ffmpeg"))
    except FfmpegRuntimeError:
        pytest.skip("The bundled ffmpeg is missing.")


def make_file(path: Path, fmt: str, seconds: float = 1.0) -> Path:
    codec, muxer, extra = _FORMATS[fmt]
    subprocess.run(
        [
            _ffmpeg(),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            *codec,
            *extra,
            "-f",
            muxer,
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retag(path: Path, fmt: str) -> None:
    """Change the title, add a long comment and a cover so that the tag size changes."""
    if fmt == "flac":
        flac = FLAC(path)
        flac["title"] = "A new title"
        flac["comment"] = LONG_COMMENT
        picture = Picture()
        picture.type = 3
        picture.mime = "image/png"
        picture.data = FAKE_COVER
        flac.add_picture(picture)
        flac.save()
    elif fmt in ("mp3", "wav", "aiff"):
        audio = {"mp3": MP3, "wav": WAVE, "aiff": AIFF}[fmt](path)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        assert tags is not None
        tags.add(TIT2(encoding=3, text=["A new title"]))
        tags.add(COMM(encoding=3, lang="eng", desc="", text=[LONG_COMMENT]))
        tags.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=FAKE_COVER))
        audio.save()
    else:
        mp4 = MP4(path)
        assert mp4.tags is not None
        mp4.tags["\xa9nam"] = ["A new title"]
        mp4.tags["\xa9cmt"] = [LONG_COMMENT]
        mp4.tags["covr"] = [MP4Cover(FAKE_COVER, imageformat=MP4Cover.FORMAT_PNG)]
        mp4.save()


@pytest.mark.parametrize(
    ("fmt", "moves"),
    [("flac", True), ("mp3", True), ("wav", False), ("aiff", False), ("m4a", True)],
)
def test_the_payload_hash_survives_a_retag(tmp_path: Path, fmt: str, moves: bool) -> None:
    path = make_file(tmp_path / f"song.{fmt}", fmt)
    before = payload_span(path)
    assert before is not None
    payload_hash = span_sha256(path, before)
    whole_hash = file_sha256(path)

    retag(path, fmt)

    after = payload_span(path)
    assert after is not None
    assert after.length == before.length
    assert span_sha256(path, after) == payload_hash
    assert file_sha256(path) != whole_hash
    if moves:
        assert after.offset != before.offset


@pytest.mark.parametrize("fmt", ["flac", "mp3", "wav", "aiff", "m4a"])
def test_the_file_is_prefix_payload_suffix(tmp_path: Path, fmt: str) -> None:
    path = make_file(tmp_path / f"song.{fmt}", fmt)
    retag(path, fmt)
    span = payload_span(path)
    assert span is not None
    prefix, suffix = read_tag_parts(path, span)
    data = path.read_bytes()
    assert len(prefix) == span.offset
    assert prefix + data[span.offset : span.offset + span.length] + suffix == data
    assert tag_bytes_size(path, span) == len(prefix) + len(suffix) == len(data) - span.length
    assert tag_bytes_size(path, span) < MAX_TAG_BYTES


def test_a_longer_wav_info_chunk_moves_the_data_chunk(tmp_path: Path) -> None:
    source = make_file(tmp_path / "plain.wav", "wav")
    tagged = tmp_path / "tagged.wav"
    subprocess.run(
        [
            _ffmpeg(),
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-c",
            "copy",
            "-metadata",
            "title=" + "x" * 500,
            str(tagged),
        ],
        check=True,
        capture_output=True,
    )
    a, b = payload_span(source), payload_span(tagged)
    assert a is not None and b is not None
    assert a.offset != b.offset
    assert span_sha256(source, a) == span_sha256(tagged, b)


def test_mp3_with_id3v1_and_apev2_trailers(tmp_path: Path) -> None:
    path = make_file(tmp_path / "song.mp3", "mp3")
    plain = payload_span(path)
    assert plain is not None
    payload_hash = span_sha256(path, plain)

    item = struct.pack("<II", 5, 0) + b"Title\x00" + b"hello"
    footer_fields = struct.pack("<II", 2000, len(item) + 32)
    ape_footer = b"APETAGEX" + footer_fields + struct.pack("<II", 1, 0x80000000) + bytes(8)
    ape_header = b"APETAGEX" + footer_fields + struct.pack("<II", 1, 0xA0000000) + bytes(8)
    id3v1 = b"TAG" + b"Title".ljust(30, b"\x00") + bytes(95)
    assert len(id3v1) == 128

    original = path.read_bytes()
    audio = original[plain.offset : plain.offset + plain.length]

    # APEv2 with a header, then ID3v1.
    path.write_bytes(original[: plain.offset] + audio + ape_header + item + ape_footer + id3v1)
    span = payload_span(path)
    assert span == plain
    assert span is not None and span_sha256(path, span) == payload_hash

    # APEv2 alone, without a header, at the end of the file.
    flag_no_header = b"APETAGEX" + footer_fields + struct.pack("<II", 1, 0) + bytes(8)
    path.write_bytes(original[: plain.offset] + audio + item + flag_no_header)
    assert payload_span(path) == plain

    # ID3v1 alone.
    path.write_bytes(original[: plain.offset] + audio + id3v1)
    assert payload_span(path) == plain


def test_flac_with_an_id3v2_prefix(tmp_path: Path) -> None:
    path = make_file(tmp_path / "song.flac", "flac")
    plain = payload_span(path)
    assert plain is not None
    body = 1000
    size_bytes = bytes([(body >> 21) & 0x7F, (body >> 14) & 0x7F, (body >> 7) & 0x7F, body & 0x7F])
    id3 = b"ID3\x04\x00\x00" + size_bytes + bytes(body)
    path.write_bytes(id3 + path.read_bytes())
    span = payload_span(path)
    assert span == Span(plain.offset + len(id3), plain.length)


def test_mp3_with_an_id3v2_footer(tmp_path: Path) -> None:
    path = make_file(tmp_path / "song.mp3", "mp3")
    original = path.read_bytes()
    span = payload_span(path)
    assert span is not None
    audio = original[span.offset : span.offset + span.length]
    id3 = b"ID3\x04\x00\x10" + bytes([0, 0, 0, 20]) + bytes(20) + b"3DI\x04\x00\x10" + bytes(4)
    path.write_bytes(id3 + audio)
    assert payload_span(path) == Span(len(id3), len(audio))


def test_mp4_with_two_mdat_atoms_has_no_payload(tmp_path: Path) -> None:
    path = make_file(tmp_path / "song.m4a", "m4a")
    assert payload_span(path) is not None
    with open(path, "ab") as handle:
        handle.write(struct.pack(">I4s", 12, b"mdat") + b"abcd")
    assert payload_span(path) is None


def test_mp4_without_mdat_and_with_large_or_open_ended_atoms(tmp_path: Path) -> None:
    ftyp = struct.pack(">I4s", 16, b"ftyp") + b"M4A \x00\x00\x00\x00"
    path = tmp_path / "x.m4a"
    path.write_bytes(ftyp + struct.pack(">I4s", 8, b"moov"))
    assert payload_span(path) is None
    # size 1: an 8-byte size follows.
    path.write_bytes(ftyp + struct.pack(">I4sQ", 1, b"mdat", 16 + 5) + b"hello")
    assert payload_span(path) == Span(16 + 16, 5)
    # size 0: the atom runs to the end of the file.
    path.write_bytes(ftyp + struct.pack(">I4s", 0, b"mdat") + b"world!")
    assert payload_span(path) == Span(16 + 8, 6)
    # a size that runs past the end of the file.
    path.write_bytes(ftyp + struct.pack(">I4s", 500, b"mdat") + b"short")
    assert payload_span(path) is None


def _riff(chunks: list[tuple[bytes, bytes]], *, big_endian: bool = False) -> bytes:
    order = ">" if big_endian else "<"
    body = b""
    for chunk_id, payload in chunks:
        body += chunk_id + struct.pack(f"{order}I", len(payload)) + payload
        if len(payload) % 2:
            body += b"\x00"
    if big_endian:
        return b"FORM" + struct.pack(">I", len(body) + 4) + b"AIFF" + body
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


def test_wav_chunks_with_odd_padding_and_a_list_chunk_after_the_data(tmp_path: Path) -> None:
    path = tmp_path / "x.wav"
    data = b"\x01\x02\x03\x04\x05"  # odd length: a pad byte follows
    path.write_bytes(
        _riff([(b"fmt ", bytes(16)), (b"JUNK", b"abc"), (b"data", data), (b"LIST", b"INFOxx")])
    )
    span = payload_span(path)
    assert span is not None
    assert path.read_bytes()[span.offset : span.offset + span.length] == data
    prefix, suffix = read_tag_parts(path, span)
    assert suffix.startswith(b"\x00LIST")
    assert prefix.endswith(b"data" + struct.pack("<I", 5))


def test_aiff_ssnd_chunk_with_big_endian_sizes(tmp_path: Path) -> None:
    path = tmp_path / "x.aiff"
    sound = bytes(range(40))
    path.write_bytes(
        _riff([(b"COMM", bytes(18)), (b"SSND", sound), (b"ID3 ", b"tag")], big_endian=True)
    )
    span = payload_span(path)
    assert span is not None
    assert path.read_bytes()[span.offset : span.offset + span.length] == sound


def test_a_truncated_wav_has_no_payload(tmp_path: Path) -> None:
    path = make_file(tmp_path / "song.wav", "wav")
    assert payload_span(path) is not None
    path.write_bytes(path.read_bytes()[:-100])
    assert payload_span(path) is None


def test_rf64_has_no_payload(tmp_path: Path) -> None:
    path = tmp_path / "x.wav"
    path.write_bytes(b"RF64" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE" + bytes(100))
    assert payload_span(path) is None


def test_a_truncated_flac_header_has_no_payload(tmp_path: Path) -> None:
    path = make_file(tmp_path / "song.flac", "flac")
    path.write_bytes(path.read_bytes()[:30])
    assert payload_span(path) is None


def test_flac_whose_audio_is_not_a_frame_has_no_payload(tmp_path: Path) -> None:
    path = make_file(tmp_path / "song.flac", "flac")
    span = payload_span(path)
    assert span is not None
    data = bytearray(path.read_bytes())
    data[span.offset] = 0x00
    path.write_bytes(bytes(data))
    assert payload_span(path) is None


def test_mp3_whose_audio_does_not_start_with_a_frame_has_no_payload(tmp_path: Path) -> None:
    path = tmp_path / "x.mp3"
    path.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x05" + b"\x00" * 5 + b"not audio at all" * 20)
    assert payload_span(path) is None


@pytest.mark.parametrize("content", [b"", b"x", b"hello world" * 100, bytes(200), b"\xff" * 64])
def test_garbage_has_no_payload(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "garbage.bin"
    path.write_bytes(content)
    assert payload_span(path) is None


def test_the_format_comes_from_the_content_not_the_extension(tmp_path: Path) -> None:
    source = make_file(tmp_path / "song.flac", "flac")
    renamed = tmp_path / "song.mp3"
    renamed.write_bytes(source.read_bytes())
    assert payload_span(renamed) == payload_span(source)


def test_a_missing_file_raises_os_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        payload_span(tmp_path / "missing.flac")


def test_read_tag_parts_refuses_a_span_beyond_the_file(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    with pytest.raises(ValueError):
        read_tag_parts(path, Span(1, 10))
    with pytest.raises(ValueError):
        span_sha256(path, Span(1, 10))

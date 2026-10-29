"""ISRC is read from each supported container, normalized, and never written."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import TSRC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4FreeForm
from mutagen.ogg import OggPage
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from mtee.domain.metadata import MetadataSnapshot, normalize_isrc
from mtee.services.metadata_reader import MetadataReader

_VALID = "USRC17607839"


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _full_box(kind: bytes, payload: bytes = b"") -> bytes:
    return _box(kind, struct.pack(">I", 0) + payload)


def _mp3(path: Path, isrc: str | None) -> None:
    # Constant 128 kbps MPEG-1 Layer III frames at 44.1 kHz, with silent payloads.
    path.write_bytes((bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(413)) * 40)
    audio = MP3(path)
    audio.add_tags()
    assert audio.tags is not None
    if isrc is not None:
        audio.tags.add(TSRC(encoding=3, text=[isrc]))
    audio.save()


def _flac(path: Path, isrc: str | None) -> None:
    stream_info = (
        struct.pack(">HH", 4096, 4096)
        + bytes(6)
        + ((44_100 << 44) | (1 << 41) | (15 << 36) | 44_100).to_bytes(8, "big")
        + bytes(16)
    )
    path.write_bytes(b"fLaC" + bytes([0x80]) + (34).to_bytes(3, "big") + stream_info)
    audio = FLAC(path)
    audio.add_tags()
    if isrc is not None:
        audio["ISRC"] = [isrc]
    audio.save()


def _ogg_pages(first: bytes, second: bytes) -> bytes:
    """Two Ogg pages on one logical stream: the identification and the comment header."""
    head = OggPage.from_packets([first], 0)[0]
    head.first = True
    comments = OggPage.from_packets([second], 1)[0]
    comments.serial = head.serial
    comments.first = False
    return head.write() + comments.write()


def _ogg_vorbis(path: Path, isrc: str | None) -> None:
    identification = (
        b"\x01vorbis"
        + struct.pack("<IB", 0, 1)
        + struct.pack("<I", 44_100)
        + struct.pack("<iii", 0, 128_000, 0)
        + bytes([0xB8, 0x01, 0x01])
    )
    comments = b"\x03vorbis" + struct.pack("<I", 4) + b"mtee" + struct.pack("<I", 0) + b"\x01"
    path.write_bytes(_ogg_pages(identification, comments))
    audio = OggVorbis(path)
    if isrc is not None:
        audio["ISRC"] = [isrc]
    audio.save()


def _opus(path: Path, isrc: str | None) -> None:
    head = b"OpusHead" + bytes([1, 2]) + struct.pack("<HIhB", 312, 48_000, 0, 0)
    tags = b"OpusTags" + struct.pack("<I", 4) + b"mtee" + struct.pack("<I", 0)
    path.write_bytes(_ogg_pages(head, tags))
    audio = OggOpus(path)
    if isrc is not None:
        audio["ISRC"] = [isrc]
    audio.save()


def _m4a(path: Path, isrc: str | None) -> None:
    """A silent AAC-LC track with no samples, enough for Mutagen to read its tags."""
    ftyp = _box(b"ftyp", b"M4A " + struct.pack(">I", 0) + b"M4A mp42isom")
    mvhd = _full_box(
        b"mvhd",
        struct.pack(">IIII", 0, 0, 44_100, 44_100)
        + struct.pack(">IHH", 0x10000, 0x100, 0)
        + bytes(8)
        + bytes(36)
        + bytes(24)
        + struct.pack(">I", 2),
    )
    mdhd = _full_box(b"mdhd", struct.pack(">IIIIHH", 0, 0, 44_100, 44_100, 0x55C4, 0))
    hdlr = _full_box(b"hdlr", struct.pack(">I", 0) + b"soun" + bytes(12) + b"\x00")
    smhd = _full_box(b"smhd", struct.pack(">HH", 0, 0))
    self_contained_url = _box(b"url ", struct.pack(">I", 1))
    dinf = _box(b"dinf", _full_box(b"dref", struct.pack(">I", 1) + self_contained_url))
    esds_body = b"".join(
        [
            bytes([0x03, 0x19]),
            struct.pack(">HB", 1, 0),
            bytes([0x04, 0x11, 0x40, 0x15]),
            bytes(3),
            struct.pack(">II", 0, 0),
            bytes([0x05, 0x02, 0x12, 0x10]),
            bytes([0x06, 0x01, 0x02]),
        ]
    )
    mp4a = _box(
        b"mp4a",
        bytes(6)
        + struct.pack(">H", 1)
        + bytes(8)
        + struct.pack(">HHHHI", 2, 16, 0, 0, 44_100 << 16)
        + _full_box(b"esds", esds_body),
    )
    stsd = _full_box(b"stsd", struct.pack(">I", 1) + mp4a)
    stbl = _box(
        b"stbl",
        stsd
        + _full_box(b"stts", struct.pack(">I", 0))
        + _full_box(b"stsc", struct.pack(">I", 0))
        + _full_box(b"stsz", struct.pack(">II", 0, 0))
        + _full_box(b"stco", struct.pack(">I", 0)),
    )
    minf = _box(b"minf", smhd + dinf + stbl)
    moov = _box(b"moov", mvhd + _box(b"trak", _box(b"mdia", mdhd + hdlr + minf)))
    path.write_bytes(ftyp + moov + _box(b"mdat", bytes(16)))
    audio = MP4(path)
    audio.add_tags()
    assert audio.tags is not None
    if isrc is not None:
        audio.tags["----:com.apple.iTunes:ISRC"] = [MP4FreeForm(isrc.encode("utf-8"))]
    audio.save()


_BUILDERS = {
    "mp3": ("track.mp3", _mp3),
    "flac": ("track.flac", _flac),
    "ogg": ("track.ogg", _ogg_vorbis),
    "opus": ("track.opus", _opus),
    "m4a": ("track.m4a", _m4a),
}


def _build(tmp_path: Path, container: str, isrc: str | None) -> Path:
    name, builder = _BUILDERS[container]
    path = tmp_path / name
    builder(path, isrc)
    return path


@pytest.mark.parametrize("container", sorted(_BUILDERS))
@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (_VALID, _VALID),
        ("US-RC1-76-07839", _VALID),
        ("usrc17607839", _VALID),
        ("  US RC1 76 07839 ", _VALID),
        ("USRC1760783", None),
        ("USRC176078390", None),
        ("1SRC17607839", None),
        ("USRC1760783X", None),
        ("", None),
    ],
)
def test_reads_normalized_isrc_from_each_container(
    tmp_path: Path, container: str, stored: str, expected: str | None
) -> None:
    path = _build(tmp_path, container, stored)
    before = path.read_bytes()

    snapshot = MetadataReader().read(path)

    assert snapshot.status == "readable", snapshot.error
    assert snapshot.isrc == expected
    assert path.read_bytes() == before


@pytest.mark.parametrize("container", sorted(_BUILDERS))
def test_missing_isrc_reads_as_none(tmp_path: Path, container: str) -> None:
    path = _build(tmp_path, container, None)

    snapshot = MetadataReader().read(path)

    assert snapshot.status == "readable", snapshot.error
    assert snapshot.isrc is None


def test_normalize_isrc_accepts_only_twelve_character_codes() -> None:
    assert normalize_isrc(" gb-ayE-06-01498 ") == "GBAYE0601498"
    assert normalize_isrc("GBAYE060149") is None
    assert normalize_isrc("GBAYE06014988") is None
    assert normalize_isrc("GB AYE 06 0149X") is None
    assert normalize_isrc(None) is None


def test_snapshot_round_trips_isrc_through_json() -> None:
    snapshot = MetadataSnapshot(title=("Song",), isrc=_VALID)

    stored = json.dumps(snapshot.to_dict(), sort_keys=True)
    restored = MetadataSnapshot.from_dict(json.loads(stored))

    assert restored == snapshot
    assert restored.isrc == _VALID


def test_snapshot_json_without_isrc_key_loads_with_none() -> None:
    stored = MetadataSnapshot(title=("Song",)).to_dict()
    del stored["isrc"]

    restored = MetadataSnapshot.from_dict(json.loads(json.dumps(stored)))

    assert restored.isrc is None
    assert restored.title == ("Song",)


def test_snapshot_json_with_malformed_isrc_loads_as_none() -> None:
    stored = MetadataSnapshot(title=("Song",)).to_dict()
    stored["isrc"] = "not-an-isrc"

    assert MetadataSnapshot.from_dict(stored).isrc is None

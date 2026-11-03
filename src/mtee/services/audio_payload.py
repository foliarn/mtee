"""Find the audio payload of a file, so that only its tag parts have to travel.

When two machines hold the same audio under different tags (the server copy predates the
tagging done on this computer), sending the whole file is a waste: the audio bytes are the
same, only the bytes around them differ. This module finds the ONE contiguous byte range that
holds the audio payload of a file, by reading the structure of the container, never by trusting
the extension:

- FLAC: after the optional ID3v2 tag, "fLaC" and the metadata blocks; the payload runs from the
  end of the last metadata block to the end of the file.
- MP3 (MPEG audio): after the optional ID3v2 tag(s), up to the start of the ID3v1 tag and/or
  the APEv2 tag at the end of the file. The first bytes must be an MPEG frame header.
- WAV ("RIFF"/"WAVE", not RF64): the payload of the first `data` chunk.
- AIFF / AIFC: the payload of the `SSND` chunk.
- MP4 / M4A: the payload of the single top-level `mdat` atom (none or several: no payload).

Everything before the payload (prefix) and after it (suffix) is the "tag part". A file is
exactly `prefix + payload + suffix`, so a machine that already holds the payload can rebuild the
whole file from the two small parts, and check the result against the SHA-256 of the whole file.

The server (which installs the core without Qt) and the Remote plugin both use this code, so it
lives in the core, in plain standard-library Python. Two machines agree on a split only when they
run the same parser; if a tagger changed bytes inside the span the SHA-256 of the span differs
and the caller falls back to a normal full transfer.

Error policy: `payload_span` returns None for any content it does not understand (unknown
format, truncated file, inconsistent sizes, an empty payload, a second `mdat`...). It never
raises for bad content. An `OSError` (file missing, locked, unreadable) is not content: it
propagates, and the caller decides what a busy file means.

Size cap: the tag parts are read into memory by `read_tag_parts`. A WAV can carry a big `LIST`
chunk after a huge `data` chunk, so a caller must check `tag_bytes_size(path, span)` against
`MAX_TAG_BYTES` and send the whole file instead when the parts are larger.
"""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

__all__ = [
    "MAX_TAG_BYTES",
    "Span",
    "payload_span",
    "read_tag_parts",
    "span_sha256",
    "tag_bytes_size",
]

# Above this many bytes of tag parts (prefix + suffix), callers should not splice.
MAX_TAG_BYTES = 64 * 1024 * 1024

_BLOCK = 1024 * 1024
_ID3V2_HEADER = 10
_ID3V1_SIZE = 128
_APE_FOOTER = 32
_MAX_ID3V2_TAGS = 4


@dataclass(frozen=True, slots=True)
class Span:
    """The audio payload of a file: `length` bytes starting at byte `offset`."""

    offset: int
    length: int


class _InvalidError(Exception):
    """The content is not something this parser understands (turned into None)."""


class _Source:
    """Exact reads at absolute offsets of an open file of known size."""

    def __init__(self, handle: BinaryIO, size: int) -> None:
        self._handle = handle
        self.size = size

    def read(self, offset: int, count: int) -> bytes:
        if offset < 0 or count < 0 or offset + count > self.size:
            raise _InvalidError("read outside the file")
        self._handle.seek(offset)
        data = self._handle.read(count)
        if len(data) != count:
            raise _InvalidError("short read")
        return data


def payload_span(path: Path) -> Span | None:
    """Return the audio payload span of the file at `path`, or None.

    None means "no single clear payload": the caller must not try a tags-only transfer.
    """
    with open(path, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        try:
            span = _find_span(_Source(handle, size))
        except (_InvalidError, struct.error):
            return None
    if span.length <= 0 or span.offset < 0 or span.offset + span.length > size:
        return None
    return span


def span_sha256(path: Path, span: Span) -> str:
    """Return the SHA-256 (lowercase hex) of the bytes of `span`, read in 1 MiB blocks.

    Raises `ValueError` when the file is shorter than the span.
    """
    digest = hashlib.sha256()
    remaining = span.length
    with open(path, "rb") as handle:
        handle.seek(span.offset)
        while remaining > 0:
            block = handle.read(min(_BLOCK, remaining))
            if not block:
                raise ValueError("The file is shorter than the span.")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def tag_bytes_size(path: Path, span: Span) -> int:
    """Return how many bytes lie outside the span: the size of prefix + suffix."""
    return os.stat(path).st_size - span.length


def read_tag_parts(path: Path, span: Span) -> tuple[bytes, bytes]:
    """Return `(prefix, suffix)`: the bytes before and after the span, read into memory.

    Raises `ValueError` when they are bigger than `MAX_TAG_BYTES` or when the file does not
    hold the span (so a changed file is not mistaken for a valid split).
    """
    with open(path, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        if span.offset + span.length > size:
            raise ValueError("The file is shorter than the span.")
        suffix_size = size - span.offset - span.length
        if span.offset + suffix_size > MAX_TAG_BYTES:
            raise ValueError("The tag parts are too big to be read into memory.")
        prefix = handle.read(span.offset)
        handle.seek(span.offset + span.length)
        suffix = handle.read(suffix_size)
    return prefix, suffix


# -- container detection ---------------------------------------------------------------


def _find_span(source: _Source) -> Span:
    head = source.read(0, min(12, source.size))
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return _riff_like(source, big_endian=False, wanted=b"data")
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return _riff_like(source, big_endian=True, wanted=b"SSND")
    if head[4:8] == b"ftyp":
        return _mp4(source)
    start = _skip_id3v2(source)
    if source.size - start >= 4 and source.read(start, 4) == b"fLaC":
        return _flac(source, start)
    return _mpeg_audio(source, start)


def _skip_id3v2(source: _Source) -> int:
    """Return the offset after the ID3v2 tag(s) at the start of the file (0 when none)."""
    offset = 0
    for _ in range(_MAX_ID3V2_TAGS):
        if source.size - offset < _ID3V2_HEADER:
            break
        header = source.read(offset, _ID3V2_HEADER)
        if header[:3] != b"ID3":
            break
        major = header[3]
        size_bytes = header[6:10]
        if major not in (2, 3, 4) or any(byte & 0x80 for byte in size_bytes):
            raise _InvalidError("bad ID3v2 header")
        body = (size_bytes[0] << 21) | (size_bytes[1] << 14) | (size_bytes[2] << 7) | size_bytes[3]
        footer = 10 if (major == 4 and header[5] & 0x10) else 0
        offset += _ID3V2_HEADER + body + footer
        if offset > source.size:
            raise _InvalidError("ID3v2 tag runs past the end of the file")
    return offset


# -- FLAC ------------------------------------------------------------------------------


def _flac(source: _Source, start: int) -> Span:
    offset = start + 4
    while True:
        header = source.read(offset, 4)
        is_last = bool(header[0] & 0x80)
        length = int.from_bytes(header[1:4], "big")
        offset += 4 + length
        if offset > source.size:
            raise _InvalidError("metadata block runs past the end of the file")
        if is_last:
            break
    if source.size - offset < 2:
        raise _InvalidError("no audio frame")
    sync = source.read(offset, 2)
    if sync[0] != 0xFF or (sync[1] & 0xFE) != 0xF8:
        raise _InvalidError("the audio does not start with a FLAC frame")
    return Span(offset, source.size - offset)


# -- MPEG audio (MP3) --------------------------------------------------------------------


def _is_mpeg_frame_header(header: bytes) -> bool:
    if len(header) < 4 or header[0] != 0xFF or (header[1] & 0xE0) != 0xE0:
        return False
    version = (header[1] >> 3) & 0x03
    layer = (header[1] >> 1) & 0x03
    bitrate = header[2] >> 4
    sample_rate = (header[2] >> 2) & 0x03
    return version != 1 and layer != 0 and bitrate != 15 and sample_rate != 3


def _mpeg_audio(source: _Source, start: int) -> Span:
    end = source.size
    if end - start < 4 or not _is_mpeg_frame_header(source.read(start, 4)):
        raise _InvalidError("not an MPEG audio file")
    if end - start >= _ID3V1_SIZE and source.read(end - _ID3V1_SIZE, 3) == b"TAG":
        end -= _ID3V1_SIZE
    if end - start >= _APE_FOOTER:
        footer = source.read(end - _APE_FOOTER, _APE_FOOTER)
        if footer[:8] == b"APETAGEX":
            tag_size = struct.unpack("<I", footer[12:16])[0]  # items + footer
            flags = struct.unpack("<I", footer[20:24])[0]
            if flags & 0x80000000:
                tag_size += _APE_FOOTER  # the tag also has a header
            if tag_size < _APE_FOOTER or tag_size > end - start:
                raise _InvalidError("APEv2 tag size is inconsistent")
            end -= tag_size
    if end <= start:
        raise _InvalidError("no audio")
    return Span(start, end - start)


# -- RIFF/WAVE and FORM/AIFF -----------------------------------------------------------


def _riff_like(source: _Source, *, big_endian: bool, wanted: bytes) -> Span:
    byte_order = ">I" if big_endian else "<I"
    offset = 12
    while offset + 8 <= source.size:
        header = source.read(offset, 8)
        chunk_id = header[:4]
        length = struct.unpack(byte_order, header[4:8])[0]
        payload = offset + 8
        if payload + length > source.size:
            raise _InvalidError("chunk runs past the end of the file")
        if chunk_id == wanted:
            return Span(payload, length)
        offset = payload + length + (length & 1)
    raise _InvalidError("no audio chunk")


# -- MP4 / M4A -------------------------------------------------------------------------


def _mp4(source: _Source) -> Span:
    offset = 0
    found: Span | None = None
    while offset < source.size:
        if source.size - offset < 8:
            raise _InvalidError("trailing bytes after the last atom")
        size, kind = struct.unpack(">I4s", source.read(offset, 8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", source.read(offset + 8, 8))[0]
            header = 16
        elif size == 0:
            size = source.size - offset
        if size < header or offset + size > source.size:
            raise _InvalidError("atom size is inconsistent")
        if kind == b"mdat":
            if found is not None:
                raise _InvalidError("several mdat atoms")
            found = Span(offset + header, size - header)
        offset += size
    if found is None:
        raise _InvalidError("no mdat atom")
    return found

"""Bounded 60-second PCM segmentation shared by the musical estimators."""

from __future__ import annotations

from collections.abc import Iterator

from mtee.domain.conversion import ConversionSource
from mtee.services.analyzers.base import AnalyzerContext
from mtee.services.media_decode_service import MediaDecodeService

SAMPLE_RATE = 22_050
SEGMENT_SECONDS = 60
_BYTES_PER_SEGMENT = SAMPLE_RATE * SEGMENT_SECONDS * 2


def pcm_segments(
    decoder: MediaDecodeService, source: ConversionSource, context: AnalyzerContext
) -> Iterator[tuple[int, bytes]]:
    buffer = bytearray()
    start_frame = 0
    for block in decoder.stream_pcm(
        source, sample_rate=SAMPLE_RATE, channels=1, is_cancelled=context.is_cancelled
    ):
        context.raise_if_cancelled()
        offset = 0
        while offset < len(block):
            take = min(_BYTES_PER_SEGMENT - len(buffer), len(block) - offset)
            buffer.extend(block[offset : offset + take])
            offset += take
            if len(buffer) == _BYTES_PER_SEGMENT:
                yield start_frame, bytes(buffer)
                start_frame += len(buffer) // 2
                buffer.clear()
    if buffer:
        yield start_frame, bytes(buffer)

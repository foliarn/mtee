"""Bitrate display uses base-1000 kbps while the stored value stays numeric."""

from mtee.domain.metadata import format_bitrate


def test_bitrate_format_is_readable_and_keeps_numeric_sorting() -> None:
    assert format_bitrate(320_000) == "320 kbps"
    assert format_bitrate(96_000) == "96 kbps"
    assert format_bitrate(128_400) == "128 kbps"
    assert format_bitrate(0) == "—"
    assert format_bitrate(None) == "—"
    assert sorted([320_000, 96_000, 128_000]) == [96_000, 128_000, 320_000]

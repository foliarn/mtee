"""The level rules (plan 127.0): a table over source types, levels and client codec sets."""

from __future__ import annotations

import pytest

from mtee_remote.errors import ApiError
from mtee_remote.streaming.levels import parse_codecs, parse_level, plan
from mtee_remote.streaming.types import DeliveryPlan, Level, SourceInfo

# The five client codec sets of the table, in column order.
DEFAULT = frozenset()  # no list: "flac, aac, opus"
FLAC_AAC_OPUS = frozenset({"flac", "aac", "opus"})
APPLE = frozenset({"alac", "aac"})
FLAC_OPUS = frozenset({"flac", "opus"})
MP3_ONLY = frozenset({"mp3"})
CLIENTS = [DEFAULT, FLAC_AAC_OPUS, APPLE, FLAC_OPUS, MP3_ONLY]


def lossy(codec: str, kbps: int, rate: int | None = None) -> DeliveryPlan:
    if codec == "opus":
        return DeliveryPlan(
            send_original=False,
            codec="opus",
            bitrate=kbps * 1000,
            mime="audio/ogg",
            ext="opus",
            key=f"opus-{kbps}",
        )
    key = f"aac-{kbps}" + (f"-r{rate}" if rate else "")
    return DeliveryPlan(
        send_original=False,
        codec="aac",
        bitrate=kbps * 1000,
        sample_rate=rate,
        mime="audio/mp4",
        ext="m4a",
        key=key,
    )


def OPUS(kbps: int) -> DeliveryPlan:  # noqa: N802 - reads as the plan name in the table
    return lossy("opus", kbps)


def AAC(kbps: int, rate: int | None = None) -> DeliveryPlan:  # noqa: N802
    return lossy("aac", kbps, rate)


FLAC_TRANSCODE = DeliveryPlan(
    send_original=False,
    codec="flac",
    mime="audio/flac",
    ext="flac",
    key="lossless-flac",
)
ORIG_FLAC = DeliveryPlan.original("audio/flac", "flac")
ORIG_ALAC = DeliveryPlan.original("audio/mp4", "m4a")
ORIG_WAV = DeliveryPlan.original("audio/wav", "wav")
ORIG_AIFF = DeliveryPlan.original("audio/aiff", "aiff")
ORIG_MP3 = DeliveryPlan.original("audio/mpeg", "mp3")
ORIG_AAC = DeliveryPlan.original("audio/mp4", "m4a")
ORIG_OGG = DeliveryPlan.original("audio/ogg", "ogg")
ORIG_OPUS = DeliveryPlan.original("audio/ogg", "opus")

SOURCES: dict[str, SourceInfo] = {
    "FLAC 16/44.1": SourceInfo("flac", True, 44100, 16, 1_411_000, 2),
    "FLAC 24/96": SourceInfo("flac", True, 96000, 24, 4_608_000, 2),
    "FLAC 24/192": SourceInfo("flac", True, 192000, 24, 9_216_000, 2),
    "ALAC 24/96": SourceInfo("alac", True, 96000, 24, 4_608_000, 2),
    "WAV 16/44.1": SourceInfo("pcm_s16le", True, 44100, 16, 1_411_200, 2),
    "AIFF 24/48": SourceInfo("pcm_s24be", True, 48000, 24, 2_304_000, 2),
    "MP3 128": SourceInfo("mp3", False, 44100, None, 128_000, 2),
    "MP3 320": SourceInfo("mp3", False, 44100, None, 320_000, 2),
    "AAC 256": SourceInfo("aac", False, 44100, None, 256_000, 2),
    "Vorbis 160": SourceInfo("vorbis", False, 44100, None, 160_000, 2),
    "Opus 128": SourceInfo("opus", False, 48000, None, 128_000, 2),
}

# For each source and level, the expected plan for each client set in CLIENTS.
TABLE: dict[str, dict[str, list[DeliveryPlan]]] = {
    "FLAC 16/44.1": {
        "original": [ORIG_FLAC] * 5,
        "lossless": [ORIG_FLAC] * 5,
        "320": [OPUS(256), OPUS(256), AAC(320), OPUS(256), AAC(320)],
        "128": [OPUS(128), OPUS(128), AAC(128), OPUS(128), AAC(128)],
    },
    "FLAC 24/96": {
        "original": [ORIG_FLAC] * 5,
        "lossless": [ORIG_FLAC] * 5,
        "320": [OPUS(256), OPUS(256), AAC(320, 48000), OPUS(256), AAC(320, 48000)],
        "128": [OPUS(128), OPUS(128), AAC(128, 48000), OPUS(128), AAC(128, 48000)],
    },
    "FLAC 24/192": {
        "original": [ORIG_FLAC] * 5,
        "lossless": [ORIG_FLAC] * 5,
        "320": [OPUS(256), OPUS(256), AAC(320, 48000), OPUS(256), AAC(320, 48000)],
        "128": [OPUS(128), OPUS(128), AAC(128, 48000), OPUS(128), AAC(128, 48000)],
    },
    "ALAC 24/96": {
        "original": [ORIG_ALAC] * 5,
        "lossless": [FLAC_TRANSCODE, FLAC_TRANSCODE, ORIG_ALAC, FLAC_TRANSCODE, FLAC_TRANSCODE],
        "320": [OPUS(256), OPUS(256), AAC(320, 48000), OPUS(256), AAC(320, 48000)],
        "128": [OPUS(128), OPUS(128), AAC(128, 48000), OPUS(128), AAC(128, 48000)],
    },
    "WAV 16/44.1": {
        "original": [ORIG_WAV] * 5,
        "lossless": [FLAC_TRANSCODE] * 5,
        "320": [OPUS(256), OPUS(256), AAC(320), OPUS(256), AAC(320)],
        "128": [OPUS(128), OPUS(128), AAC(128), OPUS(128), AAC(128)],
    },
    "AIFF 24/48": {
        "original": [ORIG_AIFF] * 5,
        "lossless": [FLAC_TRANSCODE] * 5,
        "320": [OPUS(256), OPUS(256), AAC(320), OPUS(256), AAC(320)],
        "128": [OPUS(128), OPUS(128), AAC(128), OPUS(128), AAC(128)],
    },
    "MP3 128": {
        "original": [ORIG_MP3] * 5,
        "lossless": [ORIG_MP3] * 5,
        # Not accepted (all but the last set) -> transcode at min(320, 128) = 128.
        "320": [OPUS(128), OPUS(128), AAC(128), OPUS(128), ORIG_MP3],
        "128": [OPUS(128), OPUS(128), AAC(128), OPUS(128), ORIG_MP3],
    },
    "MP3 320": {
        "original": [ORIG_MP3] * 5,
        "lossless": [ORIG_MP3] * 5,
        "320": [OPUS(256), OPUS(256), AAC(320), OPUS(256), ORIG_MP3],
        # Above the target, so transcoded even where MP3 is accepted.
        "128": [OPUS(128), OPUS(128), AAC(128), OPUS(128), AAC(128)],
    },
    "AAC 256": {
        "original": [ORIG_AAC] * 5,
        "lossless": [ORIG_AAC] * 5,
        "320": [ORIG_AAC, ORIG_AAC, ORIG_AAC, OPUS(256), AAC(256)],
        "128": [OPUS(128), OPUS(128), AAC(128), OPUS(128), AAC(128)],
    },
    "Vorbis 160": {
        "original": [ORIG_OGG] * 5,
        "lossless": [ORIG_OGG] * 5,
        "320": [OPUS(160), OPUS(160), AAC(160), OPUS(160), AAC(160)],
        "128": [OPUS(128), OPUS(128), AAC(128), OPUS(128), AAC(128)],
    },
    "Opus 128": {
        "original": [ORIG_OPUS] * 5,
        "lossless": [ORIG_OPUS] * 5,
        "320": [ORIG_OPUS, ORIG_OPUS, AAC(128), ORIG_OPUS, AAC(128)],
        "128": [ORIG_OPUS, ORIG_OPUS, AAC(128), ORIG_OPUS, AAC(128)],
    },
}


def _cases() -> list[tuple[str, Level, frozenset[str], DeliveryPlan]]:
    cases: list[tuple[str, Level, frozenset[str], DeliveryPlan]] = []
    for name, by_level in TABLE.items():
        for level, expected in by_level.items():
            for clients, want in zip(CLIENTS, expected, strict=True):
                cases.append((name, parse_level(level), clients, want))
    return cases


@pytest.mark.parametrize(
    ("source", "level", "clients", "expected"),
    _cases(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_source_level_and_client_set(
    source: str, level: Level, clients: frozenset[str], expected: DeliveryPlan
) -> None:
    assert plan(SOURCES[source], level, clients) == expected


def test_the_table_covers_every_source_and_level() -> None:
    assert set(TABLE) == set(SOURCES)
    for by_level in TABLE.values():
        assert set(by_level) == {"original", "lossless", "320", "128"}
        assert all(len(expected) == len(CLIENTS) for expected in by_level.values())


# -- rules the table does not show ---------------------------------------------------------


def test_a_lossy_source_is_never_upgraded_to_lossless() -> None:
    mp3 = SOURCES["MP3 320"]
    assert plan(mp3, "lossless", frozenset(), lossless_cap=(96000, 24)) == plan(
        mp3, "original", frozenset()
    )


def test_a_lossy_source_of_unknown_bitrate_is_sent_when_accepted() -> None:
    src = SourceInfo("mp3", False, 44100, None, None, 2)
    assert plan(src, "320", MP3_ONLY) == DeliveryPlan.original("audio/mpeg", "mp3")
    assert plan(src, "320", frozenset()) == OPUS(256)


def test_a_low_bitrate_source_is_never_upscaled() -> None:
    vorbis_64 = SourceInfo("vorbis", False, 44100, None, 64_000, 2)
    assert plan(vorbis_64, "320", frozenset()) == OPUS(64)
    assert plan(vorbis_64, "128", APPLE) == AAC(64)


def test_the_bitrate_is_compared_in_whole_kilobits() -> None:
    # Mutagen reports 320001 bit/s for many 320 kbps MP3 files.
    mp3 = SourceInfo("mp3", False, 44100, None, 320_001, 2)
    assert plan(mp3, "320", MP3_ONLY) == ORIG_MP3


def test_no_sample_rate_is_raised() -> None:
    sixteen = SourceInfo("pcm_s16le", True, 44100, 16, None, 2)
    assert plan(sixteen, "320", frozenset({"aac"})) == AAC(320)


def test_lossy_output_at_44_1_family_rates() -> None:
    src = SourceInfo("flac", True, 88200, 24, None, 2)
    assert plan(src, "320", frozenset({"aac"})) == AAC(320, 44100)
    assert plan(src, "320", frozenset()) == OPUS(256)


def test_the_original_level_ignores_the_cap_and_the_codecs() -> None:
    assert plan(SOURCES["FLAC 24/192"], "original", APPLE, lossless_cap=(48000, 16)) == ORIG_FLAC


# -- the lossless cap ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "cap", "expected"),
    [
        # 96 kHz family under 48 kHz: 48000; 24 bit under 16 bit: 16.
        (
            SourceInfo("flac", True, 96000, 24, None, 2),
            (48000, 16),
            DeliveryPlan(
                send_original=False,
                codec="flac",
                sample_rate=48000,
                bit_depth=16,
                mime="audio/flac",
                ext="flac",
                key="lossless-flac-r48000-b16",
            ),
        ),
        # 176.4 kHz under 96 kHz: 88200 (44.1 family).
        (
            SourceInfo("flac", True, 176400, 24, None, 2),
            (96000, 24),
            DeliveryPlan(
                send_original=False,
                codec="flac",
                sample_rate=88200,
                mime="audio/flac",
                ext="flac",
                key="lossless-flac-r88200",
            ),
        ),
        # 88.2 kHz under 44.1 kHz: 44100.
        (
            SourceInfo("flac", True, 88200, 16, None, 2),
            (44100, 24),
            DeliveryPlan(
                send_original=False,
                codec="flac",
                sample_rate=44100,
                mime="audio/flac",
                ext="flac",
                key="lossless-flac-r44100",
            ),
        ),
        # 192 kHz under 96 kHz: 96000.
        (
            SourceInfo("flac", True, 192000, 24, None, 2),
            (96000, 24),
            DeliveryPlan(
                send_original=False,
                codec="flac",
                sample_rate=96000,
                mime="audio/flac",
                ext="flac",
                key="lossless-flac-r96000",
            ),
        ),
        # Depth only: 24 bit under 16 bit, rate unchanged.
        (
            SourceInfo("flac", True, 44100, 24, None, 2),
            (96000, 16),
            DeliveryPlan(
                send_original=False,
                codec="flac",
                bit_depth=16,
                mime="audio/flac",
                ext="flac",
                key="lossless-flac-b16",
            ),
        ),
    ],
)
def test_the_cap_lowers_and_names_the_transcode(
    source: SourceInfo, cap: tuple[int, int], expected: DeliveryPlan
) -> None:
    assert plan(source, "lossless", frozenset(), lossless_cap=cap) == expected


def test_the_cap_never_raises_rate_or_depth() -> None:
    flac_24_96 = SOURCES["FLAC 24/96"]
    assert plan(flac_24_96, "lossless", frozenset(), lossless_cap=(96000, 24)) == ORIG_FLAC
    assert plan(flac_24_96, "lossless", frozenset(), lossless_cap=(192000, 32)) == ORIG_FLAC


def test_the_cap_applies_to_alac_and_wav() -> None:
    alac = SOURCES["ALAC 24/96"]
    assert plan(alac, "lossless", APPLE, lossless_cap=(48000, 24)) == DeliveryPlan(
        send_original=False,
        codec="flac",
        sample_rate=48000,
        mime="audio/flac",
        ext="flac",
        key="lossless-flac-r48000",
    )
    wav = SOURCES["WAV 16/44.1"]
    assert plan(wav, "lossless", frozenset(), wav_to_flac=False, lossless_cap=(44100, 16)) == (
        ORIG_WAV
    )


def test_the_cap_still_applies_when_wav_is_kept() -> None:
    src = SourceInfo("pcm_s24le", True, 96000, 24, None, 2)
    result = plan(src, "lossless", frozenset(), wav_to_flac=False, lossless_cap=(48000, 24))
    assert result.codec == "flac"
    assert result.sample_rate == 48000


# -- the lossless rules ----------------------------------------------------------------------


def test_wav_and_aiff_are_kept_when_wav_to_flac_is_off() -> None:
    wav = SOURCES["WAV 16/44.1"]
    aiff = SOURCES["AIFF 24/48"]
    assert plan(wav, "lossless", frozenset(), wav_to_flac=False) == ORIG_WAV
    assert plan(aiff, "lossless", frozenset(), wav_to_flac=False) == ORIG_AIFF


def test_alac_to_flac_for_a_client_without_alac_is_not_affected_by_wav_to_flac() -> None:
    alac = SOURCES["ALAC 24/96"]
    assert plan(alac, "lossless", frozenset(), wav_to_flac=False) == FLAC_TRANSCODE


def test_other_lossless_codecs_become_flac() -> None:
    wavpack = SourceInfo("wavpack", True, 44100, 16, None, 2)
    assert plan(wavpack, "lossless", frozenset()) == FLAC_TRANSCODE
    assert plan(wavpack, "original", frozenset()) == DeliveryPlan.original(
        "application/octet-stream", "wv"
    )


def test_big_endian_pcm_is_sent_as_aiff() -> None:
    assert plan(SOURCES["AIFF 24/48"], "original", frozenset()).ext == "aiff"


# -- parsing ---------------------------------------------------------------------------------


def test_parse_level_accepts_the_four_levels() -> None:
    assert [parse_level(name) for name in ("original", "lossless", "320", "128")] == [
        "original",
        "lossless",
        "320",
        "128",
    ]


@pytest.mark.parametrize("text", ["", "flac", "256", "Lossless", " 320"])
def test_parse_level_refuses_anything_else(text: str) -> None:
    with pytest.raises(ApiError) as caught:
        parse_level(text)
    assert caught.value.code == "bad_request"
    assert caught.value.status == 400


def test_parse_codecs_reads_a_comma_list() -> None:
    assert parse_codecs("flac, AAC ,opus") == frozenset({"flac", "aac", "opus"})
    assert parse_codecs("") == frozenset()
    assert parse_codecs("mp3,,") == frozenset({"mp3"})


def test_parse_codecs_names_the_unknown_codec() -> None:
    with pytest.raises(ApiError) as caught:
        parse_codecs("flac,wma")
    assert caught.value.code == "bad_request"
    assert "wma" in caught.value.message


def test_plan_refuses_an_unknown_level() -> None:
    with pytest.raises(ApiError) as caught:
        plan(SOURCES["FLAC 16/44.1"], "256", frozenset())  # type: ignore[arg-type]
    assert caught.value.code == "bad_request"

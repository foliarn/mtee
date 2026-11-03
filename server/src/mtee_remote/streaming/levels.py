"""Level rules: which bytes to send for a source, a level and the client's codecs (plan 127.0).

Pure functions, no I/O. `plan()` decides; the transcoder only executes the `DeliveryPlan` it
returns. The rules are the table in plan 127, section 4, with the numbers as the user approved
them. Decisions beyond that table are noted in the docstrings.
"""

from __future__ import annotations

from mtee_remote.errors import ApiError
from mtee_remote.streaming.types import (
    CLIENT_CODECS,
    LEVELS,
    DeliveryPlan,
    Level,
    SourceInfo,
)

# A client that sends no codec list gets these (architecture file, decision 11).
DEFAULT_CODECS: frozenset[str] = frozenset({"flac", "aac", "opus"})

_TARGET_BITS_PER_SECOND: dict[str, int] = {"320": 320_000, "128": 128_000}
# libopus refuses more than 256 kbps for a mono source, so Opus output is capped there (level 320
# becomes opus-256). AAC keeps the full target.
_OPUS_MAX_KBPS = 256
_ORIGINAL_EXT: dict[str, str] = {"wavpack": "wv", "truehd": "thd"}
_STANDARD_RATE_FAMILIES: dict[int, tuple[int, ...]] = {
    44100: (44100, 88200, 176400, 352800),
    48000: (48000, 96000, 192000, 384000),
}


def original_plan(src: SourceInfo) -> DeliveryPlan:
    """The file as it is stored, with the MIME type and extension of its codec."""
    codec = src.codec
    if codec == "flac":
        return DeliveryPlan.original("audio/flac", "flac")
    if codec == "mp3":
        return DeliveryPlan.original("audio/mpeg", "mp3")
    if codec in ("aac", "alac"):
        return DeliveryPlan.original("audio/mp4", "m4a")
    if codec == "vorbis":
        return DeliveryPlan.original("audio/ogg", "ogg")
    if codec == "opus":
        return DeliveryPlan.original("audio/ogg", "opus")
    if codec.startswith("pcm_"):
        if codec.endswith("be"):
            return DeliveryPlan.original("audio/aiff", "aiff")
        return DeliveryPlan.original("audio/wav", "wav")
    return DeliveryPlan.original("application/octet-stream", _ORIGINAL_EXT.get(codec, codec))


def plan(
    src: SourceInfo,
    level: Level,
    accepted: frozenset[str],
    *,
    wav_to_flac: bool = True,
    lossless_cap: tuple[int, int] | None = None,
) -> DeliveryPlan:
    """Return what to send for `src` at `level` to a client that accepts `accepted` codecs.

    An empty `accepted` means "flac, aac, opus". `lossless_cap` is `(max_sample_rate,
    max_bit_depth)`; it only lowers lossless output, and when it lowers a source the output is
    always FLAC. `wav_to_flac=False` keeps WAV and AIFF sources as they are at the *lossless*
    level (unless the cap lowers them).
    """
    if level not in LEVELS:
        raise ApiError("bad_request", "The level must be one of: " + ", ".join(LEVELS) + ".")
    clients = accepted or DEFAULT_CODECS
    if level == "original":
        return original_plan(src)
    if level == "lossless":
        return _lossless(src, clients, wav_to_flac=wav_to_flac, lossless_cap=lossless_cap)
    return _lossy(src, clients, _TARGET_BITS_PER_SECOND[level])


def parse_level(text: str) -> Level:
    """Return the level named by `text`, or raise `bad_request`."""
    for level in LEVELS:
        if text == level:
            return level
    raise ApiError("bad_request", "The level must be one of: " + ", ".join(LEVELS) + ".")


def parse_codecs(text: str) -> frozenset[str]:
    """Return the codecs of a comma-separated list; an empty text gives the empty set.

    Raises `bad_request` naming any codec that is not one of `CLIENT_CODECS`.
    """
    names = {part.strip().lower() for part in text.split(",") if part.strip()}
    unknown = sorted(names - CLIENT_CODECS)
    if unknown:
        raise ApiError("bad_request", "Unknown codec: " + ", ".join(unknown) + ".")
    return frozenset(names)


# -- lossless ---------------------------------------------------------------------------


def _lossless(
    src: SourceInfo,
    clients: frozenset[str],
    *,
    wav_to_flac: bool,
    lossless_cap: tuple[int, int] | None,
) -> DeliveryPlan:
    if not src.lossless:
        # Never upgrade a lossy file to a lossless one.
        return original_plan(src)
    rate, depth = _cap(src.sample_rate, src.bit_depth, lossless_cap)
    if rate is not None or depth is not None:
        return _flac(rate, depth)
    if src.codec == "flac":
        return original_plan(src)
    if src.codec == "alac":
        return original_plan(src) if "alac" in clients else _flac(None, None)
    # WAV, AIFF and the other lossless codecs.
    return _flac(None, None) if wav_to_flac else original_plan(src)


def _flac(rate: int | None, depth: int | None) -> DeliveryPlan:
    key = "lossless-flac"
    if rate is not None:
        key += f"-r{rate}"
    if depth is not None:
        key += f"-b{depth}"
    return DeliveryPlan(
        send_original=False,
        codec="flac",
        sample_rate=rate,
        bit_depth=depth,
        mime="audio/flac",
        ext="flac",
        key=key,
    )


def _cap(
    sample_rate: int | None, bit_depth: int | None, lossless_cap: tuple[int, int] | None
) -> tuple[int | None, int | None]:
    """Return the `(sample_rate, bit_depth)` to force, None where the source is kept."""
    if lossless_cap is None:
        return None, None
    max_rate, max_depth = lossless_cap
    rate = None
    if sample_rate is not None and sample_rate > max_rate:
        rate = _lower_rate(sample_rate, max_rate)
    depth = None
    if bit_depth is not None and bit_depth > max_depth:
        depth = max_depth
    return rate, depth


def _lower_rate(sample_rate: int, max_rate: int) -> int:
    """The highest rate of the source's family that fits under `max_rate`.

    The 44.1 kHz family (88200, 176400 ...) and the 48 kHz family (96000, 192000 ...) are kept
    apart: 176400 under 96000 gives 88200, 96000 under 48000 gives 48000. When the family has
    no rate that fits, the highest standard rate of either family does, and failing that
    `max_rate` itself.
    """
    limit = min(max_rate, sample_rate - 1)
    for base, family in _STANDARD_RATE_FAMILIES.items():
        if sample_rate % base == 0:
            fitting = [rate for rate in family if rate <= limit]
            if fitting:
                return max(fitting)
            break
    everything = [rate for family in _STANDARD_RATE_FAMILIES.values() for rate in family]
    fitting = [rate for rate in everything if rate <= limit]
    return max(fitting) if fitting else max_rate


# -- lossy ------------------------------------------------------------------------------


def _lossy_codec(clients: frozenset[str]) -> str:
    """AAC for Apple clients (they also take ALAC); Opus for the others; AAC as last resort."""
    if "aac" in clients and ("opus" not in clients or "alac" in clients):
        return "aac"
    if "opus" in clients:
        return "opus"
    return "aac"


def _kbps(bits_per_second: int) -> int:
    """Whole kilobits per second, as MTEE displays them: 320001 bit/s is 320 kbps."""
    return round(bits_per_second / 1000)


def _lossy(src: SourceInfo, clients: frozenset[str], target_bps: int) -> DeliveryPlan:
    target = _kbps(target_bps)
    source_kbps = _kbps(src.bitrate) if src.bitrate is not None else None
    # A lossy file at or below the target, in a codec the client takes, is sent as it is.
    fits = source_kbps is None or source_kbps <= target
    if not src.lossless and src.codec in clients and fits:
        return original_plan(src)
    out_kbps = target if source_kbps is None else min(target, source_kbps)
    codec = _lossy_codec(clients)
    if codec == "opus":
        out_kbps = min(out_kbps, _OPUS_MAX_KBPS)
        return DeliveryPlan(
            send_original=False,
            codec="opus",
            bitrate=out_kbps * 1000,
            sample_rate=None,
            mime="audio/ogg",
            ext="opus",
            key=f"opus-{out_kbps}",
        )
    rate = _lossy_rate(src)
    key = f"aac-{out_kbps}"
    if rate is not None:
        key += f"-r{rate}"
    return DeliveryPlan(
        send_original=False,
        codec="aac",
        bitrate=out_kbps * 1000,
        sample_rate=rate,
        mime="audio/mp4",
        ext="m4a",
        key=key,
    )


def _lossy_rate(src: SourceInfo) -> int | None:
    """48 kHz (44.1 kHz for the 44.1 family) when the source is above 48 kHz; else unchanged."""
    if src.sample_rate is None or src.sample_rate <= 48000:
        return None
    return 44100 if src.sample_rate % 44100 == 0 else 48000

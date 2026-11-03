"""ffmpeg arguments and real transcodes: codecs, gapless sample counts, failures."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from helpers import make_audio
from mtee_remote import tools
from mtee_remote.streaming import transcode
from mtee_remote.streaming.transcode import TranscodeError, ffmpeg_args, run_transcode
from mtee_remote.streaming.types import DeliveryPlan

SECONDS = 3.0
SOURCE_RATE = 44100

FLAC_16 = DeliveryPlan(send_original=False, codec="flac", bit_depth=16, ext="flac", key="flac16")
FLAC_48_16 = DeliveryPlan(
    send_original=False,
    codec="flac",
    sample_rate=48000,
    bit_depth=16,
    ext="flac",
    key="flac48-16",
)
AAC_320 = DeliveryPlan(send_original=False, codec="aac", bitrate=320000, ext="m4a", key="aac320")
OPUS_128 = DeliveryPlan(
    send_original=False, codec="opus", bitrate=128000, ext="opus", key="opus128"
)


def _ffmpeg() -> str:
    return tools.ffmpeg_path()


def _ffprobe() -> str:
    ffmpeg = Path(_ffmpeg())
    return str(ffmpeg.with_name("ffprobe" + ffmpeg.suffix))


def _probe(path: Path) -> dict[str, object]:
    """Return the first audio stream's codec, rate and sample format, and the container."""
    result = subprocess.run(
        [
            _ffprobe(),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bits_per_raw_sample,sample_fmt"
            ":format=format_name",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return {
        "codec": stream["codec_name"],
        "sample_rate": int(stream["sample_rate"]),
        "channels": stream["channels"],
        "bits": stream.get("bits_per_raw_sample"),
        "sample_fmt": stream.get("sample_fmt"),
        "format": data["format"]["format_name"],
    }


def _sample_count(path: Path, rate: int | None = None) -> int:
    """Decode the first audio stream to mono 16-bit PCM and count the samples."""
    command = [_ffmpeg(), "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1"]
    if rate is not None:
        command += ["-ar", str(rate)]
    command += ["-f", "s16le", "-"]
    result = subprocess.run(command, capture_output=True, check=True)
    return len(result.stdout) // 2


@pytest.fixture(scope="module")
def source_44(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("sources44")
    return make_audio(folder / "tone.flac", "flac", seconds=SECONDS)


@pytest.fixture(scope="module")
def long_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Half an hour of tone: long enough that an Opus encode outlives a 0.3 s cancel."""
    folder = tmp_path_factory.mktemp("long")
    return make_audio(folder / "long.flac", "flac", seconds=1800.0)


@pytest.fixture(scope="module")
def source_24_96(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = tmp_path_factory.mktemp("sources96")
    path = folder / "hires.flac"
    subprocess.run(
        [
            _ffmpeg(),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={SECONDS}:sample_rate=96000",
            "-c:a",
            "flac",
            "-sample_fmt",
            "s32",
            "-bits_per_raw_sample",
            "24",
            "-f",
            "flac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


# ---- ffmpeg_args (pure) -------------------------------------------------------------------

COMMON = [
    "-nostdin",
    "-hide_banner",
    "-v",
    "error",
    "-i",
    "SRC",
    "-map",
    "0:a:0",
    "-vn",
    "-sn",
    "-dn",
    "-map_metadata",
    "-1",
]


def _args(plan: DeliveryPlan) -> list[str]:
    return ffmpeg_args("ffmpeg", Path("SRC"), plan, Path("OUT.part-abc"))


def test_every_command_starts_with_the_common_options_and_ends_with_the_output() -> None:
    for plan in (FLAC_16, AAC_320, OPUS_128, FLAC_48_16):
        args = _args(plan)
        assert args[1:][: len(COMMON)] == COMMON
        assert args[-1] == "OUT.part-abc"
        assert "-y" not in args


def test_flac_16_bit_forces_s16_and_flac_muxer() -> None:
    args = _args(FLAC_16)
    assert args[args.index("-c:a") + 1] == "flac"
    assert args[args.index("-compression_level") + 1] == "5"
    assert args[args.index("-sample_fmt") + 1] == "s16"
    assert "-bits_per_raw_sample" not in args
    assert args[args.index("-f") + 1] == "flac"


def test_flac_24_bit_uses_s32_with_24_raw_bits() -> None:
    plan = DeliveryPlan(send_original=False, codec="flac", bit_depth=24, ext="flac", key="f24")
    args = _args(plan)
    assert args[args.index("-sample_fmt") + 1] == "s32"
    assert args[args.index("-bits_per_raw_sample") + 1] == "24"


def test_flac_without_bit_depth_keeps_the_source_format() -> None:
    plan = DeliveryPlan(send_original=False, codec="flac", ext="flac", key="f")
    args = _args(plan)
    assert "-sample_fmt" not in args
    assert "-bits_per_raw_sample" not in args


def test_flac_rejects_an_unknown_bit_depth() -> None:
    plan = DeliveryPlan(send_original=False, codec="flac", bit_depth=8, ext="flac", key="f")
    with pytest.raises(ValueError):
        _args(plan)


def test_aac_is_an_mp4_with_faststart() -> None:
    args = _args(AAC_320)
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-b:a") + 1] == "320000"
    assert args[args.index("-f") + 1] == "mp4"
    assert args[args.index("-movflags") + 1] == "+faststart"


def test_opus_is_ogg_with_vbr_on() -> None:
    args = _args(OPUS_128)
    assert args[args.index("-c:a") + 1] == "libopus"
    assert args[args.index("-b:a") + 1] == "128000"
    assert args[args.index("-vbr") + 1] == "on"
    assert args[args.index("-f") + 1] == "ogg"
    assert "-movflags" not in args


def test_sample_rate_uses_soxr_when_ffmpeg_has_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcode, "_has_soxr", lambda ffmpeg: True)
    args = _args(FLAC_48_16)
    assert args[args.index("-af") + 1] == "aresample=resampler=soxr:osr=48000"
    assert "-ar" not in args


def test_sample_rate_falls_back_to_ar_without_soxr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcode, "_has_soxr", lambda ffmpeg: False)
    args = _args(FLAC_48_16)
    assert args[args.index("-ar") + 1] == "48000"
    assert "-af" not in args


def test_no_sample_rate_option_means_no_resampling() -> None:
    args = _args(AAC_320)
    assert "-af" not in args
    assert "-ar" not in args


def test_a_lossy_plan_needs_a_bitrate() -> None:
    plan = DeliveryPlan(send_original=False, codec="aac", ext="m4a", key="aac")
    with pytest.raises(ValueError):
        _args(plan)


def test_the_original_has_no_transcode_arguments() -> None:
    plan = DeliveryPlan.original("audio/flac", "flac")
    with pytest.raises(ValueError):
        _args(plan)


def test_the_soxr_probe_runs_once_per_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append("run")
        return subprocess.CompletedProcess(args=[], returncode=0)

    transcode._has_soxr.cache_clear()
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    assert transcode._has_soxr("probe-once") is True
    assert transcode._has_soxr("probe-once") is True
    assert calls == ["run"]
    transcode._has_soxr.cache_clear()


# ---- real transcodes ----------------------------------------------------------------------


def test_flac_16_bit_is_exact_and_16_bit(tmp_path: Path, source_44: Path) -> None:
    out = tmp_path / "out.flac.part-x"
    run_transcode(_ffmpeg(), source_44, FLAC_16, out)
    info = _probe(out)
    assert info["codec"] == "flac"
    assert info["sample_rate"] == SOURCE_RATE
    assert info["sample_fmt"] == "s16"
    # FLAC is exact: the decoded sample count equals the source's.
    assert _sample_count(out) == _sample_count(source_44)


def test_flac_24_96_is_capped_to_48k_16_bit(tmp_path: Path, source_24_96: Path) -> None:
    out = tmp_path / "capped.flac.part-x"
    run_transcode(_ffmpeg(), source_24_96, FLAC_48_16, out)
    info = _probe(out)
    assert info["codec"] == "flac"
    assert info["sample_rate"] == 48000
    assert info["sample_fmt"] == "s16"
    expected = round(SECONDS * 48000)
    count = _sample_count(out)
    print(f"flac 96k -> 48k/16: {count} samples, expected {expected}")
    assert abs(count - expected) <= 1


def test_aac_320_is_a_faststart_mp4_with_the_source_length(tmp_path: Path, source_44: Path) -> None:
    out = tmp_path / "out.m4a.part-x"
    run_transcode(_ffmpeg(), source_44, AAC_320, out)
    info = _probe(out)
    assert info["codec"] == "aac"
    assert "mp4" in str(info["format"])
    data = out.read_bytes()
    assert data.index(b"moov") < data.index(b"mdat"), "moov must precede mdat (faststart)"
    difference = _sample_count(out) - _sample_count(source_44)
    print(f"aac 320k sample difference: {difference}")
    assert difference == 0


def test_opus_128_is_ogg_at_48k_with_the_source_length(tmp_path: Path, source_44: Path) -> None:
    out = tmp_path / "out.opus.part-x"
    run_transcode(_ffmpeg(), source_44, OPUS_128, out)
    info = _probe(out)
    assert info["codec"] == "opus"
    assert "ogg" in str(info["format"])
    reference = _sample_count(source_44, rate=48000)
    difference = _sample_count(out) - reference
    print(f"opus 128k sample difference at 48 kHz: {difference}")
    assert abs(difference) <= 1


def test_a_source_without_audio_fails_and_leaves_no_output(tmp_path: Path) -> None:
    bad = tmp_path / "notes.flac"
    bad.write_text("this is not audio")
    out = tmp_path / "bad.flac.part-x"
    with pytest.raises(TranscodeError) as info:
        run_transcode(_ffmpeg(), bad, FLAC_16, out)
    assert "notes.flac" in str(info.value)
    assert not out.exists()


def test_a_missing_ffmpeg_is_a_transcode_error(tmp_path: Path, source_44: Path) -> None:
    out = tmp_path / "x.flac.part-x"
    with pytest.raises(TranscodeError):
        run_transcode(str(tmp_path / "no-ffmpeg.exe"), source_44, FLAC_16, out)
    assert not out.exists()


def test_cancel_kills_ffmpeg_and_removes_the_partial_output(
    tmp_path: Path, long_source: Path
) -> None:
    out = tmp_path / "long.opus.part-x"
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    try:
        with pytest.raises(TranscodeError, match="cancelled"):
            run_transcode(_ffmpeg(), long_source, OPUS_128, out, cancel=cancel)
    finally:
        timer.cancel()
    assert not out.exists()


def test_timeout_kills_ffmpeg_and_removes_the_partial_output(
    tmp_path: Path, long_source: Path
) -> None:
    out = tmp_path / "long.opus.part-x"
    with pytest.raises(TranscodeError, match="timed out"):
        run_transcode(_ffmpeg(), long_source, OPUS_128, out, timeout=0.05)
    assert not out.exists()

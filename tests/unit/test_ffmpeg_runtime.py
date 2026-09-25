from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from mtee.services.ffmpeg_runtime import FfmpegRuntime, FfmpegRuntimeError


def test_executable_resolves_only_supported_tools_from_runtime_root(tmp_path: Path) -> None:
    for tool in ("ffmpeg", "ffprobe"):
        (tmp_path / f"{tool}.exe").touch()
    runtime = FfmpegRuntime(tmp_path)

    assert runtime.executable("ffmpeg") == tmp_path / "ffmpeg.exe"
    assert runtime.executable("ffprobe") == tmp_path / "ffprobe.exe"
    with pytest.raises(ValueError, match="Unsupported FFmpeg tool"):
        runtime.executable("ffplay")


def test_missing_executable_is_reported_without_path_fallback(tmp_path: Path) -> None:
    runtime = FfmpegRuntime(tmp_path)

    with pytest.raises(FfmpegRuntimeError, match="bundled ffmpeg runtime is missing"):
        runtime.executable("ffmpeg")


def test_run_uses_explicit_path_vector_shell_false_and_private_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "ffprobe.exe"
    executable.touch()
    monkeypatch.setenv("PATH", "foreign-tools")
    runner = Mock(
        return_value=subprocess.CompletedProcess(
            [str(executable), "-version"], 0, "ffprobe test version\n", ""
        )
    )
    monkeypatch.setattr("mtee.services.ffmpeg_runtime.subprocess.run", runner)

    result = FfmpegRuntime(tmp_path).run("ffprobe", ["-version"])

    assert result.returncode == 0
    args, kwargs = runner.call_args
    assert args[0] == [str(executable), "-version"]
    assert kwargs["shell"] is False
    assert kwargs["env"]["PATH"] == str(tmp_path)
    assert kwargs["timeout"] == 30


def test_run_rejects_unbounded_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        FfmpegRuntime(tmp_path).run("ffmpeg", [], timeout_seconds=0)


def test_version_uses_a_bounded_bundled_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ffmpeg.exe").touch()
    runtime = FfmpegRuntime(tmp_path)
    monkeypatch.setattr(
        runtime,
        "run",
        lambda tool, arguments, **kwargs: subprocess.CompletedProcess(
            [tool, *arguments], 0, "ffmpeg version test-build\nconfiguration\n", ""
        ),
    )

    assert runtime.version() == "ffmpeg version test-build"

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_pinned_ffmpeg_generates_and_probe_identifies_audio_fixtures(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    output = tmp_path / "audio"
    result = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / "create_audio_fixtures.py"),
            "--output",
            str(output),
            "--ffmpeg-dir",
            str(repository / "vendor" / "ffmpeg" / "bin"),
        ],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cover_art"]["file"] == "cover.png"
    assert (output / manifest["cover_art"]["file"]).is_file()
    by_id = {fixture["fixture_id"]: fixture for fixture in manifest["fixtures"]}
    assert len(by_id) == 9
    assert by_id["aac-adts"]["codec"] == "aac"
    assert by_id["m4a-aac"]["codec"] == "aac"
    assert by_id["m4a-alac"]["codec"] == "alac"
    assert by_id["mp3"]["codec"] == "mp3"
    assert all(
        float(item["duration_seconds"]) == pytest.approx(3, abs=0.1) for item in by_id.values()
    )
    assert all((tmp_path / "audio" / item["file"]).is_file() for item in by_id.values())

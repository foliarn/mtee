from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_fixture_generator_refuses_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "not-empty"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "scripts" / "create_audio_fixtures.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )

    assert result.returncode != 0
    assert "non-empty fixture folder" in result.stderr
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"

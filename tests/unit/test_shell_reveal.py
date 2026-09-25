from __future__ import annotations

from pathlib import Path

import pytest

from mtee.services.platform.shell_reveal import WindowsShellReveal


def test_reveal_passes_unicode_and_punctuation_as_one_argument(tmp_path: Path) -> None:
    target = tmp_path / "Café, live set's track.wav"
    target.write_bytes(b"audio fixture")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(arguments: list[str], **options: object) -> None:
        calls.append((arguments, options))

    WindowsShellReveal(runner).reveal(target)

    assert calls[0][0] == ["explorer.exe", f"/select,{target.resolve()}"]
    assert calls[0][1]["close_fds"] is True
    assert "shell" not in calls[0][1]


def test_reveal_reports_a_missing_source_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        WindowsShellReveal(lambda *_args, **_kwargs: None).reveal(tmp_path / "missing.wav")

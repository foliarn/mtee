"""Arguments recognised by the application."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.cli import parse_arguments


def test_a_run_without_argument_uses_the_normal_mode() -> None:
    options = parse_arguments([])

    assert options.data_dir is None
    assert options.demo is False
    assert options.smoke_test is False


def test_the_recipe_options_are_recognised(tmp_path: Path) -> None:
    options = parse_arguments(["--data-dir", str(tmp_path), "--demo", "--smoke-test"])

    assert options.data_dir == tmp_path
    assert options.demo is True
    assert options.smoke_test is True


def test_an_unknown_argument_is_refused_with_the_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_arguments(["--play-everything"])

    assert exit_info.value.code == 2
    assert "usage: mtee" in capsys.readouterr().err


def test_the_help_lists_the_supported_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_arguments(["--help"])

    assert exit_info.value.code == 0
    printed = capsys.readouterr().out
    assert "--data-dir" in printed
    assert "--demo" in printed
    assert "--smoke-test" in printed

from __future__ import annotations

from pathlib import Path

from tests.helpers.analysis_audio import write_music_fixture

from mtee.app import EXIT_OK, main


def test_analysis_smoke_command_runs_every_analyzer_in_an_isolated_data_dir(
    tmp_path: Path, capsys
) -> None:
    fixture = tmp_path / "copy of the source.wav"
    write_music_fixture(fixture)
    data_dir = tmp_path / "analysis-output"

    result = main(
        [
            "mtee",
            "--analysis-smoke-test",
            str(fixture),
            "--data-dir",
            str(data_dir),
        ]
    )

    captured = capsys.readouterr()
    assert result == EXIT_OK, captured.err
    output = captured.out
    assert '"source_unchanged": true' in output
    for analyzer in ("technical", "silence", "loudness", "tempo", "key"):
        assert f'"name": "{analyzer}"' in output
    assert (data_dir / "mtee.sqlite3").is_file()

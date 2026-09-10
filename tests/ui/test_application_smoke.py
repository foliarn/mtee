"""Start-up of the window, isolation of the data and persistence of a setting."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtee.app import EXIT_OK, EXIT_STORAGE_ERROR, main
from mtee.assets import main_qml, qml_dir
from mtee.models.shell_controller import SETTING_DETAILS_VISIBLE
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.app_paths import resolve_app_paths


def test_the_window_loads_and_quits_with_a_success_code(qapp, tmp_path: Path) -> None:
    exit_code = main(["mtee", "--data-dir", str(tmp_path / "run"), "--smoke-test"])

    assert exit_code == EXIT_OK
    assert (tmp_path / "run" / "mtee.sqlite3").is_file()
    assert (tmp_path / "run" / "cache").is_dir()
    assert (tmp_path / "run" / "logs").is_dir()


def test_a_path_with_spaces_and_accents_is_supported(qapp, tmp_path: Path) -> None:
    directory = tmp_path / "Ma collection épurée"

    assert main(["mtee", "--data-dir", str(directory), "--smoke-test"]) == EXIT_OK
    assert (directory / "mtee.sqlite3").is_file()


def test_demo_mode_never_touches_the_settings_of_a_normal_run(qapp, tmp_path: Path) -> None:
    normal = resolve_app_paths(tmp_path / "shared")
    assert main(["mtee", "--data-dir", str(tmp_path / "shared"), "--smoke-test"]) == EXIT_OK
    database = Database(normal.database_path)
    database.migrate()
    SettingsRepository(database).set(SETTING_DETAILS_VISIBLE, "true")
    database.close()

    demo_run = main(["mtee", "--data-dir", str(tmp_path / "shared"), "--demo", "--smoke-test"])
    assert demo_run == EXIT_OK

    demo = resolve_app_paths(tmp_path / "shared", demo=True)
    assert demo.database_path.is_file()
    assert demo.database_path != normal.database_path
    reopened = Database(normal.database_path)
    reopened.migrate()
    assert SettingsRepository(reopened).get(SETTING_DETAILS_VISIBLE) == "true"
    reopened.close()


def test_a_setting_survives_a_restart(qapp, tmp_path: Path) -> None:
    directory = tmp_path / "run"
    assert main(["mtee", "--data-dir", str(directory), "--smoke-test"]) == EXIT_OK

    database = Database(resolve_app_paths(directory).database_path)
    database.migrate()
    SettingsRepository(database).set_json(SETTING_DETAILS_VISIBLE, True)
    database.close()

    assert main(["mtee", "--data-dir", str(directory), "--smoke-test"]) == EXIT_OK

    reopened = Database(resolve_app_paths(directory).database_path)
    reopened.migrate()
    assert SettingsRepository(reopened).get_json(SETTING_DETAILS_VISIBLE) is True
    reopened.close()


def test_an_unusable_data_directory_is_reported_without_a_window(
    qapp,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("occupied", encoding="utf-8")

    exit_code = main(["mtee", "--data-dir", str(blocking_file), "--smoke-test"])

    assert exit_code == EXIT_STORAGE_ERROR
    assert "MTEE" in capsys.readouterr().err


def test_the_interface_files_travel_with_the_package() -> None:
    assert main_qml().is_file()
    assert (qml_dir() / "Mtee" / "qmldir").is_file()
    assert (qml_dir() / "Mtee" / "Theme.qml").is_file()

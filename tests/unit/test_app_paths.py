"""Failure and isolation cases of the application directories."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths

from mtee.services.app_paths import DEMO_DIRECTORY_NAME, AppPaths, resolve_app_paths


def test_data_dir_option_keeps_every_directory_under_one_root(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path / "recipe")

    assert paths.data_dir == (tmp_path / "recipe").resolve()
    assert paths.cache_dir.is_relative_to(paths.data_dir)
    assert paths.logs_dir.is_relative_to(paths.data_dir)
    assert paths.database_path.parent == paths.data_dir


def test_demo_mode_never_shares_the_directory_of_a_normal_run(tmp_path: Path) -> None:
    normal = resolve_app_paths(tmp_path)
    demo = resolve_app_paths(tmp_path, demo=True)

    assert demo.data_dir != normal.data_dir
    assert demo.data_dir.name == DEMO_DIRECTORY_NAME
    assert demo.database_path != normal.database_path


def test_standard_locations_stay_outside_the_repository(tmp_path: Path) -> None:
    QStandardPaths.setTestModeEnabled(True)
    paths = resolve_app_paths()

    repository_root = Path(__file__).resolve().parents[2]
    assert not paths.data_dir.is_relative_to(repository_root)
    assert not paths.cache_dir.is_relative_to(repository_root)


def test_ensure_creates_the_missing_directories(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path / "created")
    assert not paths.data_dir.exists()

    ensured = paths.ensure()

    assert ensured is paths
    assert paths.data_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.logs_dir.is_dir()


def test_ensure_is_repeatable_on_an_existing_directory(tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "a", tmp_path / "b", tmp_path / "c").ensure()
    marker = paths.data_dir / "keep.txt"
    marker.write_text("kept", encoding="utf-8")

    paths.ensure()

    assert marker.read_text(encoding="utf-8") == "kept"

"""Normalization is on at Normal by default, and the choices survive a restart."""

from __future__ import annotations

from pathlib import Path

from mtee.models.playback_settings_model import SETTING_NORMALIZATION, PlaybackSettingsModel
from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository


def _repository(tmp_path: Path) -> SettingsRepository:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    return SettingsRepository(database)


def test_a_fresh_installation_normalizes_at_normal(tmp_path: Path) -> None:
    model = PlaybackSettingsModel(_repository(tmp_path))

    assert model.normalizationEnabled is True
    assert model.normalizationLevel == "normal"


def test_the_choices_are_stored_and_restored(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    model = PlaybackSettingsModel(repository)
    changed: list[bool] = []
    model.changed.connect(lambda: changed.append(True))

    model.setNormalizationEnabled(False)
    model.setNormalizationLevel("loud")

    assert changed == [True, True]
    restored = PlaybackSettingsModel(repository)
    assert restored.normalizationEnabled is False
    assert restored.normalizationLevel == "loud"


def test_an_unknown_level_is_ignored(tmp_path: Path) -> None:
    model = PlaybackSettingsModel(_repository(tmp_path))

    model.setNormalizationLevel("deafening")

    assert model.normalizationLevel == "normal"


def test_setting_the_same_value_does_not_notify(tmp_path: Path) -> None:
    model = PlaybackSettingsModel(_repository(tmp_path))
    changed: list[bool] = []
    model.changed.connect(lambda: changed.append(True))

    model.setNormalizationEnabled(True)
    model.setNormalizationLevel("normal")

    assert changed == []


def test_a_corrupted_stored_value_falls_back_to_the_defaults(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.set(SETTING_NORMALIZATION, "{not json")

    model = PlaybackSettingsModel(repository)

    assert model.normalizationEnabled is True
    assert model.normalizationLevel == "normal"


def test_a_stored_value_of_the_wrong_type_keeps_the_other_choice(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.set_json(SETTING_NORMALIZATION, {"enabled": "no", "level": "quiet"})

    model = PlaybackSettingsModel(repository)

    assert model.normalizationEnabled is True
    assert model.normalizationLevel == "quiet"

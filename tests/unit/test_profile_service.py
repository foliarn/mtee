"""Profile storage: display name, the migrated playlist creator and the avatar copy."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from mtee.persistence.database import Database
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services import profile_service
from mtee.services.profile_service import (
    AVATAR_KEY,
    DEFAULT_CREATOR,
    DISPLAY_NAME_KEY,
    LEGACY_CREATOR_KEY,
    ProfileService,
    normalize_display_name,
)


@pytest.fixture
def settings(tmp_path: Path) -> Iterator[SettingsRepository]:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    yield SettingsRepository(database)
    database.close()


def _png(path: Path, color: str = "#256f82") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(32, 32, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_display_name_is_stripped_and_bounded() -> None:
    assert normalize_display_name("  Ana  ") == "Ana"
    with pytest.raises(ValueError):
        normalize_display_name("   ")
    with pytest.raises(ValueError):
        normalize_display_name("x" * 241)
    assert normalize_display_name("x" * 240) == "x" * 240


def test_display_name_is_stored_and_used_as_playlist_creator(
    settings: SettingsRepository, tmp_path: Path
) -> None:
    profile = ProfileService(settings, tmp_path / "profile")
    assert profile.display_name() == ""
    assert profile.playlist_creator() == DEFAULT_CREATOR
    profile.set_display_name("  Ana Lima ")
    assert settings.get(DISPLAY_NAME_KEY) == "Ana Lima"
    assert ProfileService(settings, tmp_path / "profile").playlist_creator() == "Ana Lima"


def test_former_playlist_creator_is_migrated_once(
    settings: SettingsRepository, tmp_path: Path
) -> None:
    settings.set(LEGACY_CREATOR_KEY, "Local curator")
    profile = ProfileService(settings, tmp_path / "profile")
    assert profile.display_name() == "Local curator"
    assert settings.get(LEGACY_CREATOR_KEY) is None
    # A second start changes nothing, and a later name wins over the old value.
    profile.set_display_name("Ana")
    ProfileService(settings, tmp_path / "profile")
    assert profile.display_name() == "Ana"


def test_an_existing_display_name_wins_over_the_legacy_value(
    settings: SettingsRepository, tmp_path: Path
) -> None:
    settings.set(DISPLAY_NAME_KEY, "Ana")
    settings.set(LEGACY_CREATOR_KEY, "Old name")
    profile = ProfileService(settings, tmp_path / "profile")
    assert profile.display_name() == "Ana"
    assert settings.get(LEGACY_CREATOR_KEY) is None


def test_an_invalid_legacy_value_is_dropped(settings: SettingsRepository, tmp_path: Path) -> None:
    settings.set(LEGACY_CREATOR_KEY, "   ")
    profile = ProfileService(settings, tmp_path / "profile")
    assert profile.display_name() == ""
    assert settings.get(LEGACY_CREATOR_KEY) is None


def test_avatar_is_a_copy_and_the_source_is_untouched(
    qapp, settings: SettingsRepository, tmp_path: Path
) -> None:
    source = _png(tmp_path / "pictures" / "me.png")
    before = _digest(source)
    profile = ProfileService(settings, tmp_path / "profile")
    assert profile.avatar_path() is None

    stored = profile.set_avatar(source)

    assert stored.parent == tmp_path / "profile"
    assert stored.suffix == ".png"
    assert stored != source
    assert profile.avatar_path() == stored
    assert _digest(stored) == before
    assert _digest(source) == before


def test_replacing_the_avatar_removes_the_previous_copy(
    qapp, settings: SettingsRepository, tmp_path: Path
) -> None:
    profile = ProfileService(settings, tmp_path / "profile")
    first = profile.set_avatar(_png(tmp_path / "a.png"))
    second = profile.set_avatar(_png(tmp_path / "b.png", "#ff2e88"))
    assert first != second
    assert not first.exists()
    assert second.exists()
    assert profile.avatar_path() == second

    profile.clear_avatar()
    assert not second.exists()
    assert profile.avatar_path() is None
    assert settings.get(AVATAR_KEY) is None


def test_a_file_that_is_not_an_image_is_refused(
    qapp, settings: SettingsRepository, tmp_path: Path
) -> None:
    text = tmp_path / "notes.png"
    text.write_text("this is not a picture", encoding="utf-8")
    profile = ProfileService(settings, tmp_path / "profile")
    with pytest.raises(ValueError, match="PNG, JPEG"):
        profile.set_avatar(text)
    assert not (tmp_path / "profile").exists() or not any((tmp_path / "profile").iterdir())
    assert profile.avatar_path() is None


def test_a_missing_or_oversized_file_is_refused(
    qapp, settings: SettingsRepository, tmp_path: Path, monkeypatch
) -> None:
    profile = ProfileService(settings, tmp_path / "profile")
    with pytest.raises(ValueError, match="does not exist"):
        profile.set_avatar(tmp_path / "missing.png")
    picture = _png(tmp_path / "big.png")
    monkeypatch.setattr(profile_service, "MAX_AVATAR_BYTES", 10)
    with pytest.raises(ValueError, match="10 MB"):
        profile.set_avatar(picture)


def test_a_stored_avatar_name_cannot_point_outside_the_profile_folder(
    settings: SettingsRepository, tmp_path: Path
) -> None:
    settings.set(AVATAR_KEY, "../../secret.png")
    profile = ProfileService(settings, tmp_path / "profile")
    assert profile.avatar_path() is None

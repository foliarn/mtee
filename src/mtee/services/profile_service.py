"""The local profile: display name and avatar image, kept in the app data directory.

The display name is the name written on the playlists (it replaces the former
"Playlist creator name" setting, whose stored value is migrated). The avatar is a
byte copy of an image chosen by the user, stored under the profile directory; the
source file is only read. No e-mail, password or server field exists in v0.1.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from PySide6.QtGui import QImageReader

from mtee.persistence.settings_repository import SettingsRepository

__all__ = [
    "AVATAR_FORMATS",
    "DEFAULT_CREATOR",
    "DISPLAY_NAME_KEY",
    "MAX_AVATAR_BYTES",
    "MAX_DISPLAY_NAME_LENGTH",
    "PROFILE_DIRECTORY_NAME",
    "ProfileService",
    "normalize_display_name",
]

PROFILE_DIRECTORY_NAME = "profile"
DISPLAY_NAME_KEY = "profile/display_name"
AVATAR_KEY = "profile/avatar_file"
LEGACY_CREATOR_KEY = "playlists/creator"
# Shown on playlists when no display name is set; the value existed before the profile.
DEFAULT_CREATOR = "MTEE"
MAX_DISPLAY_NAME_LENGTH = 240
MAX_AVATAR_BYTES = 10 * 1024 * 1024
# Qt image format name to the extension of the stored copy.
AVATAR_FORMATS: dict[str, str] = {
    "png": ".png",
    "jpeg": ".jpg",
    "webp": ".webp",
    "bmp": ".bmp",
    "gif": ".gif",
}


def normalize_display_name(value: str) -> str:
    """Return the stripped name, or raise ``ValueError`` when it is empty or too long."""
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(f"Use a display name between 1 and {MAX_DISPLAY_NAME_LENGTH} characters.")
    return cleaned


class ProfileService:
    """Reads and writes the display name and the avatar of the single local profile."""

    def __init__(self, settings: SettingsRepository, profile_dir: Path) -> None:
        self._settings = settings
        self._profile_dir = profile_dir
        self.migrate_legacy_creator()

    @property
    def profile_dir(self) -> Path:
        return self._profile_dir

    def display_name(self) -> str:
        """Return the stored display name, or an empty string when none is set."""
        return self._settings.get(DISPLAY_NAME_KEY, "") or ""

    def playlist_creator(self) -> str:
        """The name written on playlists: the display name, or the default when empty."""
        return self.display_name() or DEFAULT_CREATOR

    def set_display_name(self, value: str) -> str:
        name = normalize_display_name(value)
        self._settings.set(DISPLAY_NAME_KEY, name)
        return name

    def avatar_path(self) -> Path | None:
        """Return the stored avatar file, or ``None`` when there is none on disk."""
        stored = self._settings.get(AVATAR_KEY, "") or ""
        if not stored or Path(stored).name != stored:
            return None
        path = self._profile_dir / stored
        return path if path.is_file() else None

    def set_avatar(self, source: Path) -> Path:
        """Copy the image ``source`` into the profile directory and make it the avatar.

        The source is only read. The previous avatar copy is removed after the new one
        is in place, so a failure leaves the old avatar usable.
        """
        image_format = validate_avatar_source(source)
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        destination = self._profile_dir / f"avatar-{uuid4().hex}{AVATAR_FORMATS[image_format]}"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        previous = self._settings.get(AVATAR_KEY, "") or ""
        self._settings.set(AVATAR_KEY, destination.name)
        if previous and Path(previous).name == previous and previous != destination.name:
            (self._profile_dir / previous).unlink(missing_ok=True)
        return destination

    def clear_avatar(self) -> None:
        previous = self._settings.get(AVATAR_KEY, "") or ""
        self._settings.delete(AVATAR_KEY)
        if previous and Path(previous).name == previous:
            (self._profile_dir / previous).unlink(missing_ok=True)

    def migrate_legacy_creator(self) -> bool:
        """Move the former playlist creator setting into the display name, once.

        Returns whether a value was moved. A display name that is already set wins, and
        an invalid legacy value is dropped rather than kept under the old key.
        """
        legacy = self._settings.get(LEGACY_CREATOR_KEY)
        if legacy is None:
            return False
        if not self.display_name():
            try:
                self._settings.set(DISPLAY_NAME_KEY, normalize_display_name(legacy))
                moved = True
            except ValueError:
                moved = False
        else:
            moved = False
        self._settings.delete(LEGACY_CREATOR_KEY)
        return moved


def validate_avatar_source(source: Path) -> str:
    """Return the image format of ``source`` or raise ``ValueError`` with the reason."""
    if not source.is_file():
        raise ValueError("The chosen avatar file does not exist.")
    size = source.stat().st_size
    if size == 0 or size > MAX_AVATAR_BYTES:
        raise ValueError("Choose an image of at most 10 MB.")
    reader = QImageReader(str(source))
    image_format = bytes(reader.format().data()).decode("ascii", "replace").lower()
    if image_format not in AVATAR_FORMATS or not reader.canRead():
        raise ValueError("Choose a PNG, JPEG, WebP, BMP or GIF image.")
    return image_format

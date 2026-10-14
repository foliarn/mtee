"""Qt model of the local profile: display name and avatar (plan 114).

QML never reads the avatar file. It asks the ``profile`` image provider for the image;
the provider reads the copy stored under the profile directory. The avatar copy runs as a
background job, because it copies a file of up to 10 MB.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, QSize, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from mtee.services.jobs import JobContext, JobService
from mtee.services.profile_service import ProfileService

__all__ = ["PROFILE_PROVIDER_ID", "ProfileAvatarProvider", "ProfileModel"]

PROFILE_PROVIDER_ID = "profile"


class ProfileAvatarProvider(QQuickImageProvider):
    """Serve the current avatar as ``image://profile/<revision>``; the revision busts caches."""

    def __init__(self, profile: ProfileService) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._profile = profile

    def requestImage(self, image_id: str, size: QSize, requested_size: QSize) -> QImage:
        del image_id, size, requested_size
        path = self._profile.avatar_path()
        if path is None:
            return QImage()
        return QImage(str(path))


class ProfileModel(QObject):
    """Expose the display name and the avatar to the Profile page, and change them."""

    changed = Signal()
    nameChanged = Signal(str)
    noticeRaised = Signal(str)
    _avatarReady = Signal(str)

    def __init__(
        self,
        profile: ProfileService,
        jobs: JobService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._jobs = jobs
        self._revision = 0
        self._busy = False
        self._avatarReady.connect(self._on_avatar_ready)

    @property
    def service(self) -> ProfileService:
        return self._profile

    @Property(str, notify=changed)
    def displayName(self) -> str:
        return self._profile.display_name()

    @Property(bool, notify=changed)
    def hasAvatar(self) -> bool:
        return self._profile.avatar_path() is not None

    @Property(str, notify=changed)
    def avatarSource(self) -> str:
        """An image-provider URL, or an empty string when no avatar is set."""
        if not self.hasAvatar:
            return ""
        return f"image://{PROFILE_PROVIDER_ID}/{self._revision}"

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._busy

    @Slot(str)
    def setDisplayName(self, value: str) -> None:
        try:
            name = self._profile.set_display_name(value)
        except ValueError as error:
            self.noticeRaised.emit(str(error))
            return
        self.changed.emit()
        # The playlists show the creator name; the app connects this to their refresh.
        self.nameChanged.emit(name)

    @Slot(str)
    def setAvatarFrom(self, url: str) -> None:
        """Copy the image at the local file ``url`` as the avatar, in the background."""
        source = QUrl(url).toLocalFile()
        if not source:
            self.noticeRaised.emit("Choose an image file on this computer.")
            return
        self._set_busy(True)
        path = Path(source)

        def task(context: JobContext) -> None:
            del context
            try:
                self._profile.set_avatar(path)
            except (OSError, ValueError) as error:
                self._avatarReady.emit(str(error))
                return
            self._avatarReady.emit("")

        self._jobs.submit(task, label="Copy profile picture", visible=False)

    @Slot()
    def clearAvatar(self) -> None:
        self._profile.clear_avatar()
        self._revision += 1
        self.changed.emit()

    @Slot(str)
    def _on_avatar_ready(self, error: str) -> None:
        self._set_busy(False)
        if error:
            self.noticeRaised.emit(error)
            return
        self._revision += 1
        self.changed.emit()

    def _set_busy(self, value: bool) -> None:
        self._busy = value
        self.changed.emit()

"""Qt models of the Profile and Data & privacy pages, with the jobs run inline."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QColor, QImage

from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.models.data_privacy_model import DataPrivacyModel
from mtee.models.profile_model import ProfileAvatarProvider, ProfileModel
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository, load_or_create_device_id
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.data_privacy import RestoreLayout
from mtee.services.profile_service import DISPLAY_NAME_KEY, ProfileService

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


class InlineJobs:
    def __init__(self) -> None:
        self.labels: list[str] = []

    def submit(self, task, *, label: str = "", visible: bool = True, **_kwargs) -> str:
        self.labels.append(label)
        with suppress(Exception):  # a failing job reports through its own signal
            task(None)
        return "job"


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(tmp_path / "data" / "mtee.sqlite3")
    db.migrate()
    yield db
    db.close()


def _url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def _png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(QColor("#c6ff1a"))
    assert image.save(str(path), "PNG")
    return path


def test_profile_model_changes_the_name_and_announces_it(qapp, database, tmp_path) -> None:
    profile = ProfileService(SettingsRepository(database), tmp_path / "data" / "profile")
    model = ProfileModel(profile, InlineJobs())
    announced: list[str] = []
    notices: list[str] = []
    model.nameChanged.connect(announced.append)
    model.noticeRaised.connect(notices.append)

    model.setDisplayName("   ")
    assert notices and announced == []

    model.setDisplayName("  Ana ")
    assert model.displayName == "Ana"
    assert announced == ["Ana"]
    assert SettingsRepository(database).get(DISPLAY_NAME_KEY) == "Ana"


def test_profile_model_copies_an_avatar_and_serves_it_as_an_image(qapp, database, tmp_path) -> None:
    profile = ProfileService(SettingsRepository(database), tmp_path / "data" / "profile")
    model = ProfileModel(profile, InlineJobs())
    assert model.avatarSource == ""

    model.setAvatarFrom(_url(_png(tmp_path / "pictures" / "me.png")))

    assert model.hasAvatar
    assert model.avatarSource.startswith("image://profile/")
    assert model.busy is False
    image = ProfileAvatarProvider(profile).requestImage("1", QSize(), QSize())
    assert not image.isNull()


def test_profile_model_reports_a_refused_avatar_and_releases_busy(qapp, database, tmp_path) -> None:
    profile = ProfileService(SettingsRepository(database), tmp_path / "data" / "profile")
    model = ProfileModel(profile, InlineJobs())
    notices: list[str] = []
    model.noticeRaised.connect(notices.append)
    text = tmp_path / "notes.png"
    text.write_text("plain text", encoding="utf-8")

    model.setAvatarFrom(_url(text))

    assert notices and "PNG, JPEG" in notices[0]
    assert model.busy is False
    assert model.hasAvatar is False


def test_data_privacy_model_backs_up_resets_and_schedules_a_restore(
    qapp, database, tmp_path
) -> None:
    settings = SettingsRepository(database)
    device = load_or_create_device_id(settings)
    play_log = PlayLogRepository(database)
    started = NOW - timedelta(hours=1)
    play_log.insert_events(
        [
            PlayEvent(
                event_id=str(uuid4()),
                track=PlayedTrack(track_id="a", path="a.mp3"),
                started_at=started,
                ended_at=started + timedelta(seconds=35),
                heard_ms=35_000,
                counted=True,
            )
        ],
        device,
    )
    layout = RestoreLayout(tmp_path / "data")
    model = DataPrivacyModel(database, layout, play_log, InlineJobs(), clock=lambda: NOW)
    finished: list[str] = []
    notices: list[str] = []
    model.finished.connect(finished.append)
    model.noticeRaised.connect(notices.append)

    backup = tmp_path / "backups" / "mtee-backup.sqlite3"
    backup.parent.mkdir(parents=True)
    model.backUpTo(_url(backup))
    assert backup.is_file()
    assert finished[0] == "Backup saved as mtee-backup.sqlite3."
    model.backUpTo(_url(backup))
    assert notices and "already exists" in notices[-1]

    model.restoreFrom(_url(backup))
    assert model.pendingRestore["sourceName"] == "mtee-backup.sqlite3"
    model.cancelRestore()
    assert model.pendingRestore == {}

    model.resetStatistics()
    assert finished[-1] == "Statistics reset. Listening events removed: 1."
    assert play_log.totals().sessions == 0
    assert model.busy is False

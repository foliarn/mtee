"""Queue rows remain attached to the service queue, not the explorer selection."""

from __future__ import annotations

from pathlib import Path

from mtee.domain.playback import PlaybackStatus
from mtee.domain.tracks import TrackId
from mtee.models.player_model import PlayerModel
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.player_backend import BackendEvent, BackendEventHandler
from mtee.services.player_service import PlayerService


class QueueBackend:
    def __init__(self) -> None:
        self.handler: BackendEventHandler | None = None
        self.loads: list[int] = []
        self.current_position = 0
        self.active_session_id = 0

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        self.handler = handler

    def load(self, path: Path, session_id: int) -> None:
        del path
        self.active_session_id = session_id
        self.loads.append(session_id)
        self.emit("duration", session_id, 2_000_000)
        self.emit("seekable", session_id, True)
        self.emit("loaded", session_id)

    def set_paused(self, paused: bool) -> None:
        del paused
        return

    def seek(self, position_us: int) -> None:
        self.current_position = position_us

    def set_volume(self, value: int) -> None:
        del value
        return

    def position_us(self) -> int:
        return self.current_position

    def stop(self) -> None:
        self.emit("stopped", self.active_session_id)

    def close(self) -> None:
        return

    def emit(self, name: str, session_id: int, value: object = None) -> None:
        if self.handler is not None:
            self.handler(BackendEvent(name, session_id, value))


def test_queue_model_exposes_the_captured_order_and_selects_an_existing_row(
    qapp, qtbot, tmp_path: Path
) -> None:
    tracks: dict[str, dict[str, object]] = {}
    ids = []
    for index in range(3):
        track_id = str(TrackId.new())
        path = tmp_path / f"{index}.wav"
        path.write_bytes(b"synthetic fixture")
        ids.append(track_id)
        tracks[track_id] = {
            "id": track_id,
            "title": f"Track {index}",
            "artist": "Artist",
            "path": str(path),
            "seconds": 2,
            "durationUs": 2_000_000,
            "duration": "0:02",
        }
    backend = QueueBackend()
    service = PlayerService(
        lambda track_id: dict(tracks[track_id]), FileAccessCoordinator(), backend, parent=qapp
    )
    player = PlayerModel(service, qapp)
    captured = list(ids)
    player.playQueue(captured, 1, "folder:root/album", "Album")
    captured.reverse()

    qtbot.waitUntil(lambda: service.state.status is PlaybackStatus.PLAYING)
    model = player.queue_model()
    assert model.track_ids_snapshot() == ids
    assert model.count_value() == 3
    assert model.rows_snapshot()[1]["current"] is True
    assert player.playing_id_value() == ids[1]
    assert player.playing_track_value()["title"] == "Track 1"

    player.playIndex(2)
    qtbot.waitUntil(
        lambda: (
            service.state.status is PlaybackStatus.PLAYING and service.state.current_id == ids[2]
        )
    )
    assert model.track_ids_snapshot() == ids
    assert len(backend.loads) == 2
    service.close()

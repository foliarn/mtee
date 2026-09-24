"""Qt-facing playback state and transport commands."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.models.playback_queue_model import PlaybackQueueModel
from mtee.services.player_service import PlayerService

__all__ = ["PlayerModel"]


class PlayerModel(QObject):
    """One model shared by the island, queue and fullscreen player."""

    playbackChanged = Signal()

    def __init__(self, service: PlayerService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._queue_model = PlaybackQueueModel(service, self)
        service.stateChanged.connect(self.playbackChanged.emit)

    @Property(str, notify=playbackChanged)
    def status(self) -> str:
        return self.status_value()

    def status_value(self) -> str:
        return self._service.state.status.value

    @Property(str, notify=playbackChanged)
    def playingId(self) -> str:
        return self.playing_id_value()

    def playing_id_value(self) -> str:
        return self._service.state.current_id

    @Property(dict, notify=playbackChanged)
    def playingTrack(self) -> dict[str, Any]:
        return self.playing_track_value()

    def playing_track_value(self) -> dict[str, Any]:
        return self._service.current_track

    @Property(str, notify=playbackChanged)
    def playingSourceTitle(self) -> str:
        return self.playing_source_title_value()

    def playing_source_title_value(self) -> str:
        return self._service.state.source_title

    @Property(str, notify=playbackChanged)
    def playingSource(self) -> str:
        return self.playing_source_value()

    def playing_source_value(self) -> str:
        return self._service.state.source

    @Property(str, notify=playbackChanged)
    def playingSourceKind(self) -> str:
        return self.playing_source_kind_value()

    def playing_source_kind_value(self) -> str:
        return self._service.state.source.partition(":")[0]

    @Property(bool, notify=playbackChanged)
    def isPlaying(self) -> bool:
        return self._service.state.is_playing

    @Property(float, notify=playbackChanged)
    def position(self) -> float:
        return self.position_value()

    def position_value(self) -> float:
        return self._service.state.position_us / 1_000_000

    @Property(int, notify=playbackChanged)
    def positionUs(self) -> int:
        return self._service.state.position_us

    @Property(float, notify=playbackChanged)
    def duration(self) -> float:
        duration = self._service.state.duration_us
        if duration is not None:
            return duration / 1_000_000
        return float(self._service.current_track.get("seconds", 0) or 0)

    @Property(int, notify=playbackChanged)
    def durationUs(self) -> int:
        return self._service.state.duration_us or 0

    @Property(bool, notify=playbackChanged)
    def seekable(self) -> bool:
        return self._service.state.seekable

    @Property(bool, notify=playbackChanged)
    def seeking(self) -> bool:
        return self._service.state.seeking

    @Property(int, notify=playbackChanged)
    def volume(self) -> int:
        return self._service.state.volume

    @Property(bool, notify=playbackChanged)
    def muted(self) -> bool:
        return self._service.state.muted

    @Property(bool, notify=playbackChanged)
    def shuffle(self) -> bool:
        return self._service.state.shuffle

    @Property(str, notify=playbackChanged)
    def repeat(self) -> str:
        return self._service.state.repeat

    @Property(str, notify=playbackChanged)
    def errorMessage(self) -> str:
        return self._service.state.error_message

    @Property(str, notify=playbackChanged)
    def codec(self) -> str:
        return self._service.state.codec

    @Property(QObject, constant=True)
    def queueModel(self) -> QObject:
        return self._queue_model

    def queue_model(self) -> PlaybackQueueModel:
        return self._queue_model

    @Property(bool, constant=True)
    def hasQueueModel(self) -> bool:
        return True

    @Property(list, notify=playbackChanged)
    def upNext(self) -> list[dict[str, Any]]:
        return self._service.up_next()

    @Property(list, notify=playbackChanged)
    def history(self) -> list[dict[str, Any]]:
        return self._service.history_rows()

    def is_playing_value(self) -> bool:
        return self._service.state.is_playing

    def volume_value(self) -> int:
        return self._service.state.volume

    def muted_value(self) -> bool:
        return self._service.state.muted

    def shuffle_value(self) -> bool:
        return self._service.state.shuffle

    def repeat_value(self) -> str:
        return self._service.state.repeat

    def up_next_value(self) -> list[dict[str, Any]]:
        return self._service.up_next()

    def history_value(self) -> list[dict[str, Any]]:
        return self._service.history_rows()

    @Slot(list, int, str, str)
    def playQueue(
        self,
        track_ids: list,
        start_index: int,
        source: str = "",
        source_title: str = "",
    ) -> None:
        self._service.play_queue(
            [str(track_id) for track_id in track_ids],
            int(start_index),
            source=source,
            source_title=source_title,
        )

    @Slot(int)
    def playIndex(self, index: int) -> None:
        self._service.play_index(int(index))

    @Slot()
    def togglePlay(self) -> None:
        self._service.toggle_play()

    @Slot()
    def previous(self) -> None:
        self._service.previous()

    @Slot()
    def next(self) -> None:
        self._service.next()

    @Slot(float)
    def seek(self, seconds: float) -> None:
        self._service.seek(round(max(0.0, float(seconds)) * 1_000_000))

    @Slot(int)
    def seekUs(self, position_us: int) -> None:
        self._service.seek(int(position_us))

    @Slot(int)
    def setVolume(self, value: int) -> None:
        self._service.set_volume(int(value))

    @Slot()
    def toggleMute(self) -> None:
        self._service.toggle_mute()

    @Slot()
    def toggleShuffle(self) -> None:
        self._service.toggle_shuffle()

    @Slot()
    def cycleRepeat(self) -> None:
        self._service.cycle_repeat()

    @Slot()
    def retry(self) -> None:
        self._service.retry()

    @Slot(str, result=bool)
    def stopAndRelease(self, track_id: str = "") -> bool:
        return self._service.stop_and_release(track_id)

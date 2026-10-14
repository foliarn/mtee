"""Qt-facing playback state and transport commands."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QByteArray, QElapsedTimer, QObject, QTimer, Signal, Slot

from mtee.domain.playback import PlaybackStatus
from mtee.domain.scrub import EnsurePlaying, Next, ScrubCommand, ScrubSession, Seek, Silence
from mtee.models.cover_accent_model import CoverAccentModel
from mtee.models.playback_history_model import PlaybackHistoryModel
from mtee.models.playback_queue_model import PlaybackQueueModel
from mtee.models.waveform_model import WaveformModel
from mtee.services.player_service import PlayerService

__all__ = ["PlayerModel"]

_SCRUB_TICK_MS = 20
_SEEK_END_GUARD_US = 200_000


class PlayerModel(QObject):
    """One model shared by the island, queue and fullscreen player."""

    playbackChanged = Signal()
    positionChanged = Signal()
    trackAccessReleased = Signal(str)
    scrubbingChanged = Signal()
    levelsChanged = Signal()

    def __init__(
        self,
        service: PlayerService,
        parent: QObject | None = None,
        *,
        waveform: WaveformModel | None = None,
        accent: CoverAccentModel | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._waveform = waveform
        self._accent = accent
        self._queue_model = PlaybackQueueModel(service, self)
        self._upcoming_queue_model = PlaybackQueueModel(service, self, upcoming_only=True)
        self._history_model = PlaybackHistoryModel(service, self)
        self._scrub: ScrubSession | None = None
        self._clock = QElapsedTimer()
        self._clock.start()
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setInterval(_SCRUB_TICK_MS)
        self._scrub_timer.timeout.connect(self._scrub_tick)
        service.stateChanged.connect(self.playbackChanged.emit)
        service.positionChanged.connect(self.positionChanged.emit)
        service.trackAccessReleased.connect(self.trackAccessReleased.emit)

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

    @Property(str, notify=playbackChanged)
    def currentEntryId(self) -> str:
        return self._service.state.current_entry_id

    @Property(int, notify=playbackChanged)
    def queueRevision(self) -> int:
        return self._service.queue_state.revision

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

    @Property(bool, notify=playbackChanged)
    def pausePending(self) -> bool:
        return self._service.pause_pending

    @Property(float, notify=positionChanged)
    def position(self) -> float:
        return self.position_value()

    def position_value(self) -> float:
        return self._service.state.position_us / 1_000_000

    @Property(int, notify=positionChanged)
    def positionUs(self) -> int:
        return self._service.state.position_us

    @Property(float, notify=playbackChanged)
    def duration(self) -> float:
        duration = self._service.state.duration_us
        if duration is not None:
            return duration / 1_000_000
        return float(self._service.current_track.get("seconds", 0) or 0)

    @Property(float, notify=playbackChanged)
    def playbackDuration(self) -> float:
        """Duration reported by the playback engine, without metadata fallback."""
        duration = self._service.state.duration_us
        if duration is not None and duration > 0:
            return duration / 1_000_000
        return 0.0

    @Property(int, notify=playbackChanged)
    def durationUs(self) -> int:
        return self._service.state.duration_us or 0

    @Property(bool, notify=playbackChanged)
    def seekable(self) -> bool:
        return self._service.state.seekable

    @Property(bool, notify=positionChanged)
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

    @Property(QObject, constant=True)
    def upcomingQueueModel(self) -> QObject:
        return self._upcoming_queue_model

    @Property(QObject, constant=True)
    def historyModel(self) -> QObject:
        return self._history_model

    @Property(bool, constant=True)
    def hasHistoryModel(self) -> bool:
        return True

    @Property(QObject, constant=True)
    def waveformModel(self) -> QObject:
        return self._waveform if self._waveform is not None else self

    @Property(str, notify=playbackChanged)
    def state(self) -> str:
        return "idle"

    @Property(float, notify=playbackChanged)
    def progress(self) -> float:
        return 0.0

    @Property(str, notify=playbackChanged)
    def error(self) -> str:
        return ""

    @Property(QObject, constant=True)
    def accent(self) -> QObject:
        """Accent colour of the playing cover; this model itself (no accent) when unattached."""
        return self._accent if self._accent is not None else self

    @Property(str, constant=True)
    def baseColor(self) -> str:
        return ""

    @Property(str, constant=True)
    def darkColor(self) -> str:
        return ""

    @Property(str, constant=True)
    def foregroundColor(self) -> str:
        return "#FFFFFF"

    @Property(bool, constant=True)
    def isLight(self) -> bool:
        return False

    @Property(bool, constant=True)
    def hasAccent(self) -> bool:
        return False

    @Property(QByteArray, notify=levelsChanged)
    def levels(self) -> QByteArray:
        """Stand-in for ``WaveformModel.levels`` when no waveform model is attached."""
        return QByteArray()

    @Slot(int)
    def setBarCount(self, count: int) -> None:
        return

    @Slot(float)
    def seekRatio(self, ratio: float) -> None:
        duration = self._service.state.duration_us or 0
        self._service.seek(round(max(0.0, min(1.0, ratio)) * duration))

    @Property(bool, notify=scrubbingChanged)
    def scrubbing(self) -> bool:
        return self._scrub is not None

    @Slot(float, float)
    def scrubPress(self, ratio: float, width_px: float) -> None:
        """Start a scrub on the waveform; ``ratio`` is the pressed point, ``width_px`` its width."""
        if self._scrub is not None or width_px <= 0 or not self._service.state.seekable:
            return
        self._scrub = ScrubSession(float(width_px))
        self.scrubbingChanged.emit()
        self._scrub_timer.start()
        self._execute(self._scrub.press(float(ratio), self._now()))

    @Slot(float)
    def scrubMove(self, ratio: float) -> None:
        if self._scrub is not None:
            self._execute(self._scrub.move(float(ratio), self._now()))

    @Slot(float)
    def scrubRelease(self, ratio: float) -> None:
        if self._scrub is None:
            return
        session, self._scrub = self._scrub, None
        self._scrub_timer.stop()
        self._execute(session.release(float(ratio), self._now()))
        self.scrubbingChanged.emit()

    def _now(self) -> float:
        return float(self._clock.nsecsElapsed()) / 1_000_000.0

    @Slot()
    def _scrub_tick(self) -> None:
        if self._scrub is not None:
            self._execute(self._scrub.tick(self._now()))

    def _execute(self, commands: list[ScrubCommand]) -> None:
        for command in commands:
            if isinstance(command, Seek):
                duration = self._service.state.duration_us or 0
                target = round(command.ratio * duration)
                # A seek to the very end would finish the track while the button is down.
                self._service.seek(min(target, max(0, duration - _SEEK_END_GUARD_US)))
            elif isinstance(command, Silence):
                self._service.set_transient_silence(command.on)
            elif isinstance(command, EnsurePlaying):
                self._ensure_playing()
            elif isinstance(command, Next):
                self._service.next()

    def _ensure_playing(self) -> None:
        state = self._service.state
        if state.status is PlaybackStatus.PAUSED or (
            state.status is PlaybackStatus.LOADING and self._service.pause_pending
        ):
            self._service.resume()

    def queue_model(self) -> PlaybackQueueModel:
        return self._queue_model

    def enqueue_tracks(
        self,
        track_ids: list[str],
        *,
        source: str = "",
        source_title: str = "",
        tracks: list[dict[str, Any]] | None = None,
    ) -> tuple[str, ...]:
        return self._service.enqueue_tracks(
            track_ids, source=source, source_title=source_title, tracks=tracks
        )

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

    @Slot(list, int, str, str, list)
    def playQueueWithRows(
        self,
        track_ids: list,
        start_index: int,
        source: str,
        source_title: str,
        tracks: list,
    ) -> None:
        self._service.play_queue(
            [str(track_id) for track_id in track_ids],
            int(start_index),
            source=source,
            source_title=source_title,
            tracks=[dict(track) for track in tracks if isinstance(track, dict)],
        )

    @Slot(int)
    def playIndex(self, index: int) -> None:
        self._service.play_index(int(index))

    @Slot(str, result=bool)
    def playEntry(self, entry_id: str) -> bool:
        return self._service.play_entry(entry_id)

    @Slot(result=int)
    def clearHistory(self) -> int:
        """Empty the History panel (Settings > Data & privacy); the queue is kept."""
        return self._service.clear_history()

    @Slot(str, result=bool)
    def playHistoryEntry(self, history_id: str) -> bool:
        return self._service.play_history_entry(history_id)

    @Slot(str)
    def enqueueHistoryEntry(self, history_id: str) -> None:
        self._service.enqueue_history_entry(history_id)

    @Slot(str, result=bool)
    def removeQueueEntry(self, entry_id: str) -> bool:
        return self._service.remove_queue_entry(entry_id)

    @Slot(str, str, result=bool)
    def moveQueueEntry(self, entry_id: str, before_entry_id: str) -> bool:
        return self._service.move_queue_entry(entry_id, before_entry_id or None)

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
        if self._waveform is not None:
            self._waveform.retry()
        else:
            self._service.retry()

    @Slot(str, result=bool)
    def stopAndRelease(self, track_id: str = "") -> bool:
        return self._service.stop_and_release(track_id)

    @Slot(str)
    def refreshTrack(self, track_id: str) -> None:
        self._service.refresh_track(track_id)

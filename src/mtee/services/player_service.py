"""Single playback queue and native-player lifetime for every presentation."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from mtee.domain.playback import PlaybackState, PlaybackStatus
from mtee.domain.playback_history import HistoryEntry, PlaybackHistory
from mtee.domain.playback_queue import QueueEntry, QueueState
from mtee.domain.tracks import TrackId
from mtee.persistence.playback_repository import PlaybackRepository, PlaybackSession
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.file_access import FileAccessCoordinator, FileAccessTimeoutError
from mtee.services.player_backend import BackendEvent, PlayerBackend

__all__ = ["PlayerService"]

TrackResolver = Callable[[str], dict[str, Any]]
_LOGGER = logging.getLogger(__name__)
_VOLUME_KEY = "player.volume"
_MUTED_KEY = "player.muted"
# Slider drags write once, after the last move.
_SETTINGS_SAVE_DELAY_MS = 500


class _BackendEventBridge(QObject):
    eventReceived = Signal(object)


class PlayerService(QObject):
    """Own the immutable queue, file read lease and state transitions."""

    stateChanged = Signal()
    positionChanged = Signal()
    queueChanged = Signal()
    trackAccessReleased = Signal(str)
    sessionSaveFailed = Signal(str)

    def __init__(
        self,
        resolver: TrackResolver,
        file_access: FileAccessCoordinator,
        backend: PlayerBackend | None,
        *,
        backend_error: str = "",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolver = resolver
        self._file_access = file_access
        self._backend = backend
        self._backend_error = backend_error
        self._state = PlaybackState()
        self._queue = QueueState()
        self._track_rows: dict[str, dict[str, Any]] = {}
        self._read_contexts: dict[int, AbstractContextManager] = {}
        self._read_track_ids: dict[int, str] = {}
        self._history = PlaybackHistory()
        self._history_recorded_entry: str | None = None
        self._unmuted_volume = self._state.volume
        self._transient_silence = False
        self._pending_seek_us: int | None = None
        self._pending_seek_started = 0.0
        self._pause_requested_session_id: int | None = None
        self._expected_pause_state: bool | None = None
        self._closed = False
        self._session_repository: PlaybackRepository | None = None
        self._save_executor: ThreadPoolExecutor | None = None
        self._save_futures: list[Future[bool]] = []
        self._save_sequence = 0
        self._last_checkpoint = time.monotonic()
        self._restore_seek: tuple[int, int] | None = None
        self._settings_repository: SettingsRepository | None = None
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(_SETTINGS_SAVE_DELAY_MS)
        self._settings_timer.timeout.connect(self._save_settings)
        self.sessionSaveFailed.connect(self._on_session_save_failed)
        self._bridge = _BackendEventBridge(self)
        self._bridge.eventReceived.connect(
            self._handle_backend_event, Qt.ConnectionType.QueuedConnection
        )
        if backend is not None:
            backend.set_event_handler(self._bridge.eventReceived.emit)
        self._position_timer = QTimer(self)
        self._position_timer.setInterval(100)
        self._position_timer.timeout.connect(self._poll_position)

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def queue_state(self) -> QueueState:
        return self._queue

    def attach_session(
        self, repository: PlaybackRepository, session: PlaybackSession | None
    ) -> None:
        """Begin ordered saves and restore the optional last session in pause."""
        if self._session_repository is not None:
            raise RuntimeError("A playback repository is already attached")
        self._session_repository = repository
        self._save_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mtee-playback")
        if session is None:
            return
        self._save_sequence = session.write_sequence
        self._queue = session.queue
        self._history = PlaybackHistory(session.history)
        for item in session.history:
            if item.snapshot and item.track_id not in self._track_rows:
                self._track_rows[item.track_id] = dict(item.snapshot)
        for entry in (
            *session.queue.past,
            *((session.queue.current,) if session.queue.current else ()),
            *session.queue.upcoming,
        ):
            if entry.snapshot and entry.track_id not in self._track_rows:
                self._track_rows[entry.track_id] = dict(entry.snapshot)
        self._sync_queue_projection()
        if self._queue.current is not None:
            self._open_queue_current(initially_paused=True, restore_position_us=session.position_us)

    def attach_settings(self, repository: SettingsRepository) -> None:
        """Restore the saved volume and mute without starting playback."""
        if self._settings_repository is not None:
            raise RuntimeError("A settings repository is already attached")
        self._settings_repository = repository
        stored_volume = repository.get_json(_VOLUME_KEY)
        stored_muted = repository.get_json(_MUTED_KEY)
        # bool is an int subclass, so the exact type is checked.
        volume = self._state.volume
        if type(stored_volume) is int and 0 <= stored_volume <= 100:
            volume = stored_volume
        muted = stored_muted if type(stored_muted) is bool else self._state.muted
        if volume:
            self._unmuted_volume = volume
        self._publish(volume=volume, muted=muted)
        if self._backend is not None:
            try:
                self._backend.set_volume(0 if muted else volume)
            except Exception as error:
                _LOGGER.warning("Could not apply the saved volume: %s", error)

    def _schedule_settings_save(self) -> None:
        if self._settings_repository is None or self._closed:
            return
        self._settings_timer.start()

    @Slot()
    def _save_settings(self) -> None:
        """Write the volume and mute now. A failure is logged, never raised to the UI."""
        self._settings_timer.stop()
        repository = self._settings_repository
        if repository is None:
            return
        try:
            repository.set_json(_VOLUME_KEY, self._state.volume)
            repository.set_json(_MUTED_KEY, self._state.muted)
        except Exception:
            _LOGGER.exception("Could not save the player volume and mute")

    def _schedule_session_save(self) -> None:
        if self._session_repository is None or self._save_executor is None or self._closed:
            return
        self._save_sequence += 1
        snapshot = PlaybackSession(
            self._queue,
            max(0, self._state.position_us),
            self._save_sequence,
            self._history.entries,
        )
        future = self._save_executor.submit(self._session_repository.save, snapshot)
        self._save_futures.append(future)
        future.add_done_callback(self._report_save_result)

    def _report_save_result(self, future: Future[bool]) -> None:
        error = future.exception()
        if error is not None:
            self.sessionSaveFailed.emit(str(error))

    @Slot(str)
    def _on_session_save_failed(self, message: str) -> None:
        self._publish(error_message=f"Could not save playback session: {message}")

    def flush_session(self) -> None:
        """Persist the effective final position before native player teardown."""
        self._save_settings()
        if self._session_repository is None or self._save_executor is None:
            return
        if self._state.current_id and self._backend is not None:
            with suppress(Exception):
                position = self._backend.position_us()
                if position is not None:
                    self._publish(position_us=max(0, int(position)))
        self._schedule_session_save()
        futures = self._save_futures
        self._save_futures = []
        for future in futures:
            future.result()

    @property
    def current_track(self) -> dict[str, Any]:
        return dict(self._track_rows.get(self._state.current_id, {}))

    @property
    def pause_pending(self) -> bool:
        """Whether the current loading session should start in a paused state."""
        return self._pause_requested_session_id == self._state.session_id

    def refresh_track(self, track_id: str) -> None:
        """Refresh queue labels after a verified source metadata edit."""
        if track_id not in self._track_rows:
            return
        with suppress(Exception):
            row = self._resolver(track_id)
            if row:
                self._track_rows[track_id] = dict(row)
        self.queueChanged.emit()
        if track_id == self._state.current_id:
            self.stateChanged.emit()

    def queue_rows(self) -> list[dict[str, Any]]:
        rows = []
        entries = (
            *self._queue.past,
            *((self._queue.current,) if self._queue.current else ()),
            *self._queue.upcoming,
        )
        for index, entry in enumerate(entries):
            track_id = entry.track_id
            track = dict(self._track_rows.get(track_id, {}))
            rows.append(
                {
                    **track,
                    "id": track_id,
                    "trackId": track_id,
                    "entryId": entry.entry_id,
                    "origin": entry.origin,
                    "source": entry.source,
                    "sourceTitle": entry.source_title,
                    "revision": self._queue.revision,
                    "current": self._queue.current is entry,
                    "available": _available(track),
                    "index": index,
                }
            )
        return rows

    def up_next(self) -> list[dict[str, Any]]:
        start = len(self._queue.past) + (1 if self._queue.current else 0)
        return [dict(row) for row in self.queue_rows()[start:]]

    def history_rows(self) -> list[dict[str, Any]]:
        """The listenings, most recent first, each merged with the freshest track row."""
        rows = []
        for entry in self._history.entries:
            track = {**entry.snapshot, **self._track_rows.get(entry.track_id, {})}
            rows.append(
                {
                    **track,
                    "id": entry.track_id,
                    "trackId": entry.track_id,
                    "historyId": entry.history_id,
                    "playedAt": entry.played_at_utc,
                    "source": entry.source,
                    "sourceTitle": entry.source_title,
                    "available": _available(track),
                }
            )
        return rows

    def play_history_entry(self, history_id: str) -> bool:
        """Play a past listening now as a new occurrence, leaving the queue as it is."""
        entry = self._history.find(history_id)
        if entry is None:
            return False
        track = {**entry.snapshot, **self._track_rows.get(entry.track_id, {})}
        if not _available(track):
            return False
        self._track_rows[entry.track_id] = dict(track)
        occurrence = QueueEntry.create(
            entry.track_id,
            "manual",
            source=entry.source,
            source_title=entry.source_title,
            snapshot=track,
        )
        self._queue = self._queue.insert_current(occurrence)
        self._open_queue_current()
        return True

    def enqueue_history_entry(self, history_id: str) -> tuple[str, ...]:
        """Append a past listening to the manual part of the queue."""
        entry = self._history.find(history_id)
        if entry is None:
            return ()
        track = {**entry.snapshot, **self._track_rows.get(entry.track_id, {})}
        return self.enqueue_tracks(
            [entry.track_id],
            source=entry.source,
            source_title=entry.source_title,
            tracks=[{**track, "id": entry.track_id}],
        )

    def _record_history(self) -> None:
        """Remember the track being left, once per occurrence."""
        track_id = self._state.current_id
        entry_id = self._state.current_entry_id
        if not track_id or entry_id == self._history_recorded_entry:
            return
        self._history_recorded_entry = entry_id
        self._history = self._history.record(
            HistoryEntry(
                history_id=str(uuid4()),
                track_id=track_id,
                snapshot=dict(self._track_rows.get(track_id, {})),
                source=self._state.source,
                source_title=self._state.source_title,
                played_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )

    def play_queue(
        self,
        track_ids: list[str] | tuple[str, ...],
        start_index: int = 0,
        *,
        source: str = "",
        source_title: str = "",
        tracks: list[dict[str, Any]] | None = None,
    ) -> None:
        """Copy the visible order now; later view changes cannot mutate this queue."""
        ids = tuple(str(track_id) for track_id in track_ids)
        if not ids or not 0 <= start_index < len(ids):
            return
        if tracks is not None:
            for track in tracks:
                track_id = str(track.get("id", ""))
                if track_id in ids:
                    self._track_rows[track_id] = dict(track)
        for track_id in ids:
            if track_id not in self._track_rows:
                with suppress(Exception):
                    row = self._resolver(track_id)
                    if row:
                        self._track_rows[track_id] = dict(row)
        entries = [
            QueueEntry.create(
                track_id,
                "context",
                source=source,
                source_title=source_title,
                snapshot=self._track_rows.get(track_id),
            )
            for track_id in ids
        ]
        self._queue = self._queue.start_context(
            entries, start_index, source=source, source_title=source_title
        )
        self._open_queue_current()
        self._trim_track_rows()

    def enqueue_tracks(
        self,
        track_ids: list[str] | tuple[str, ...],
        *,
        source: str = "",
        source_title: str = "",
        tracks: list[dict[str, Any]] | None = None,
    ) -> tuple[str, ...]:
        rows = {str(row.get("id", "")): dict(row) for row in tracks or []}
        entries = []
        for track_id in track_ids:
            identity = str(track_id)
            snapshot = rows.get(identity) or self._track_rows.get(identity)
            if snapshot is None:
                with suppress(Exception):
                    snapshot = self._resolver(identity)
            if snapshot:
                self._track_rows[identity] = dict(snapshot)
            entries.append(
                QueueEntry.create(
                    identity,
                    "manual",
                    source=source,
                    source_title=source_title,
                    snapshot=dict(snapshot) if snapshot else None,
                )
            )
        if entries:
            self._queue = self._queue.enqueue(entries)
            self._sync_queue_projection()
            self._schedule_session_save()
        return tuple(entry.entry_id for entry in entries)

    def remove_queue_entry(self, entry_id: str) -> bool:
        changed = self._queue.remove(entry_id)
        if changed is self._queue:
            return False
        self._queue = changed
        self._sync_queue_projection()
        self._schedule_session_save()
        return True

    def move_queue_entry(self, entry_id: str, before_entry_id: str | None) -> bool:
        changed = self._queue.move(entry_id, before_entry_id)
        if changed is self._queue:
            return False
        self._queue = changed
        self._sync_queue_projection()
        self._schedule_session_save()
        return True

    def play_entry(self, entry_id: str) -> bool:
        changed = self._queue.play_entry(entry_id)
        if changed is self._queue:
            return False
        self._queue = changed
        self._open_queue_current()
        return True

    def _queue_track_ids(self) -> tuple[str, ...]:
        entries = (
            *self._queue.past,
            *((self._queue.current,) if self._queue.current else ()),
            *self._queue.upcoming,
        )
        return tuple(entry.track_id for entry in entries)

    def _sync_queue_projection(self) -> None:
        self._publish(
            track_ids=self._queue_track_ids(),
            current_index=len(self._queue.past) if self._queue.current else -1,
            shuffle=self._queue.shuffle,
            repeat=self._queue.repeat,
        )
        self.queueChanged.emit()

    def _open_queue_current(
        self, *, initially_paused: bool = False, restore_position_us: int = 0
    ) -> None:
        if self._queue.current is None:
            return
        self._open_index(
            len(self._queue.past),
            track_ids=self._queue_track_ids(),
            source=self._queue.current.source or self._queue.source,
            source_title=self._queue.current.source_title or self._queue.source_title,
            initially_paused=initially_paused,
            restore_position_us=restore_position_us,
        )

    @Slot()
    def toggle_play(self) -> None:
        if self._state.status is PlaybackStatus.PLAYING:
            self.pause()
        elif self._state.status is PlaybackStatus.PAUSED:
            self.resume()
        elif self._state.status is PlaybackStatus.LOADING:
            if self.pause_pending:
                self.resume()
            else:
                self.pause()
        elif self._state.status in (PlaybackStatus.ERROR, PlaybackStatus.ENDED):
            self.retry()
        elif self._queue.current is None and self._queue.upcoming:
            self._queue = self._queue.next()
            self._open_queue_current()

    @Slot()
    def pause(self) -> None:
        if self._state.status is PlaybackStatus.LOADING and self._state.current_id:
            if not self.pause_pending:
                self._pause_requested_session_id = self._state.session_id
                self._expected_pause_state = True
                try:
                    if self._backend is not None:
                        self._backend.set_paused(True)
                except Exception as error:
                    self._fail(str(error))
                    return
                self.stateChanged.emit()
            return
        if self._backend is None or self._state.status is not PlaybackStatus.PLAYING:
            return
        try:
            self._expected_pause_state = True
            self._backend.set_paused(True)
            self._publish(status=PlaybackStatus.PAUSED)
            self._poll_position()
            self._schedule_session_save()
        except Exception as error:
            self._fail(str(error))

    @Slot()
    def resume(self) -> None:
        if self._state.status is PlaybackStatus.LOADING:
            if self.pause_pending:
                self._pause_requested_session_id = None
                self._expected_pause_state = False
                self.stateChanged.emit()
            return
        if self._backend is None or self._state.status is not PlaybackStatus.PAUSED:
            return
        try:
            self._expected_pause_state = False
            self._backend.set_paused(False)
            self._publish(status=PlaybackStatus.PLAYING)
            self._schedule_session_save()
        except Exception as error:
            self._fail(str(error))

    @Slot()
    def next(self) -> None:
        if self._queue.current is None and not self._queue.upcoming:
            return
        if self._queue.repeat == "one" and self._queue.current is not None:
            # Repeat one: Next restarts the same track, like a natural end.
            self._open_index(self._state.current_index)
        elif self._queue.upcoming:
            self._queue = self._queue.next()
            self._open_queue_current()
        elif self._queue.repeat == "all":
            self._queue = self._queue.repeat_all()
            self._open_queue_current()
        else:
            self._finish(stop_backend=True)

    @Slot(int)
    def play_index(self, index: int) -> None:
        """Play an existing row without capturing or rebuilding the queue."""
        target = int(index)
        current_index = len(self._queue.past)
        if target == current_index and self._queue.current:
            self._open_queue_current()
        elif target > current_index:
            offset = target - current_index - (1 if self._queue.current else 0)
            if 0 <= offset < len(self._queue.upcoming):
                self.play_entry(self._queue.upcoming[offset].entry_id)
        elif 0 <= target < current_index:
            while len(self._queue.past) > target:
                self._queue = self._queue.previous()
            self._open_queue_current()

    @Slot()
    def previous(self) -> None:
        if self._queue.current is None:
            return
        position = self._effective_previous_position()
        if position >= 3_000_000:
            self._restart_current()
        elif self._queue.past:
            self._queue = self._queue.previous()
            self._open_queue_current()
        elif self._queue.repeat == "all" and self._queue.context_order:
            self._queue = self._queue.previous_wrap()
            self._open_queue_current()
        else:
            self._restart_current()

    def _effective_previous_position(self) -> int:
        if self._pending_seek_us is not None:
            return self._pending_seek_us
        if self._backend is not None:
            with suppress(Exception):
                position = self._backend.position_us()
                if position is not None:
                    return max(0, int(position))
        return self._state.position_us

    def _restart_current(self) -> None:
        self.seek(0)
        if self._state.status is PlaybackStatus.PAUSED:
            self.resume()

    @Slot(int)
    def seek(self, position_us: int) -> None:
        if (
            self._backend is None
            or not self._state.current_id
            or not self._state.seekable
            or self._state.duration_us is None
        ):
            return
        target = max(0, min(int(position_us), self._state.duration_us))
        try:
            self._backend.seek(target)
            self._pending_seek_us = target
            self._pending_seek_started = time.monotonic()
            self._publish(position_us=target, seeking=True)
        except Exception as error:
            self._fail(str(error))

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        value = max(0, min(100, int(volume)))
        muted = self._state.muted
        try:
            if self._backend is not None:
                self._backend.set_volume(0 if muted or self._transient_silence else value)
            if value:
                self._unmuted_volume = value
            self._publish(volume=value)
            self._schedule_settings_save()
        except Exception as error:
            self._fail(str(error))

    @Slot()
    def toggle_mute(self) -> None:
        muted = not self._state.muted
        try:
            if self._backend is not None:
                self._backend.set_volume(
                    0 if muted or self._transient_silence else self._state.volume
                )
            if not muted:
                self._unmuted_volume = max(1, self._state.volume)
            self._publish(muted=muted)
            self._schedule_settings_save()
        except Exception as error:
            self._fail(str(error))

    def set_transient_silence(self, silent: bool) -> None:
        """Cut the sound, or restore it, without changing the volume the user chose.

        Used while scrubbing fast. It publishes neither ``muted`` nor ``volume``, so no
        control moves, and it follows the user's mute: restoring never unmutes. Loading a
        track, an error, the end of a track and closing all lift it.
        """
        if self._backend is None or self._closed or silent == self._transient_silence:
            return
        self._transient_silence = silent
        try:
            self._backend.set_volume(0 if silent or self._state.muted else self._state.volume)
        except Exception as error:
            self._transient_silence = False
            self._fail(str(error))

    @Slot()
    def toggle_shuffle(self) -> None:
        self._queue = self._queue.set_shuffle(not self._queue.shuffle)
        self._sync_queue_projection()
        self._schedule_session_save()

    @Slot()
    def cycle_repeat(self) -> None:
        value = cast(
            Literal["off", "one", "all"],
            {"off": "all", "all": "one", "one": "off"}[self._state.repeat],
        )
        self._queue = self._queue.set_repeat(value)
        self._sync_queue_projection()
        self._schedule_session_save()

    @Slot()
    def retry(self) -> None:
        if self._state.current_index >= 0:
            self._open_index(self._state.current_index)

    @Slot(str)
    def stop_and_release(self, track_id: str = "") -> bool:
        """Stop the currently played UUID and explicitly release its read lease."""
        if not self._state.current_id or (track_id and track_id != self._state.current_id):
            return False
        next_session = self._state.session_id + 1
        self._pause_requested_session_id = None
        self._expected_pause_state = None
        self._publish(
            status=PlaybackStatus.IDLE,
            session_id=next_session,
            current_id="",
            current_entry_id="",
            current_index=-1,
            position_us=0,
            duration_us=None,
            seekable=False,
            error_message="",
            seeking=False,
        )
        self._position_timer.stop()
        if self._backend is not None:
            try:
                self._backend.stop()
            except Exception as error:
                self._publish(status=PlaybackStatus.ERROR, error_message=str(error))
        else:
            self._release_read_lease(self._state.session_id - 1)
        return True

    def close(self) -> None:
        if self._closed:
            return
        flush_error: Exception | None = None
        try:
            self.flush_session()
        except Exception as error:
            flush_error = error
        self._closed = True
        self._transient_silence = False
        if self._save_executor is not None:
            self._save_executor.shutdown(wait=True)
        self._position_timer.stop()
        self.stop_and_release()
        if self._backend is not None:
            self._backend.set_event_handler(None)
            self._backend.close()
        # A successful backend close is the confirmation that native file handles
        # are gone. On failure, retain every lease rather than report a false release.
        self._release_read_lease()
        if flush_error is not None:
            raise flush_error

    def _open_index(
        self,
        index: int,
        *,
        track_ids: tuple[str, ...] | None = None,
        source: str | None = None,
        source_title: str | None = None,
        initially_paused: bool = False,
        restore_position_us: int = 0,
    ) -> None:
        ids = track_ids or self._state.track_ids
        if not 0 <= index < len(ids):
            return
        self._pause_requested_session_id = None
        self._expected_pause_state = initially_paused
        self._restore_seek = None
        track_id = ids[index]
        previous_id = self._state.current_id
        next_entry_id = self._queue.current.entry_id if self._queue.current else ""
        if previous_id and self._state.current_entry_id != next_entry_id:
            self._record_history()
        session_id = self._state.session_id + 1
        if initially_paused:
            self._pause_requested_session_id = session_id
            self._restore_seek = (session_id, max(0, restore_position_us))
        _LOGGER.debug("Playback request session=%s track=%s", session_id, track_id)
        current_source = self._state.source if source is None else source
        current_title = self._state.source_title if source_title is None else source_title
        self._publish(
            status=PlaybackStatus.LOADING,
            track_ids=tuple(ids),
            current_id=track_id,
            current_entry_id=next_entry_id,
            current_index=index,
            position_us=0,
            duration_us=_duration_us(self._track_rows.get(track_id, {})),
            seekable=False,
            error_message="",
            session_id=session_id,
            source=current_source,
            source_title=current_title,
            codec="",
            sample_rate=None,
            channels="",
            seeking=False,
            history=tuple(entry.track_id for entry in self._history.entries),
        )
        self.queueChanged.emit()
        self._pending_seek_us = None
        if not initially_paused:
            self._schedule_session_save()
        if self._backend is not None and previous_id:
            try:
                self._backend.stop()
            except Exception as error:
                self._fail(str(error))
                return
        self._position_timer.start()
        if self._backend is None:
            self._fail(self._backend_error or "The audio runtime is unavailable.")
            return
        try:
            # Resolve again at load time so a moved or replaced file does not rely
            # on a path captured when the queue was created.
            track = self._resolver(track_id)
            self._track_rows[track_id] = dict(track)
            path = Path(str(track.get("path", "")))
            if not path.is_file():
                raise FileNotFoundError(f"The audio file is unavailable: {path}")
            context = self._file_access.acquire_read(
                TrackId.parse(track_id), "playback", timeout_seconds=0
            )
            context.__enter__()
            self._read_contexts[session_id] = context
            self._read_track_ids[session_id] = track_id
            self._transient_silence = False
            self._backend.set_volume(0 if self._state.muted else self._state.volume)
            # An explicit activation means "play this track". Reset the native
            # pause property here, once, before load so a previous track's pause
            # cannot leak into the new session.
            self._backend.set_paused(initially_paused)
            self._backend.load(path, session_id)
            _LOGGER.debug("Playback load command sent session=%s track=%s", session_id, track_id)
        except (FileAccessTimeoutError, OSError, KeyError, ValueError) as error:
            self._release_read_lease(session_id)
            self._fail(str(error))
        except Exception as error:
            self._release_read_lease(session_id)
            self._fail(str(error))

    def _handle_backend_event(self, event: object) -> None:
        if not isinstance(event, BackendEvent):
            return
        _LOGGER.debug(
            "Playback native event session=%s current_session=%s event=%s",
            event.session_id,
            self._state.session_id,
            event.name,
        )
        if event.name == "stopped":
            _LOGGER.debug("Playback stop confirmed session=%s", event.session_id)
            self._release_read_lease(event.session_id)
            if event.session_id == self._state.session_id:
                self._position_timer.stop()
            return
        if event.name == "error":
            self._release_read_lease(event.session_id)
            if event.session_id == self._state.session_id:
                self._fail(
                    str(event.value or "The audio file could not be played."),
                    source_closed=True,
                )
            return
        if event.session_id != self._state.session_id:
            return
        if event.name == "start-file":
            return
        if event.name == "loaded":
            for previous_session in tuple(self._read_contexts):
                if previous_session != event.session_id:
                    self._release_read_lease(previous_session)
            pause_when_loaded = self.pause_pending
            self._pause_requested_session_id = None
            self._publish(
                status=(PlaybackStatus.PAUSED if pause_when_loaded else PlaybackStatus.PLAYING),
                error_message="",
            )
            self._position_timer.start()
            self._apply_restore_seek()
        elif event.name == "eof":
            self._release_read_lease(event.session_id)
            self._on_eof()
        elif event.name == "pause":
            if self._state.status in (PlaybackStatus.PLAYING, PlaybackStatus.PAUSED):
                paused = bool(event.value)
                if self._expected_pause_state is not None and paused != self._expected_pause_state:
                    _LOGGER.debug(
                        "Ignoring stale pause notification session=%s paused=%s expected=%s",
                        event.session_id,
                        paused,
                        self._expected_pause_state,
                    )
                    return
                status = PlaybackStatus.PAUSED if paused else PlaybackStatus.PLAYING
                self._publish(status=status)
        elif event.name == "duration":
            value = event.value if isinstance(event.value, int) else None
            self._publish(duration_us=max(0, value) if value is not None else None)
            self._apply_restore_seek()
        elif event.name == "seekable":
            self._publish(seekable=bool(event.value))
            self._apply_restore_seek()
        elif event.name == "codec":
            self._publish(codec=str(event.value or ""))
        elif event.name == "sample-rate":
            value = event.value if isinstance(event.value, int) else 0
            self._publish(sample_rate=value if value > 0 else None)
        elif event.name == "channels":
            self._publish(channels=str(event.value or ""))

    def _poll_position(self) -> None:
        if self._backend is None or not self._state.current_id:
            return
        if self._state.status not in (PlaybackStatus.PLAYING, PlaybackStatus.PAUSED):
            return
        try:
            position = self._backend.position_us()
        except Exception as error:
            self._fail(str(error))
            return
        if position is None:
            return
        if self._state.duration_us is not None:
            position = min(position, self._state.duration_us)
        seeking = self._state.seeking
        if self._pending_seek_us is not None:
            if abs(position - self._pending_seek_us) <= 300_000:
                self._pending_seek_us = None
                seeking = False
            elif time.monotonic() - self._pending_seek_started < 2:
                return
            else:
                self._pending_seek_us = None
                seeking = False
        self._publish(position_us=max(0, position), seeking=seeking)
        if (
            self._state.status is PlaybackStatus.PLAYING
            and time.monotonic() - self._last_checkpoint >= 5
        ):
            self._last_checkpoint = time.monotonic()
            self._schedule_session_save()

    def _apply_restore_seek(self) -> None:
        pending = self._restore_seek
        if pending is None or pending[0] != self._state.session_id:
            return
        if self._state.status is not PlaybackStatus.PAUSED or not self._state.seekable:
            return
        duration = self._state.duration_us
        if duration is None or self._backend is None:
            return
        target = min(pending[1], duration)
        try:
            self._backend.seek(target)
            self._pending_seek_us = target
            self._pending_seek_started = time.monotonic()
            self._restore_seek = None
            self._publish(position_us=target, seeking=True)
        except Exception as error:
            self._fail(str(error))

    def _on_eof(self) -> None:
        if self._queue.repeat == "one":
            self._open_index(self._state.current_index)
        elif self._queue.upcoming:
            self._queue = self._queue.next()
            self._open_queue_current()
        elif self._queue.repeat == "all":
            self._queue = self._queue.repeat_all()
            self._open_queue_current()
        else:
            self._finish()

    def _finish(self, *, stop_backend: bool = False) -> None:
        self._record_history()
        self._transient_silence = False
        self._position_timer.stop()
        self._publish(
            status=PlaybackStatus.ENDED,
            position_us=self._state.duration_us or self._state.position_us,
            seekable=False,
            seeking=False,
        )
        if stop_backend and self._backend is not None:
            try:
                self._backend.stop()
            except Exception as error:
                self._publish(status=PlaybackStatus.ERROR, error_message=str(error))
        else:
            self._release_read_lease(self._state.session_id)
        self.queueChanged.emit()
        self._schedule_session_save()
        self._trim_track_rows()

    def _fail(self, message: str, *, source_closed: bool = False) -> None:
        self._transient_silence = False
        self._position_timer.stop()
        self._pending_seek_us = None
        self._restore_seek = None
        self._pause_requested_session_id = None
        self._expected_pause_state = None
        self._publish(
            status=PlaybackStatus.ERROR,
            error_message=message,
            seekable=False,
            seeking=False,
        )
        if source_closed:
            self._release_read_lease(self._state.session_id)
        elif self._backend is not None:
            with suppress(Exception):
                self._backend.stop()
        else:
            self._release_read_lease(self._state.session_id)

    def _publish(self, **changes: Any) -> None:
        previous = self._state
        self._state = replace(previous, **changes)
        if (
            previous.position_us != self._state.position_us
            or previous.seeking != self._state.seeking
        ):
            self.positionChanged.emit()
        if any(key not in {"position_us", "seeking"} for key in changes):
            self.stateChanged.emit()

    def _trim_track_rows(self) -> None:
        retained = set(self._state.track_ids) | {e.track_id for e in self._history.entries}
        if self._state.current_id:
            retained.add(self._state.current_id)
        self._track_rows = {
            track_id: row for track_id, row in self._track_rows.items() if track_id in retained
        }

    def _release_read_lease(self, session_id: int | None = None) -> None:
        if session_id is None:
            sessions = tuple(self._read_contexts)
            contexts = tuple(self._read_contexts.values())
            self._read_contexts.clear()
            released = tuple((key, self._read_track_ids.pop(key, "")) for key in sessions)
        else:
            context = self._read_contexts.pop(session_id, None)
            contexts = (context,) if context is not None else ()
            track_id = self._read_track_ids.pop(session_id, "")
            released = ((session_id, track_id),) if context is not None else ()
        for context in contexts:
            if context is not None:
                context.__exit__(None, None, None)
        for released_session, track_id in released:
            if track_id:
                _LOGGER.debug(
                    "Playback read lease released session=%s track=%s",
                    released_session,
                    track_id,
                )
                self.trackAccessReleased.emit(track_id)


def _available(track: dict[str, Any]) -> bool:
    return str(track.get("status", "")) == "readable"


def _duration_us(track: dict[str, Any]) -> int | None:
    value = track.get("durationUs")
    if isinstance(value, int) and value > 0:
        return value
    seconds = track.get("seconds")
    return (
        max(0, int(seconds) * 1_000_000)
        if isinstance(seconds, (int, float)) and seconds > 0
        else None
    )

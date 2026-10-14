"""Qt model of the listening statistics shown on the Profile page (plan 115).

The queries run as a background job, never on the GUI thread. Each request carries a
generation number; a result that belongs to an older period or refresh is dropped.
The period is a calendar period in local time (see ``mtee.domain.listening_periods``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from mtee.domain.listening_periods import PERIOD_KINDS, calendar_period, listening_buckets
from mtee.domain.play_log import ListeningPeriod
from mtee.persistence.play_log_repository import ListeningTotals, PlayLogRepository
from mtee.services.jobs import JobContext, JobService

__all__ = [
    "PERIOD_LABELS",
    "StatisticsModel",
    "StatisticsSnapshot",
    "read_statistics",
]

TOP_LIMIT = 10
DEFAULT_PERIOD = "month"
PERIOD_LABELS = {
    "week": "This week",
    "month": "This month",
    "year": "This year",
    "all": "All time",
}


@dataclass(frozen=True, slots=True)
class StatisticsSnapshot:
    """Everything the Profile page shows for one period, computed in one pass."""

    kind: str
    totals: ListeningTotals
    top_tracks: list[dict[str, Any]]
    top_albums: list[dict[str, Any]]
    top_artists: list[dict[str, Any]]
    series: list[dict[str, Any]]


def top_artists(period: ListeningPeriod) -> list[dict[str, Any]]:
    """TODO(step 112): rank artists once the artist splitting rules are merged.

    Until then the Profile page shows no top artists. The splitting rules belong to the
    artist index of step 112; the statistics do not reimplement them. The period is kept
    in the signature so the ranking has the same input as the other rankings.
    """
    del period
    return []


def read_statistics(play_log: PlayLogRepository, kind: str, now: datetime) -> StatisticsSnapshot:
    """Read every figure of the period ``kind`` ending at ``now``. Runs in a worker."""
    if kind not in PERIOD_KINDS:
        raise ValueError(f"unknown statistics period: {kind!r}")
    period = calendar_period(kind, now)
    daily = play_log.daily_listening(period)
    buckets = listening_buckets(
        kind, now, [(row.day, row.listening_ms, row.counted_plays) for row in daily]
    )
    return StatisticsSnapshot(
        kind=kind,
        totals=play_log.totals(period),
        top_tracks=[
            {
                "trackId": rank.track_id,
                "title": rank.title,
                "artist": rank.artist,
                "album": rank.album,
                "path": rank.path,
                "countedPlays": rank.counted_plays,
                "listeningMs": rank.listening_ms,
                "lastPlayed": rank.last_played.astimezone(UTC).isoformat(timespec="seconds"),
            }
            for rank in play_log.top_tracks(period, limit=TOP_LIMIT)
        ],
        top_albums=[
            {
                "album": rank.album,
                "countedPlays": rank.counted_plays,
                "listeningMs": rank.listening_ms,
            }
            for rank in play_log.top_albums(period, limit=TOP_LIMIT)
        ],
        top_artists=top_artists(period),
        series=[
            {
                "start": bucket.start.isoformat(),
                "granularity": bucket.granularity,
                "listeningMs": bucket.listening_ms,
                "countedPlays": bucket.counted_plays,
            }
            for bucket in buckets
        ],
    )


class StatisticsModel(QObject):
    """Expose the statistics of the selected period to QML, read off the GUI thread."""

    changed = Signal()
    _resultReady = Signal(int, object, str)

    def __init__(
        self,
        play_log: PlayLogRepository,
        jobs: JobService,
        parent: QObject | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        super().__init__(parent)
        self._play_log = play_log
        self._jobs = jobs
        self._clock = clock
        self._kind = DEFAULT_PERIOD
        self._generation = 0
        self._loading = False
        self._error = ""
        self._snapshot: StatisticsSnapshot | None = None
        self._resultReady.connect(self._receive)

    @Property(str, notify=changed)
    def period(self) -> str:
        return self._kind

    @Property(str, notify=changed)
    def periodLabel(self) -> str:
        return PERIOD_LABELS[self._kind]

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(int, notify=changed)
    def listeningMs(self) -> int:
        return self._snapshot.totals.listening_ms if self._snapshot else 0

    @Property(int, notify=changed)
    def countedPlays(self) -> int:
        return self._snapshot.totals.counted_plays if self._snapshot else 0

    @Property(int, notify=changed)
    def sessions(self) -> int:
        return self._snapshot.totals.sessions if self._snapshot else 0

    @Property(list, notify=changed)
    def topTracks(self) -> list[dict[str, Any]]:
        return self._snapshot.top_tracks if self._snapshot else []

    @Property(list, notify=changed)
    def topAlbums(self) -> list[dict[str, Any]]:
        return self._snapshot.top_albums if self._snapshot else []

    @Property(list, notify=changed)
    def topArtists(self) -> list[dict[str, Any]]:
        """Empty until step 112 provides the artist rules (see ``top_artists``)."""
        return self._snapshot.top_artists if self._snapshot else []

    @Property(list, notify=changed)
    def series(self) -> list[dict[str, Any]]:
        return self._snapshot.series if self._snapshot else []

    @Slot(str)
    def setPeriod(self, kind: str) -> None:
        if kind not in PERIOD_KINDS or kind == self._kind:
            return
        self._kind = kind
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        self._generation += 1
        generation = self._generation
        kind = self._kind
        now = self._clock()
        self._loading = True
        self.changed.emit()

        def task(context: JobContext) -> None:
            del context
            try:
                snapshot = read_statistics(self._play_log, kind, now)
            except Exception as error:
                self._resultReady.emit(generation, None, str(error))
                raise
            self._resultReady.emit(generation, snapshot, "")

        self._jobs.submit(task, label="Read listening statistics", visible=False)

    @Slot(int, object, str)
    def _receive(self, generation: int, snapshot: object, error: str) -> None:
        if generation != self._generation:
            return
        self._loading = False
        self._error = error
        if isinstance(snapshot, StatisticsSnapshot):
            self._snapshot = snapshot
        self.changed.emit()

"""Statistics of the Profile page: queries on a temporary database and the Qt model."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.models.statistics_model import StatisticsModel, read_statistics
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
DEVICE = str(uuid4())


class InlineJobs:
    """Runs each job at once on the calling thread; the job service is tested elsewhere."""

    def __init__(self) -> None:
        self.labels: list[str] = []

    def submit(self, task, *, label: str = "", visible: bool = True, **_kwargs) -> str:
        self.labels.append(label)
        with suppress(Exception):  # a failing job reports through its own signal
            task(None)
        return "job"


@pytest.fixture
def play_log(tmp_path: Path) -> Iterator[PlayLogRepository]:
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    repository = PlayLogRepository(database)
    recent = NOW - timedelta(hours=1)
    repository.insert_events(
        [
            _event("a", recent, 35_000, True),
            _event("b", recent - timedelta(hours=1), 2_000, False),
            _event("c", NOW - timedelta(days=800), 30_000, True),
        ],
        DEVICE,
    )
    yield repository
    database.close()


def _event(track: str, started: datetime, heard_ms: int, counted: bool) -> PlayEvent:
    return PlayEvent(
        event_id=str(uuid4()),
        track=PlayedTrack(
            track_id=track,
            path=f"{track}.mp3",
            artist=f"Artist {track}",
            title=f"Title {track}",
            album="Album",
        ),
        started_at=started,
        ended_at=started + timedelta(milliseconds=heard_ms),
        heard_ms=heard_ms,
        counted=counted,
    )


def test_week_and_all_time_snapshots_count_only_their_period(play_log) -> None:
    week = read_statistics(play_log, "week", NOW)
    assert (week.totals.sessions, week.totals.listening_ms, week.totals.counted_plays) == (
        2,
        37_000,
        1,
    )
    assert [track["trackId"] for track in week.top_tracks] == ["a"]
    assert week.top_tracks[0]["countedPlays"] == 1
    assert week.top_albums == [{"album": "Album", "countedPlays": 1, "listeningMs": 37_000}]
    assert len(week.series) == 7
    assert sum(bucket["listeningMs"] for bucket in week.series) == 37_000

    everything = read_statistics(play_log, "all", NOW)
    assert everything.totals.sessions == 3
    assert everything.totals.counted_plays == 2
    assert {track["trackId"] for track in everything.top_tracks} == {"a", "c"}
    assert everything.series[0]["granularity"] == "month"


def test_top_artists_wait_for_the_artist_rules(play_log) -> None:
    # TODO(step 112): the ranking uses the splitting rules; until then it is empty.
    assert read_statistics(play_log, "all", NOW).top_artists == []


def test_an_unknown_period_is_refused(play_log) -> None:
    with pytest.raises(ValueError):
        read_statistics(play_log, "decade", NOW)


def test_model_reads_the_selected_period_through_the_job_service(qapp, play_log) -> None:
    jobs = InlineJobs()
    model = StatisticsModel(play_log, jobs, clock=lambda: NOW)
    model.refresh()
    assert jobs.labels == ["Read listening statistics"]
    assert model.period == "month"
    assert model.periodLabel == "This month"
    assert model.listeningMs == 37_000
    assert model.loading is False

    model.setPeriod("all")
    assert model.period == "all"
    assert model.periodLabel == "All time"
    assert model.sessions == 3
    assert model.topTracks and model.topArtists == []

    model.setPeriod("decade")
    assert model.period == "all"


def test_a_result_of_an_older_request_is_dropped(qapp, play_log) -> None:
    model = StatisticsModel(play_log, InlineJobs(), clock=lambda: NOW)
    model.refresh()
    stale = read_statistics(play_log, "week", NOW)
    model.setPeriod("year")
    model._receive(0, stale, "")  # a request made before the period changed
    assert model._snapshot is not None
    assert model._snapshot.kind == "year"

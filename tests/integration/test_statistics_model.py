"""Statistics of the Profile page: queries on a temporary database and the Qt model."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from mtee.domain.artist_index import CreditRules
from mtee.domain.play_log import PlayedTrack, PlayEvent
from mtee.models.statistics_model import TOP_LIMIT, StatisticsModel, read_statistics
from mtee.persistence.database import Database
from mtee.persistence.play_log_repository import PlayLogRepository

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
DEVICE = str(uuid4())


class InlineJobs:
    """Runs each job at once on the calling thread; the job service is tested elsewhere."""

    accepting = True

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


def test_top_artists_without_rules_keep_each_text_whole(play_log) -> None:
    # Without any solo name nothing is cut at "&": each play names its artist text as it is.
    ranking = read_statistics(play_log, "all", NOW).top_artists
    assert [(row["artist"], row["countedPlays"]) for row in ranking] == [
        ("Artist a", 1),
        ("Artist c", 1),
    ]


@pytest.fixture
def artist_log(tmp_path: Path) -> Iterator[PlayLogRepository]:
    database = Database(tmp_path / "artists.sqlite3")
    database.migrate()
    repository = PlayLogRepository(database)
    recent = NOW - timedelta(hours=1)
    repository.insert_events(
        [
            _artist_event("A", recent, "Chase & Status", 40_000, True),
            _artist_event("B", recent, "Chase & Status", 30_000, True),
            _artist_event("C", recent, "Camo & Krooked", 50_000, True),
            _artist_event("D", recent, "Camo & Krooked", 10_000, False),
            _artist_event("E", recent, "Status", 5_000, True),
            _artist_event("F", recent, "Solo Artist", 90_000, True),
            _artist_event("G", recent, "Ghost", 1_000_000, False),
            _artist_event("H", recent, "", 9_000, True),
        ],
        DEVICE,
    )
    yield repository
    database.close()


def _artist_event(
    track: str, started: datetime, artist: str, heard_ms: int, counted: bool
) -> PlayEvent:
    return PlayEvent(
        event_id=str(uuid4()),
        track=PlayedTrack(track_id=track, path=f"{track}.mp3", artist=artist, title=track),
        started_at=started,
        ended_at=started + timedelta(milliseconds=heard_ms),
        heard_ms=heard_ms,
        counted=counted,
    )


def _ranking(rows: list[dict]) -> list[tuple[str, int, int]]:
    return [(row["artist"], row["countedPlays"], row["listeningMs"]) for row in rows]


def test_top_artists_split_with_the_index_rules(artist_log) -> None:
    rules = CreditRules(solo=frozenset({"chase"}))
    ranking = read_statistics(artist_log, "all", NOW, rules).top_artists
    # "Chase & Status" is cut because Chase is a solo artist; "Camo & Krooked" is not.
    # Status counts for its own play and for both halves of "Chase & Status".
    assert _ranking(ranking) == [
        ("Status", 3, 75_000),
        ("Chase", 2, 70_000),
        ("Solo Artist", 1, 90_000),
        ("Camo & Krooked", 1, 60_000),
    ]
    assert [row["key"] for row in ranking[:2]] == ["status", "chase"]


def test_top_artists_honour_the_user_choices(artist_log) -> None:
    rules = CreditRules(
        solo=frozenset({"chase"}),
        one_names=("Chase & Status",),
        split_keys=frozenset({"camo & krooked"}),
    )
    ranking = read_statistics(artist_log, "all", NOW, rules).top_artists
    # "This is one artist" keeps the credit whole; "Split" cuts Camo & Krooked at "&".
    assert _ranking(ranking) == [
        ("Chase & Status", 2, 70_000),
        ("Solo Artist", 1, 90_000),
        ("Camo", 1, 60_000),
        ("Krooked", 1, 60_000),
        ("Status", 1, 5_000),
    ]


def test_top_artists_are_limited_and_skip_plays_without_a_count(artist_log) -> None:
    ranking = read_statistics(artist_log, "all", NOW, CreditRules()).top_artists
    names = [row["artist"] for row in ranking]
    assert "Ghost" not in names
    assert "" not in names
    assert len(names) <= TOP_LIMIT


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
    assert model.topTracks
    assert [row["artist"] for row in model.topArtists] == ["Artist a", "Artist c"]


def test_model_ranks_artists_with_the_rules_of_its_index(qapp, artist_log) -> None:
    rules = CreditRules(solo=frozenset({"chase"}))
    model = StatisticsModel(artist_log, InlineJobs(), clock=lambda: NOW, artist_rules=lambda: rules)
    model.setPeriod("all")
    model.refresh()
    assert model.topArtists[0]["artist"] == "Status"
    assert model.topArtists[0]["countedPlays"] == 3


def test_an_index_rebuild_recounts_only_when_the_rules_changed(qapp, artist_log) -> None:
    current = {"rules": CreditRules(solo=frozenset({"chase"}))}
    jobs = InlineJobs()
    model = StatisticsModel(
        artist_log, jobs, clock=lambda: NOW, artist_rules=lambda: current["rules"]
    )
    model.setPeriod("all")
    counted = len(jobs.labels)

    model.followArtistRules()  # a rebuild that changed no rule starts no query
    assert len(jobs.labels) == counted

    current["rules"] = CreditRules(solo=frozenset({"chase", "status"}))
    model.followArtistRules()
    assert len(jobs.labels) == counted + 1

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

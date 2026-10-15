"""Read-only sampling, provider failure/retry and human-review preservation."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest
from scripts.archive.artist_enrichment_pilot import (
    MusicBrainzClient,
    ProviderError,
    canonical_profile,
    enrich_musicbrainz,
    lucene_name,
    make_report,
    prepare,
    select_tracks,
    validate_observations,
    write_json,
)

pytestmark = pytest.mark.archive


def track(index: int, name: str = "Artist", title: str = "Title") -> dict:
    return {
        "track_id": f"track-{index:03}",
        "title": title,
        "path": f"/music/{index}.mp3",
        "credits": [{"artist_id": "artist-a", "name": name, "credit_role": "artist"}],
    }


def database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE artists(artist_id TEXT,display_name TEXT,state TEXT);
            CREATE TABLE track_artist_credits(track_id TEXT,artist_id TEXT,position INT,
                                             role TEXT,confirmed INT);
            CREATE TABLE track_artist_review(track_id TEXT,confirmed_title TEXT,review_state TEXT);
            CREATE TABLE track_locations(track_id TEXT,path TEXT,metadata_json TEXT);
            INSERT INTO artists VALUES('artist-a','Fictional Producer','established');
            INSERT INTO artists VALUES('artist-b','Draft Profile','provisional');
            INSERT INTO track_artist_credits VALUES('track-001','artist-a',0,'artist',1);
            INSERT INTO track_artist_credits VALUES('track-001','artist-b',1,'artist',0);
            INSERT INTO track_artist_review VALUES('track-001','Fictional Song','confirmed');
            INSERT INTO track_locations VALUES('track-001','/fictional/song.mp3','{"genre":[]}');
        """)


def test_prepare_is_read_only_and_uses_confirmed_profiles(tmp_path: Path) -> None:
    source = tmp_path / "input.sqlite3"
    database(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    result = prepare(source, tmp_path / "run", [], 50, 105)
    assert result["sample_tracks"] == 1
    assert result["catalog_artists"] == 1
    assert hashlib.sha256(source.read_bytes()).digest() == before
    assert not (tmp_path / "missing.sqlite3").exists()
    with pytest.raises(sqlite3.OperationalError):
        prepare(tmp_path / "missing.sqlite3", tmp_path / "missing-run", [], 50, 105)
    assert not (tmp_path / "missing.sqlite3").exists()
    with pytest.raises(ValueError, match="new output"):
        prepare(source, tmp_path / "run", [], 50, 105)


def test_sample_repeats_is_unique_and_reports_missing_categories() -> None:
    rows = [track(i) for i in range(80)]
    rows[0] = track(0, "MC One", "Vocal song")
    rows[1] = track(1, "AB", "Song (Bootleg)")
    rows[2] = track(2, "Producer", "Song (Remix)")
    selectors = [
        {"category": "MC", "artists": ["MC One"]},
        {"category": "absent", "artists": ["Not in catalog"]},
    ]
    first, coverage = select_tracks(rows, selectors, 50, 105)
    second, _ = select_tracks(list(reversed(rows)), selectors, 50, 105)
    assert first == second
    assert len({r["track_id"] for r in first}) == 50
    assert first[0]["credits"][0]["name"] == "MC One"
    assert coverage["selectors"][1]["selected"] == 0
    assert "collaboration" in coverage["missing_structural"]
    assert coverage["structural"]["short_name"] > 0


def test_special_names_are_lucene_literals_and_profiles_are_artist_pages() -> None:
    assert lucene_name('A+ & "B"') == 'artist:"A\\+ \\& \\"B\\""'
    assert canonical_profile("https://open.spotify.com/artist/1234567890123456789012?si=x")
    assert canonical_profile("https://soundcloud.com/fictional?secret_token=remove") == (
        "https://soundcloud.com/fictional"
    )
    assert canonical_profile("https://open.spotify.com/track/1234567890123456789012") is None
    assert canonical_profile("https://soundcloud.com/fictional/a-song") is None
    assert canonical_profile("https://soundcloud.com/search") is None


class Timer:
    value = 0.0

    def clock(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def test_http_retry_respects_retry_after_and_success_cache(tmp_path: Path) -> None:
    timer = Timer()
    timestamps = []

    def opener(request, timeout):
        timestamps.append(timer.value)
        assert request.get_header("User-agent").startswith("MTEEArtistPilot/")
        assert timeout == 15
        if len(timestamps) == 1:
            headers = Message()
            headers["Retry-After"] = "4"
            raise HTTPError(request.full_url, 429, "slow down", headers, None)
        return io.BytesIO(b'{"artists": []}')

    client = MusicBrainzClient(tmp_path, opener=opener, clock=timer.clock, sleeper=timer.sleep)
    assert client.get("artist/", {"query": "x"}) == {"artists": []}
    assert timestamps[1] - timestamps[0] >= 4
    assert client.get("artist/", {"query": "x"}) == {"artists": []}
    assert len(timestamps) == 2
    client.get("artist/", {"query": "y"})
    assert timestamps[2] - timestamps[1] == pytest.approx(1.1)


@pytest.mark.parametrize("body", [b"<html>error</html>", b"[]", b'{"error":"bad"}'])
def test_invalid_responses_do_not_become_empty_searches(tmp_path: Path, body: bytes) -> None:
    client = MusicBrainzClient(tmp_path, opener=lambda *a, **kw: io.BytesIO(body))
    with pytest.raises(ProviderError):
        client.get("artist/", {})
    assert not list(tmp_path.glob("*.json"))


def test_checkpoint_retries_error_but_preserves_success(tmp_path: Path) -> None:
    write_json(
        tmp_path / "artists.json",
        [{"artist_id": "a", "display_name": "A"}, {"artist_id": "b", "display_name": "B"}],
    )
    write_json(
        tmp_path / "musicbrainz.json",
        {
            "artists": {
                "a": {"status": "succeeded", "candidates": []},
                "b": {"status": "error", "error": "HTTP 503"},
            },
            "runs": [],
        },
    )

    class Client(MusicBrainzClient):
        requests = 0
        cache_hits = 0

        def __init__(self) -> None:  # no cache folder: the fake never reads the network
            pass

        def get(self, resource: str, parameters: dict) -> dict:
            assert resource == "artist/"
            assert "B" in parameters["query"]
            self.requests += 1
            return {"artists": []}

    result = enrich_musicbrainz(tmp_path, Client())
    assert result["artists"]["b"]["status"] == "succeeded"
    assert result["runs"][0]["http_requests"] == 1


def test_observations_require_evidence_and_reports_keep_human_decisions(tmp_path: Path) -> None:
    source = tmp_path / "input.sqlite3"
    database(source)
    run = tmp_path / "run"
    prepare(source, run, [], 50, 105)
    observation = {
        "artist_id": "artist-a",
        "roles": ["Producer"],
        "bass_related": True,
        "interest_proposal": "keep",
        "reason": "Official artist bio",
        "sources": [{"url": "https://example.org/artist", "title": "Official bio"}],
    }
    artists = json.loads((run / "artists.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="evidence"):
        validate_observations([{**observation, "sources": []}], artists)
    make_report(run, [observation])
    review = run / "human-review.csv"
    original = review.read_text(encoding="utf-8-sig")
    assert "pending" in original
    review.write_text(original.replace("pending", "exclude"), encoding="utf-8-sig")
    before = review.read_bytes()
    make_report(run, [observation])
    assert review.read_bytes() == before
    assert "Revue humaine à faire" in (run / "rapport.md").read_text(encoding="utf-8")

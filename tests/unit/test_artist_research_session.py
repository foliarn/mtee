from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from artist_enrichment_pilot import read_json, write_json
from artist_pilot_server import ReviewStore
from artist_research_session import ResearchSession


@pytest.fixture
def session(tmp_path):
    artists = [
        {"artist_id": aid, "display_name": aid, "representative_titles": ["Song"]}
        for aid in ["validated", "existing", "new", "other"]
    ]
    write_json(tmp_path / "artists.json", artists)
    write_json(tmp_path / "observations.json", [{"artist_id": "existing", "roles": ["MC"]}])
    write_json(
        tmp_path / "review.json", {"validated": {"validated_at": "yesterday", "roles": ["Singer"]}}
    )
    write_json(tmp_path / "musicbrainz.json", {"artists": {}, "runs": []})
    write_json(
        tmp_path / "sample.json",
        [
            {
                "title": "Song",
                "path": "private-path",
                "credits": [{"artist_id": "new", "name": "new", "credit_role": "remixer"}],
            }
        ],
    )
    client = Mock(requests=0, cache_hits=0)
    client.get.return_value = {"artists": []}
    return ResearchSession(ReviewStore(tmp_path), client)


def result(packet):
    return {
        "batch_id": packet["batch_id"],
        "observations": [
            {
                "artist_id": a["artist_id"],
                "roles": [],
                "bass_related": None,
                "interest_proposal": "uncertain",
                "identity_status": "unresolved",
                "links": [],
                "sources": [],
                "reason": "Inconnu",
                "issues": [],
            }
            for a in packet["artists"]
        ],
    }


def test_status_is_readonly_and_excludes_human_reviews(session):
    before = {p.name: p.read_bytes() for p in session.directory.iterdir()}
    assert session.status()["counts"] == {
        "queued": 2,
        "running": 0,
        "ready": 1,
        "validated": 1,
        "error": 0,
    }
    assert {p.name: p.read_bytes() for p in session.directory.iterdir()} == before
    session.client.get.assert_not_called()


def test_reservation_resumes_same_batch_without_network_or_paths(session):
    packet = session.next_batch(1)
    assert packet["artists"][0]["artist_id"] == "new"
    assert "private-path" not in json.dumps(packet)
    assert packet["artists"][0]["collaborations"][0]["credits"][0]["role"] == "remixer"
    assert session.next_batch(10) == packet
    resumed = ResearchSession(session.store, session.client)
    assert resumed.next_batch(5) == packet
    assert resumed.status()["counts"]["running"] == 1
    session.client.get.assert_not_called()


def test_collect_only_reserved_artist_and_reuses_checkpoint(session):
    packet = session.next_batch(1)
    collected = session.collect()
    assert collected["batch_id"] == packet["batch_id"]
    assert session.client.get.call_count == 1
    session.collect()
    assert session.client.get.call_count == 1
    assert session.status()["status"] == "audit"
    assert session.store.reviews()["validated"]["roles"] == ["Singer"]


def test_import_is_atomic_idempotent_and_no_human_validation(session):
    packet = session.next_batch(1)
    session.collect()
    reviews = session.store.reviews()
    payload = result(packet)
    assert session.import_result(payload) == {"imported": 1, "idempotent": False}
    assert session.import_result(payload) == {"imported": 1, "idempotent": True}
    assert session.store.reviews() == reviews
    assert session.next_batch(5)["artists"][0]["artist_id"] == "other"
    assert read_json(session.directory / "observations.json")[0] == {
        "artist_id": "existing",
        "roles": ["MC"],
    }


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "unknown", "source", "profile", "schema"]
)
def test_invalid_result_never_publishes(session, change):
    packet = session.next_batch(2)
    session.collect()
    payload = result(packet)
    if change == "missing":
        payload["observations"].pop()
    elif change == "duplicate":
        payload["observations"][1] = payload["observations"][0]
    elif change == "unknown":
        payload["observations"][0]["artist_id"] = "unknown"
    elif change == "source":
        payload["observations"][0]["identity_status"] = "matched"
    elif change == "profile":
        payload["observations"][0]["links"] = [
            {
                "label": "Spotify",
                "url": "https://open.spotify.com/artist/not-an-id",
                "evidence_url": "https://example.com",
            }
        ]
    else:
        payload["observations"][0]["bass_related"] = 1
    before = (session.directory / "observations.json").read_bytes()
    with pytest.raises(ValueError):
        session.import_result(payload)
    assert (session.directory / "observations.json").read_bytes() == before
    assert session.state()["active"] == packet["batch_id"]


def test_validation_during_web_research_wins(session):
    packet = session.next_batch(1)
    session.collect()
    session.store.save_page(
        {"new": {"decision": "exclude", "roles": ["MC"], "bass_related": False}}
    )
    assert session.import_result(result(packet))["imported"] == 0
    assert session.store.reviews()["new"]["tags"] == ["idgaf"]
    assert {o["artist_id"] for o in read_json(session.directory / "observations.json")} == {
        "existing"
    }


def test_collection_failure_preserves_batch_and_reuses_partial_success(session):
    packet = session.next_batch(2)
    session.client.get.side_effect = [{"artists": []}, RuntimeError("offline")]
    with pytest.raises(RuntimeError, match="offline"):
        session.collect()
    assert session.status()["status"] == "paused"
    session.client.get.side_effect = None
    session.collect()
    assert session.client.get.call_count == 3
    assert session.next_batch()["batch_id"] == packet["batch_id"]


def test_crash_between_publication_and_receipt_recovers(session):
    packet = session.next_batch(1)
    session.collect()
    original_state = session.state()
    session.import_result(result(packet))
    write_json(session.path, original_state)
    next_packet = session.next_batch(1)
    assert next_packet["artists"][0]["artist_id"] == "other"
    assert session.state()["batches"][packet["batch_id"]]["status"] == "recovered"


def test_import_requires_collection_and_closed_batch_cannot_change(session):
    packet = session.next_batch(1)
    payload = result(packet)
    with pytest.raises(ValueError, match="collect"):
        session.import_result(payload)
    session.collect()
    session.import_result(payload)
    payload["observations"][0]["reason"] = "different"
    with pytest.raises(ValueError, match="clos"):
        session.import_result(payload)


def test_explicit_pause_keeps_batch(session):
    packet = session.next_batch(1)
    session.progress("Limite de recherche", paused=True)
    assert session.status()["status"] == "paused"
    assert session.next_batch()["batch_id"] == packet["batch_id"]


def test_no_ai_constructor_or_process_is_used(monkeypatch, session):
    forbidden = Mock(side_effect=AssertionError("No AI worker"))
    monkeypatch.setattr("artist_enrichment_worker.CodexAudit", forbidden)
    monkeypatch.setattr("artist_enrichment_worker.subprocess.Popen", forbidden)
    packet = session.next_batch(1)
    session.collect()
    session.import_result(result(packet))
    forbidden.assert_not_called()

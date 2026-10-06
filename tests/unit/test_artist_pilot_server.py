from __future__ import annotations

import csv
import io
import json
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from artist_enrichment_pilot import write_json
from artist_pilot_server import ReviewStore, make_server


@pytest.fixture
def pilot(tmp_path):
    write_json(tmp_path / "artists.json", [{"artist_id": "a", "display_name": "Test"}])
    write_json(
        tmp_path / "sample.json", [{"track_id": "t", "path": "private-path", "title": "Test"}]
    )
    for name in ["summary", "musicbrainz"]:
        write_json(tmp_path / f"{name}.json", {})
    write_json(tmp_path / "observations.json", [{"artist_id": "a", "roles": ["MC"]}])
    return tmp_path


def test_review_persistence_is_separate_and_export_escapes_formulas(pilot):
    before = {p.name: p.read_bytes() for p in pilot.iterdir()}
    store = ReviewStore(pilot)
    record = store.save(
        "a", {"decision": "keep", "roles": ["MC", "MC"], "bass_related": True, "notes": "=SUM(A1)"}
    )
    assert ReviewStore(pilot).reviews()["a"] == record
    assert record["roles"] == ["MC"]
    assert {p.name: p.read_bytes() for p in pilot.iterdir() if p.name != "review.json"} == before
    assert "path" not in store.data()["tracks"][0]
    rows = list(csv.DictReader(io.StringIO(store.export().decode("utf-8-sig"))))
    assert rows[0]["notes"] == "'=SUM(A1)"


def test_profiles_can_be_corrected_without_changing_evidence(pilot):
    store = ReviewStore(pilot)
    before = (pilot / "observations.json").read_bytes()
    record = store.save(
        "a",
        {
            "decision": "uncertain",
            "roles": [],
            "identity_decision": "accepted",
            "spotify_url": "https://open.spotify.com/artist/0123456789ABCDEFGHIJKL?si=test",
            "soundcloud_url": "https://soundcloud.com/example-artist?si=test",
        },
    )
    assert record["spotify_url"] == "https://open.spotify.com/artist/0123456789ABCDEFGHIJKL"
    assert record["soundcloud_url"] == "https://soundcloud.com/example-artist"
    assert store.reviews()["a"]["identity_decision"] == "accepted"
    assert (pilot / "observations.json").read_bytes() == before


def test_unchanged_proposals_are_effective_without_individual_writes(pilot):
    write_json(
        pilot / "observations.json",
        [
            {
                "artist_id": "a",
                "roles": ["MC"],
                "interest_proposal": "exclude",
                "identity_status": "unresolved",
                "bass_related": True,
                "links": [{"url": "https://soundcloud.com/example-artist"}],
            }
        ],
    )
    store = ReviewStore(pilot)
    record = store.data()["reviews"]["a"]
    assert record["decision"] == "exclude"
    assert record["roles"] == ["MC"]
    assert record["identity_decision"] == "pending"  # no invented identity
    assert record["accepted_by_default"] is True
    assert not store.path.exists()
    row = next(csv.DictReader(io.StringIO(store.export().decode("utf-8-sig"))))
    assert row["human_decision"] == "exclude"
    assert row["soundcloud_url_corrected"] == "https://soundcloud.com/example-artist"
    assert row["acceptance"] == "default"


def test_batch_is_atomic_and_preserves_existing_corrections(pilot):
    write_json(pilot / "artists.json", [{"artist_id": x, "display_name": x} for x in ("a", "b")])
    store = ReviewStore(pilot)
    store.save("a", {"decision": "keep", "roles": ["MC"], "notes": "existing"})
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save_many(
            {"a": {"decision": "exclude", "roles": []}, "b": {"decision": "delete", "roles": []}}
        )
    assert store.path.read_bytes() == before
    store.save_many({"b": {"decision": "uncertain", "roles": ["DJ"]}})
    assert store.reviews()["a"]["notes"] == "existing"
    assert store.data()["reviews"]["b"]["accepted_by_default"] is False


def test_two_thousand_artists_need_only_changed_records(pilot):
    write_json(
        pilot / "artists.json",
        [{"artist_id": str(i), "display_name": f"Artist {i}"} for i in range(2000)],
    )
    with (pilot / "human-review.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["artist_id", "human_decision", "roles_corrected", "notes"])
        writer.writerows([[str(i), "pending", "", ""] for i in range(2000)])
    store = ReviewStore(pilot)
    assert len(store.data()["reviews"]) == 2000
    assert not store.path.exists()
    store.save_many(
        {
            "17": {"decision": "keep", "roles": ["Producer"]},
            "1999": {"decision": "exclude", "roles": []},
        }
    )
    assert set(store.reviews()) == {"17", "1999"}
    assert len(list(csv.DictReader(io.StringIO(store.export().decode("utf-8-sig"))))) == 2000


def test_legacy_notes_are_preserved_without_a_tri_decision(pilot):
    (pilot / "human-review.csv").write_text(
        "artist_id,human_decision,roles_corrected,notes\na,pending,,existing note\n",
        encoding="utf-8",
    )
    assert ReviewStore(pilot).data()["reviews"]["a"]["notes"] == "existing note"


def test_producer_defaults_to_dj_but_explicit_dj_exception_is_kept(pilot):
    write_json(pilot / "observations.json", [{"artist_id": "a", "roles": ["Producer"]}])
    before = (pilot / "observations.json").read_bytes()
    store = ReviewStore(pilot)
    assert store.data()["reviews"]["a"]["roles"] == ["Producer", "DJ"]
    assert not store.path.exists()
    store.save("a", {"decision": "keep", "roles": ["Producer"]})
    assert store.data()["reviews"]["a"]["roles"] == ["Producer"]
    assert (pilot / "observations.json").read_bytes() == before


def test_explicit_unknown_and_removed_profile_override_proposal(pilot):
    write_json(
        pilot / "observations.json",
        [
            {
                "artist_id": "a",
                "roles": ["MC"],
                "bass_related": True,
                "links": [{"url": "https://soundcloud.com/example-artist"}],
            }
        ],
    )
    store = ReviewStore(pilot)
    store.save("a", {"decision": "keep", "roles": [], "bass_related": None, "soundcloud_url": ""})
    record = store.data()["reviews"]["a"]
    assert record["bass_related"] is None
    assert record["roles"] == []
    assert record["soundcloud_url"] == ""


def test_old_pending_tri_uses_proposal_and_keeps_corrections(pilot):
    store = ReviewStore(pilot)
    store.save("a", {"decision": "pending", "roles": ["DJ"], "notes": "previous correction"})
    record = store.data()["reviews"]["a"]
    assert record["decision"] == "keep"
    assert record["roles"] == ["DJ"]
    assert record["notes"] == "previous correction"


def test_unknown_defaults_and_idgaf_leave_source_records_intact(pilot):
    store = ReviewStore(pilot)
    assert store.data()["reviews"]["a"]["decision"] == "keep"
    assert store.data()["reviews"]["a"]["bass_related"] is False
    before = (pilot / "artists.json").read_bytes()
    store.save("a", {"decision": "exclude", "roles": ["MC"]})
    assert store.reviews()["a"]["tags"] == ["idgaf"]
    assert (pilot / "artists.json").read_bytes() == before
    row = next(csv.DictReader(io.StringIO(store.export().decode("utf-8-sig"))))
    assert row["artist_tags"] == "idgaf"
    store.save("a", {"decision": "keep", "roles": ["MC"]})
    assert store.reviews()["a"]["tags"] == []


def test_page_validation_is_bounded_atomic_and_does_not_accept_other_pages(pilot):
    write_json(
        pilot / "artists.json", [{"artist_id": str(i), "display_name": str(i)} for i in range(201)]
    )
    store = ReviewStore(pilot)
    store.save("200", {"decision": "exclude", "roles": [], "notes": "Keep prior choice"})
    original = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save_page({str(i): {"decision": "keep", "roles": []} for i in range(101)})
    assert store.path.read_bytes() == original
    store.save_page({str(i): {"decision": "keep", "roles": []} for i in range(100)})
    assert len(store.reviews()) == 101
    assert "100" not in store.reviews()
    assert store.reviews()["200"]["notes"] == "Keep prior choice"


def test_track_audit_and_clickable_categories_preserve_original_tags(pilot):
    write_json(
        pilot / "sample.json",
        [
            {
                "track_id": "t",
                "title": "Test (Remix)",
                "observed_genres": ["Electronic, House"],
                "credits": [{"artist_id": "a", "name": "Test", "credit_role": "artist"}],
            }
        ],
    )
    write_json(
        pilot / "genre-rules.json",
        {
            "tracks": {
                "t": {
                    "genres": ["Drum & Bass"],
                    "rejected_tags": {"house": "User correction"},
                }
            }
        },
    )
    before = (pilot / "sample.json").read_bytes()
    track = ReviewStore(pilot).data()["tracks"][0]
    assert track["genre_audit"]["retained"] == ["Drum & Bass"]
    assert "remix" in track["selection_categories"]
    assert track["observed_genres"] == ["Electronic, House"]
    assert (pilot / "sample.json").read_bytes() == before


@pytest.mark.parametrize(
    "aid,patch",
    [
        ("unknown", {}),
        ("a", {"decision": "delete"}),
        ("a", {"roles": ["Fake"]}),
        ("a", {"roles": "MC"}),
        ("a", {"bass_related": "yes"}),
        ("a", {"notes": "x" * 4001}),
        ("a", {"spotify_url": "https://open.spotify.com/album/0123456789ABCDEFGHIJKL"}),
        ("a", {"soundcloud_url": "https://soundcloud.com/example-artist/track"}),
        ("a", {"spotify_url": "https://soundcloud.com/example-artist"}),
        ("a", {"identity_decision": "follow"}),
    ],
)
def test_invalid_review_never_writes(pilot, aid, patch):
    payload = {"decision": "pending", "roles": [], "bass_related": None, "notes": ""} | patch
    with pytest.raises(ValueError):
        ReviewStore(pilot).save(aid, payload)
    assert not (pilot / "review.json").exists()


def test_http_local_only_static_allowlist_and_same_origin_save(pilot):
    server = make_server(pilot, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/data", timeout=2) as response:
            assert response.headers["Cache-Control"] == "no-store"
            assert "path" not in json.load(response)["tracks"][0]
        for path in ["/catalog.json", "/../artist_enrichment_pilot.py", "/review.json"]:
            with pytest.raises(HTTPError) as caught:
                urlopen(base + path, timeout=2)
            assert caught.value.code == 404
        payload = json.dumps({"decision": "keep", "roles": ["MC"], "bass_related": True}).encode()
        for origin in [None, "https://foreign.example"]:
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            with pytest.raises(HTTPError) as caught:
                urlopen(
                    Request(base + "/api/review/a", data=payload, method="PUT", headers=headers),
                    timeout=2,
                )
            assert caught.value.code == 403
        request = Request(
            base + "/api/review/a",
            data=payload,
            method="PUT",
            headers={"Content-Type": "application/json", "Origin": base},
        )
        with urlopen(request, timeout=2) as response:
            assert json.load(response)["decision"] == "keep"
        request = Request(
            base + "/api/reviews",
            data=json.dumps({"a": {"decision": "exclude", "roles": []}}).encode(),
            method="PUT",
            headers={"Content-Type": "application/json", "Origin": base},
        )
        with urlopen(request, timeout=2) as response:
            assert json.load(response)["a"]["decision"] == "exclude"
        with pytest.raises(HTTPError) as caught:
            urlopen(Request(base + "/api/data", headers={"Host": "foreign.example"}), timeout=2)
        assert caught.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

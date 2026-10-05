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
        with pytest.raises(HTTPError) as caught:
            urlopen(Request(base + "/api/data", headers={"Host": "foreign.example"}), timeout=2)
        assert caught.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

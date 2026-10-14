import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "archive"))
from track_genre_audit import audit_track


def test_compound_generic_tags_are_ignored_without_losing_specific_genres():
    result = audit_track(
        {
            "observed_genres": [
                "Electronic, House",
                "Dance / Pop",
                "Alternative",
                "Electronica",
                "UKG 2-Step",
                "Jungle",
            ]
        },
        {},
    )
    assert result["retained"] == ["House", "UKG 2-Step", "Jungle"]
    assert result["ignored"] == ["Electronic", "Dance", "Pop", "Alternative", "Electronica"]


def test_artist_context_only_rejects_house_and_never_assigns_artist_genres():
    track = {
        "credits": [{"artist_id": "a", "name": "Artist"}],
        "observed_genres": ["House", "Dubstep"],
    }
    rules = {
        "artists": {
            "a": {
                "house_unlikely": True,
                "genres": ["Drum & Bass"],
                "source": "Verified career context",
            }
        }
    }
    result = audit_track(track, rules)
    assert result["retained"] == ["Dubstep"]
    assert result["alerts"][0]["tag"] == "House"
    assert audit_track({**track, "observed_genres": []}, rules)["retained"] == []
    rules["artists"]["a"].pop("source")
    assert audit_track(track, rules)["retained"] == ["House", "Dubstep"]


def test_recording_correction_does_not_spread_to_other_tracks():
    rules = {
        "tracks": {
            "t": {
                "genres": ["Drum & Bass"],
                "source": "User correction",
                "rejected_tags": {"house": "Wrong tag"},
            }
        }
    }
    track = {"track_id": "t", "observed_genres": ["Electronic, House"]}
    result = audit_track(track, rules)
    assert result["retained"] == ["Drum & Bass"]
    assert result["alerts"] == [{"tag": "House", "reason": "Wrong tag"}]
    assert audit_track({**track, "track_id": "other"}, rules)["retained"] == ["House"]


def test_multi_genre_artist_without_explicit_conflict_keeps_track_tags():
    rules = {"artists": {"a": {"genres": ["UKG", "Dubstep", "Jungle"]}}}
    track = {"credits": [{"artist_id": "a", "name": "Artist"}], "observed_genres": ["House"]}
    assert audit_track(track, rules)["retained"] == ["House"]

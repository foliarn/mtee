"""Synthetic safety and repeatability checks for the local ExecPlan 102 tool."""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path

import pytest
from mutagen.id3 import TIT2, TPE1
from mutagen.wave import WAVE
from scripts.audit_mapping_sample import (
    _clean_annotation,
    _inventory_one,
    _is_link_or_junction,
    _motifs,
    _music_refs,
    _parse_filename_metadata,
    _values,
    propose_metadata,
    run,
    same_artist_credit,
    select_sample,
    simulate_rename_proposals,
)


def _row(
    index: int, extension: str = ".mp3", *, title: str = "Title", artist: str = "Artist"
) -> dict:
    return {
        "item_id": f"item-{index}",
        "root_alias": "R1",
        "relative_path": f"Folder/Track {index}{extension}",
        "extension": extension,
        "status": "readable",
        "tags": {
            "title": [title] if title else [],
            "artist": [artist] if artist else [],
            "album": [],
            "album_artist": [],
            "genre": [],
            "date": [],
            "bpm": [],
            "key": [],
        },
        "music_urls": [],
    }


def test_sample_is_independent_of_inventory_order_and_has_disjoint_groups() -> None:
    rows = [_row(index) for index in range(220)]
    first = select_sample(rows, seed=102)
    second = select_sample(list(reversed(rows)), seed=102)

    def signature(sample: list[dict]) -> list[tuple[str, str]]:
        return [(row["sample_group"], row["item_id"]) for row in sample]

    assert signature(first) == signature(second)
    random_ids = {row["item_id"] for row in first if row["sample_group"] == "random"}
    targeted_ids = {row["item_id"] for row in first if row["sample_group"] == "targeted"}
    assert len(random_ids) == 100
    assert len(targeted_ids) == 50
    assert not random_ids & targeted_ids


def test_small_population_and_rare_formats_are_bounded() -> None:
    rows = [_row(0, ".wav"), _row(1, ".aiff"), _row(2, ".mp3", title="", artist="")]
    selected = select_sample(rows, random_size=1, targeted_size=50)
    assert len(selected) == 3
    assert len({row["item_id"] for row in selected}) == 3
    extensions = {Path(row["relative_path"]).suffix for row in selected}
    assert extensions == {".wav", ".aiff", ".mp3"}


def test_targeted_missing_artist_quotas_do_not_recount_missing_both() -> None:
    rows = [_row(index, title="", artist="") for index in range(80)]
    rows.extend(_row(index + 80, title=f"Title {index}", artist="") for index in range(80))
    rows.extend(_row(index + 160) for index in range(80))

    targeted = [
        row
        for row in select_sample(rows, random_size=0, targeted_size=50)
        if row["sample_group"] == "targeted"
    ]

    priority_two = [row for row in targeted if row["sample_priority"] == 2]
    assert sum("title_and_artist_missing" in row["sample_motifs"] for row in priority_two) == 15
    assert sum("artist_only_missing" in row["sample_motifs"] for row in priority_two) == 15


def test_inventory_records_unicode_multivalues_without_changing_audio(tmp_path: Path) -> None:
    path = tmp_path / "Café.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    row = _inventory_one("R1", tmp_path, path)

    assert row["status"] == "readable"
    assert row["relative_path"] == "Café.wav"
    assert row["tags"]["title"] == []
    assert row["changed_during_read"] is False
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_inventory_preserves_raw_multivalues_and_version_markers(tmp_path: Path) -> None:
    path = tmp_path / "Artist - Song (Extended Remix).wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 80)
    tagged = WAVE(path)
    tagged.add_tags()
    assert tagged.tags is not None
    tagged.tags.add(TIT2(encoding=3, text=["Song (Extended Remix)", "Song (Radio Edit)"]))
    tagged.tags.add(TPE1(encoding=3, text=["Zoë", "Guest"]))
    tagged.save()

    row = _inventory_one("R1", tmp_path, path)

    assert row["tags"]["title"] == ["Song (Extended Remix)", "Song (Radio Edit)"]
    assert row["tags"]["artist"] == ["Zoë", "Guest"]
    assert "version_marker" in _motifs(row)


def test_unreadable_files_remain_in_inventory(tmp_path: Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not audio")
    row = _inventory_one("R1", tmp_path, path)
    assert row["status"] == "unreadable"
    assert row["error"]


def test_mutagen_missing_tag_alias_value_error_is_treated_as_absent() -> None:
    class MutagenTags(dict):
        def get(self, key: str, default: object = None) -> object:
            if key not in self:
                raise ValueError
            return super().get(key, default)

    assert _values(MutagenTags({"TITLE": ["Song"]}), ("artist", "TITLE")) == ["Song"]


def test_music_references_keep_identifiers_and_strip_sensitive_url_parameters() -> None:
    tags = {
        "spotify_track_id": ["spotify:track:0123456789abcdef"],
        "website": ["https://www.soundcloud.com/artist/song?token=private"],
        "private_token": ["do-not-keep"],
        "unrelated_url": ["https://example.invalid/music"],
    }

    urls, identifiers = _music_refs(tags, list(tags))

    assert urls == ["https://www.soundcloud.com/artist/song"]
    assert identifiers == [
        {"source_key": "spotify_track_id", "value": "spotify:track:0123456789abcdef"}
    ]


def test_junctions_are_treated_like_links() -> None:
    class Junction:
        def is_symlink(self) -> bool:
            return False

        def is_junction(self) -> bool:
            return True

    assert _is_link_or_junction(Junction())  # type: ignore[arg-type]


def test_run_refuses_output_inside_root_before_scanning(tmp_path: Path) -> None:
    root = tmp_path / "collection"
    root.mkdir()
    nested_output = root / ".local" / "result"
    args = type(
        "Args",
        (),
        {
            "output": str(nested_output),
            "inventory_input": None,
            "root": [str(root)],
            "seed": 102,
            "random_size": 100,
            "targeted_size": 50,
        },
    )()
    with pytest.raises(ValueError, match="outside"):
        run(args)
    assert not nested_output.exists()


def test_frozen_inventory_input_is_reusable_without_roots(tmp_path: Path) -> None:
    inventory = [_row(index) for index in range(4)]
    input_path = tmp_path / "inventory.jsonl"
    input_path.write_text("".join(json.dumps(row) + "\n" for row in inventory), encoding="utf-8")
    args = type(
        "Args",
        (),
        {
            "output": str(tmp_path / "output"),
            "inventory_input": str(input_path),
            "root": None,
            "seed": 102,
            "random_size": 2,
            "targeted_size": 1,
        },
    )()

    result = run(args)

    assert (result / "run.json").is_file()
    assert len((result / "inventory.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    assert len((result / "sample.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_title_prefix_artist_is_removed_and_all_title_values_are_cleaned() -> None:
    row = _row(
        1,
        title="Ev & Taiki Nulight - Chaos (Free Download) (Taiki Nulight Remix)",
        artist="Ev & Taiki Nulight",
    )
    row["tags"]["title"].append("Ev & Taiki Nulight - Chaos (Radio Edit)")

    proposal = propose_metadata(row, ["Ev", "Taiki Nulight", "Ev & Taiki Nulight"])

    assert proposal["proposed_artists"] == ["Ev & Taiki Nulight"]
    assert proposal["proposed_titles"] == ["Chaos (Taiki Nulight Remix)", "Chaos (Radio Edit)"]
    assert proposal["existing_titles"] == row["tags"]["title"]
    assert "Free Download" in proposal["removed_annotations"]


def test_artist_can_be_in_title_and_imperfect_filename_separator_is_supported() -> None:
    from_title = _row(1, title="HERMIT - BREAK IT OFF (Extended Mix)", artist="")
    title_proposal = propose_metadata(from_title, [])
    assert title_proposal["proposed_artists"] == ["HERMIT"]
    assert title_proposal["proposed_titles"] == ["BREAK IT OFF (Extended Mix)"]
    assert (
        title_proposal["artist_evidence_basis"] == "uppercase_artist_prefix_in_title_tag_unverified"
    )

    artists, title, _ = _parse_filename_metadata("Mozey- Hands.wav", ["Mozey", "AC-13"])
    assert artists == ["Mozey"]
    assert title == "Hands"
    # The longer known credit must win before the dash is interpreted as a separator.
    artists, title, _ = _parse_filename_metadata("AC-13 - Track.wav", ["AC-13", "AC"])
    assert artists == ["AC-13"]
    assert title == "Track"


def test_cleaning_removes_technical_catalog_noise_but_keeps_version_and_flags_year() -> None:
    title, removed, ambiguous = _clean_annotation(
        "Track (Free Download) (HYP123) (320kbps) (Extended Remix) (2025)"
    )
    assert title == "Track (Extended Remix) (2025)"
    assert {"Free Download", "HYP123", "320kbps"} <= set(removed)
    assert "2025" in ambiguous


def test_cleaning_does_not_remove_technical_words_when_they_are_track_text() -> None:
    title, removed, _ = _clean_annotation("Master of Puppets")
    assert title == "Master of Puppets"
    assert removed == []


def test_artist_collaboration_separator_differences_are_not_conflicts() -> None:
    known = ["Ev", "Taiki Nulight", "Ev & Taiki Nulight"]
    assert same_artist_credit("Ev & Taiki Nulight", "Ev, Taiki Nulight", known)
    assert not same_artist_credit("Ev & Taiki Nulight", "Ev & Mozey", [*known, "Mozey"])


def test_user_identified_a_plus_and_ev_collaborations_remain_artist_values() -> None:
    for credit, known in (
        ("Riordan, A+", ["Riordan", "A+"]),
        ("Ev & Taiki Nulight", ["Ev", "Taiki Nulight"]),
    ):
        row = _row(1, title="Track", artist=credit)
        proposal = propose_metadata(row, known)
        assert proposal["proposed_artists"] == [credit]
        assert same_artist_credit(credit, " & ".join(known), [*known, credit])


def test_encoding_damage_is_reported_without_rewriting_artist_or_title() -> None:
    row = _row(1, title="Caf� Song", artist="Zo�")
    proposal = propose_metadata(row, ["Zo�"])
    assert proposal["encoding_warning"] is True
    assert "possible_encoding_corruption" in proposal["ambiguous_annotations"]
    assert proposal["proposed_artists"] == ["Zo�"]


def test_rename_simulation_checks_existing_proposed_and_windows_collisions() -> None:
    inventory = [
        _row(1, title="Shared", artist="One"),
        _row(2, title="", artist="Two"),
        _row(3, title="NUL", artist="Three"),
        _row(4, title="Taken", artist="Four"),
        _row(5, title="Shared", artist="Five"),
    ]
    inventory[4]["relative_path"] = "Folder/Shared.mp3"
    proposals = {
        "item-1": {"proposed_titles": ["Shared"]},
        "item-2": {"proposed_titles": ["Shared"]},
        "item-3": {"proposed_titles": ["NUL"]},
        "item-4": {"proposed_titles": ["Taken?"]},
    }
    previews = simulate_rename_proposals(inventory, proposals)
    assert any(c["kind"] == "proposed_target" for c in previews[0]["collisions"])
    assert any(c["kind"] == "proposed_target" for c in previews[1]["collisions"])
    assert any(c["kind"] == "existing_file" for c in previews[0]["collisions"])
    assert previews[2]["windows_name_issues"]
    assert previews[3]["windows_name_issues"]
    assert all(not row["rename_applied"] for row in previews)


def test_rename_simulation_uses_windows_case_and_trailing_dot_identity() -> None:
    inventory = [_row(1), _row(2)]
    inventory[0]["relative_path"] = "Folder/Old.mp3"
    inventory[1]["relative_path"] = "folder/TITLE.mp3"
    previews = simulate_rename_proposals(
        inventory,
        {"item-1": {"proposed_titles": ["title"]}, "item-2": {"proposed_titles": ["Trailing. "]}},
    )
    assert any(c["kind"] == "existing_file" for c in previews[0]["collisions"])
    assert previews[1]["windows_name_issues"]
    assert not previews[0]["rename_applied"]

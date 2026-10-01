from __future__ import annotations

from pathlib import Path

import pytest

from mtee.domain.analysis import ANALYSIS_ALGORITHM_VERSION, AnalysisSettings, format_bpm
from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.musical_key import MusicalKey
from mtee.domain.tracks import SourceRevision
from mtee.domain.waveform import WaveformPoints
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository


@pytest.fixture
def database(tmp_path: Path):
    database = Database(tmp_path / "mtee.sqlite3")
    database.migrate()
    yield database
    database.close()


def _add_track(database: Database, track_id: str) -> None:
    with database.transaction() as connection:
        connection.execute("INSERT INTO tracks(track_id) VALUES (?)", (track_id,))


def _points(duration_us: int = 5_000_000) -> WaveformPoints:
    return WaveformPoints(duration_us, (-100, -200), (100, 300), (70, 150))


def test_a_result_is_stored_and_read_back(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    assert repository.get("t1") is None

    saved = repository.save_result(
        "t1", bpm=127.98123, key=MusicalKey(6, True), source_duration_us=200_000_000
    )

    assert saved.bpm == pytest.approx(127.981)
    assert saved.key == MusicalKey(6, True)
    assert saved.analyzed
    assert saved.algorithm_version == ANALYSIS_ALGORITHM_VERSION
    assert repository.get("t1") == saved
    assert repository.get_many(["t1", "missing"]) == {"t1": saved}


def test_an_undetermined_value_is_stored_as_unknown_not_zero(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    saved = repository.save_result("t1", bpm=None, key=None, source_duration_us=None)
    assert saved.bpm is None and saved.key is None and saved.analyzed


def test_a_value_edited_by_the_user_is_never_replaced_by_an_analysis(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.save_result("t1", bpm=120.0, key=MusicalKey(0, False), source_duration_us=1)
    repository.mark_user_edited(["t1"], "bpm")

    repeated = repository.save_result(
        "t1", bpm=140.0, key=MusicalKey(2, True), source_duration_us=1
    )

    assert repeated.bpm == 120.0  # kept: the user edited the tempo
    assert repeated.bpm_user_edited and not repeated.key_user_edited
    assert repeated.key == MusicalKey(2, True)  # replaced: the key was not edited


def test_an_edit_made_before_any_analysis_protects_the_value_from_a_later_one(
    database: Database,
) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.mark_user_edited(["t1"], "key")
    before = repository.get("t1")
    assert before is not None and not before.analyzed and before.key_user_edited

    after = repository.save_result("t1", bpm=100.0, key=MusicalKey(5, False), source_duration_us=1)

    assert after.key is None and after.key_user_edited
    assert after.bpm == 100.0
    assert after.analyzed


def test_only_bpm_and_key_can_be_flagged(database: Database) -> None:
    _add_track(database, "t1")
    with pytest.raises(ValueError):
        AnalysisRepository(database).mark_user_edited(["t1"], "title")


def test_a_waveform_is_permanent_and_replaced_in_place(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    assert repository.load_waveform("t1", 5_000_000) is None
    repository.save_waveform("t1", _points(), 5_000_000)
    assert repository.load_waveform("t1", 5_000_000) == _points()
    repository.save_waveform("t1", _points(6_000_000), 6_000_000)
    assert repository.load_waveform("t1", 6_000_000) == _points(6_000_000)


def test_a_waveform_survives_a_tag_edit_but_not_a_replaced_audio_file(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.save_waveform("t1", _points(), 200_000_000)
    assert repository.load_waveform("t1", 200_000_000) is not None
    assert repository.load_waveform("t1", 200_400_000) is not None  # same audio, tags rewritten
    assert repository.load_waveform("t1", 231_000_000) is None  # a different length
    assert repository.load_waveform("t1", None) is not None  # length unknown: keep the result


def test_a_waveform_from_another_algorithm_version_is_recomputed(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.save_waveform("t1", _points(), 5_000_000)
    with database.transaction() as connection:
        connection.execute("UPDATE track_waveforms SET algorithm_version = 0")
    assert repository.load_waveform("t1", 5_000_000) is None


def test_a_version_one_waveform_is_ignored_and_a_version_two_one_is_read(
    database: Database,
) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    # A version 1 row holds (low, high) pairs of 4 bytes, which the new format cannot read.
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO track_waveforms (track_id, duration_us, source_duration_us, "
            "points, algorithm_version, computed_at_utc) VALUES ('t1', 5000000, 5000000, "
            "x'9CFF6400', 1, '2026-09-30T00:00:00Z')"
        )
    assert repository.load_waveform("t1", 5_000_000) is None
    assert not repository.has_current_waveform("t1", 5_000_000)
    repository.save_waveform("t1", _points(), 5_000_000)
    assert repository.load_waveform("t1", 5_000_000) == _points()
    assert repository.has_current_waveform("t1", 5_000_000)
    assert not repository.has_current_waveform("t1", 9_000_000)  # a different audio length


def test_a_damaged_stored_waveform_is_ignored(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.save_waveform("t1", _points(), 5_000_000)
    with database.transaction() as connection:
        connection.execute("UPDATE track_waveforms SET points = x'0102030405'")
    assert repository.load_waveform("t1", 5_000_000) is None


def test_the_current_check_uses_version_and_audio_length(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    assert not repository.is_current(None, 1)
    saved = repository.save_result("t1", bpm=120.0, key=None, source_duration_us=10_000_000)
    assert repository.is_current(saved, 10_000_000)
    assert repository.is_current(saved, 10_500_000)
    assert not repository.is_current(saved, 12_500_000)
    flagged_only = AnalysisRepository(database)
    _add_track(database, "t2")
    flagged_only.mark_user_edited(["t2"], "bpm")
    assert not flagged_only.is_current(flagged_only.get("t2"), 1)


def test_an_older_analysis_is_analyzed_again_but_its_waveform_is_kept(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    saved = repository.save_result("t1", bpm=120.0, key=None, source_duration_us=5_000_000)
    repository.save_waveform("t1", _points(), 5_000_000)
    assert repository.is_current(saved, 5_000_000)

    with database.transaction() as connection:  # what a result of the previous version looks like
        connection.execute(
            "UPDATE track_analysis SET algorithm_version = ?", (ANALYSIS_ALGORITHM_VERSION - 1,)
        )
    older = repository.get("t1")
    assert not repository.is_current(older, 5_000_000)
    assert repository.load_waveform("t1", 5_000_000) == _points()


def test_removing_a_track_removes_its_results(database: Database) -> None:
    _add_track(database, "t1")
    repository = AnalysisRepository(database)
    repository.save_result("t1", bpm=120.0, key=None, source_duration_us=1)
    repository.save_waveform("t1", _points(), 1)
    with database.transaction() as connection:
        connection.execute("DELETE FROM tracks WHERE track_id = 't1'")
    assert repository.get("t1") is None
    assert repository.load_waveform("t1", 1) is None


def test_settings_are_brought_inside_their_limits() -> None:
    settings = AnalysisSettings(
        notation="nope", bpm_min=10, bpm_max=20, parallel_jobs=99, bpm_decimals=7
    ).normalized()
    assert settings.notation == "camelot"
    assert settings.bpm_min == 40 and settings.bpm_max == 80
    assert settings.parallel_jobs == 8 and settings.bpm_decimals == 2
    wide = AnalysisSettings(bpm_min=70, bpm_max=180).normalized()
    assert (wide.bpm_min, wide.bpm_max) == (70, 180)
    tight = AnalysisSettings(bpm_min=100, bpm_max=150).normalized()
    assert tight.bpm_max == 200  # one full octave at least


def test_bpm_is_written_with_the_chosen_decimals() -> None:
    assert format_bpm(127.98123, 2) == "127.98"
    assert format_bpm(127.98123, 1) == "128.0"
    assert format_bpm(127.5, 0) == "128"
    assert format_bpm("not a number", 2) == "not a number"


def test_the_library_lists_a_folder_tree_and_shows_calculated_values(
    database: Database, tmp_path: Path
) -> None:
    library = LibraryRepository(database)
    root = library.add_root(tmp_path)
    audio = _write_scanned_tracks(database, library, root["id"], tmp_path)
    repository = AnalysisRepository(database)

    everything = library.track_ids_in_tree(root["id"], "")
    assert sorted(everything) == sorted(audio.values())
    assert sorted(library.track_ids_in_tree(root["id"], "sets")) == sorted(
        [audio["sets/a.wav"], audio["sets/deep/b.wav"]]
    )
    assert library.track_ids_in_tree(root["id"], "sets/deep") == [audio["sets/deep/b.wav"]]
    assert library.track_ids_in_tree(root["id"], "se") == []  # a prefix is not a folder

    track_id = audio["top.wav"]
    plain = library.tracks_in_folder(root["id"], "")[0]
    assert plain["bpmText"] == "" and plain["key"] == ""

    repository.save_result(track_id, bpm=127.98, key=MusicalKey(9, True), source_duration_us=1)
    library.set_analysis_display("camelot", 2)
    shown = library.track(track_id)
    assert shown["bpm"] == pytest.approx(127.98) and shown["bpmText"] == "127.98"
    assert shown["key"] == "8A" and shown["keyCamelot"] == "8A"
    library.set_analysis_display("classic", 0)
    switched = library.tracks_in_folder(root["id"], "")[0]
    assert switched["bpmText"] == "128" and switched["key"] == "Am"
    assert switched["keyCamelot"] == "8A"  # the colour stays on the Camelot wheel

    repository.mark_user_edited([track_id], "bpm")
    edited = library.track(track_id)
    assert edited["bpm"] == "" and edited["bpmText"] == ""  # the tag decides once edited


def _write_scanned_tracks(
    database: Database, library: LibraryRepository, root_id: str, base: Path
) -> dict[str, str]:
    """Register readable tracks in a tree through the real scan API."""
    layout = ["top.wav", "sets/a.wav", "sets/deep/b.wav", "sets2/c.wav"]
    generation = library.begin_scan(root_id)
    entries = []
    for relative in layout:
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not real audio, only a catalogued file")
        entries.append((relative, path, SourceRevision.observe(path), MetadataSnapshot()))
    library.upsert_locations(root_id, entries, generation)
    owners = {relative: library.path_owner(base / relative) for relative in layout}
    assert all(owners.values())
    return {relative: str(owner) for relative, owner in owners.items()}

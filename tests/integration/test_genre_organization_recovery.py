"""Genre organization uses copied audio and reconciles interrupted disk/database phases."""

from __future__ import annotations

import json
import os
import threading
import wave
from pathlib import Path

import pytest

from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision, TrackId
from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.plugins.genre_manager.organizer import GenreOrganizer
from mtee.plugins.genre_manager.repository import GenreManagerRepository
from mtee.plugins.genre_manager.sessions import GenreSessionRepository
from mtee.services.file_access import FileAccessCoordinator


@pytest.fixture
def scenario(tmp_path: Path):
    database = Database(tmp_path / "data" / "mtee.sqlite3")
    database.migrate()
    music = tmp_path / "music"
    (music / "Incoming").mkdir(parents=True)
    library = LibraryRepository(database)
    root_id = library.add_root(music)["id"]
    decisions = GenreManagerRepository(database)
    house = decisions.create_genre("House")
    sessions = GenreSessionRepository(database, library, PlaylistsRepository(database))
    access = FileAccessCoordinator()
    organizer = GenreOrganizer(database, library, sessions, access)

    def add(name: str, *, reviewed: bool = True) -> str:
        path = music / "Incoming" / name
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 800)
        generation = library.begin_scan(root_id)
        library.upsert_locations(
            root_id,
            [
                (
                    f"Incoming/{name}",
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(title=(path.stem,), technical=TechnicalInfo(duration_us=100)),
                )
            ],
            generation,
        )
        track_id = library.path_owner(path)
        assert track_id is not None
        decisions.set_genres(track_id, [house], expected_revision=0, operation_id=f"genre-{name}")
        if reviewed:
            decisions.mark_reviewed(track_id, expected_revision=1, operation_id=f"review-{name}")
        return track_id

    yield database, music, root_id, house, library, sessions, organizer, add, access
    database.close()


def test_preview_move_undo_and_unreviewed_stay_in_place(scenario) -> None:
    _, music, root_id, house, library, sessions, organizer, add, _ = scenario
    reviewed = add("Reviewed.wav")
    unreviewed = add("Unreviewed.wav", reviewed=False)
    session = sessions.open_source("folder", "Incoming", root_id=root_id)
    organizer.set_destination(root_id, house, "House")
    preview = organizer.preview(session["session_id"])
    assert (preview["ready"], preview["unreviewed"]) == (1, 1)
    assert preview["rows"][0]["needsFolder"] is True
    assert not (music / "House").exists()
    original_bytes = (music / "Incoming" / "Reviewed.wav").read_bytes()

    result = organizer.apply(preview["operationId"])
    assert (result["status"], result["moved"]) == ("completed", 1)
    assert organizer.latest_undoable(session["session_id"]) == preview["operationId"]
    assert library.source_record(reviewed).path == music / "House" / "Reviewed.wav"
    assert (music / "House" / "Reviewed.wav").read_bytes() == original_bytes
    assert library.source_record(unreviewed).path == music / "Incoming" / "Unreviewed.wav"
    inverse = organizer.prepare_undo(preview["operationId"])
    assert inverse["ready"] == 1
    assert organizer.apply(inverse["operationId"])["moved"] == 1
    assert organizer.latest_undoable(session["session_id"]) == ""
    assert library.source_record(reviewed).path == music / "Incoming" / "Reviewed.wav"
    assert (music / "Incoming" / "Reviewed.wav").read_bytes() == original_bytes


def test_stale_classification_and_collision_are_refused(scenario) -> None:
    _, music, root_id, house, _, sessions, organizer, add, _ = scenario
    track_id = add("One.wav")
    session = sessions.open_source("folder", "Incoming", root_id=root_id)
    organizer.set_destination(root_id, house, "House")
    preview = organizer.preview(session["session_id"])
    (music / "House").mkdir()
    (music / "House" / "One.wav").write_bytes(b"other")
    result = organizer.apply(preview["operationId"])
    assert result["conflicts"] == 1
    assert (music / "Incoming" / "One.wav").exists()
    assert (music / "House" / "One.wav").read_bytes() == b"other"
    (music / "House" / "One.wav").unlink()
    preview = organizer.preview(session["session_id"])
    GenreManagerRepository(scenario[0]).set_genres(
        track_id, [], expected_revision=1, operation_id="remove-genre"
    )
    assert organizer.apply(preview["operationId"])["conflicts"] == 1


def test_recover_disk_moved_before_catalogue_commit(scenario) -> None:
    database, music, root_id, house, library, sessions, organizer, add, _ = scenario
    track_id = add("Interrupted.wav")
    session = sessions.open_source("folder", "Incoming", root_id=root_id)
    organizer.set_destination(root_id, house, "House")
    preview = organizer.preview(session["session_id"])
    source = music / "Incoming" / "Interrupted.wav"
    target = music / "House" / "Interrupted.wav"
    target.parent.mkdir()
    from mtee.domain.tracks import sha256_of_file

    proof = preview["rows"][0]["revision"] | {"sha256": sha256_of_file(source)}
    os.rename(source, target)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE gm_organization_items SET phase='moved',source_revision_json=? "
            "WHERE operation_id=? AND track_id=?",
            (json.dumps(proof), preview["operationId"], track_id),
        )
        connection.execute(
            "UPDATE gm_organization_operations SET status='running' WHERE operation_id=?",
            (preview["operationId"],),
        )
    outcome = organizer.recover()
    assert outcome == [
        {"operationId": preview["operationId"], "trackId": track_id, "status": "completed"}
    ]
    assert library.source_record(track_id).path == target
    assert organizer.recover() == []


def test_eighty_of_one_hundred_tracks_preview_without_mutating_music(scenario) -> None:
    _, music, root_id, house, _, sessions, organizer, add, _ = scenario
    for index in range(100):
        add(f"Batch {index:03d}.wav", reviewed=index < 80)
    session = sessions.open_source("folder", "Incoming", root_id=root_id)
    organizer.set_destination(root_id, house, "House")
    preview = organizer.preview(session["session_id"])
    assert (preview["ready"], preview["unreviewed"]) == (80, 20)
    assert not (music / "House").exists()
    assert len(list((music / "Incoming").glob("*.wav"))) == 100


def test_recover_marks_unstarted_item_for_new_preview(scenario) -> None:
    database, _, root_id, house, _, sessions, organizer, add, _ = scenario
    track_id = add("Pending.wav")
    session = sessions.open_source("folder", "Incoming", root_id=root_id)
    organizer.set_destination(root_id, house, "House")
    preview = organizer.preview(session["session_id"])
    with database.transaction() as connection:
        connection.execute(
            "UPDATE gm_organization_operations SET status='running' WHERE operation_id=?",
            (preview["operationId"],),
        )
    assert organizer.recover() == [
        {
            "operationId": preview["operationId"],
            "trackId": track_id,
            "status": "conflict",
        }
    ]
    row = (
        database.connection()
        .execute(
            "SELECT phase FROM gm_organization_items WHERE operation_id=? AND track_id=?",
            (preview["operationId"], track_id),
        )
        .fetchone()
    )
    assert row[0] == "conflict"


def test_busy_track_is_named_in_preview_and_not_moved(scenario) -> None:
    _, music, root_id, house, _, sessions, organizer, add, access = scenario
    track_id = add("Playing.wav")
    session = sessions.open_source("folder", "Incoming", root_id=root_id)
    organizer.set_destination(root_id, house, "House")
    held = threading.Event()
    release = threading.Event()

    def play() -> None:
        with access.acquire_read(TrackId.parse(track_id), "test playback"):
            held.set()
            release.wait(5)

    thread = threading.Thread(target=play)
    thread.start()
    assert held.wait(5)
    try:
        preview = organizer.preview(session["session_id"])
        assert preview["rows"][0]["status"] == "busy"
        assert preview["ready"] == 0
        assert (music / "Incoming" / "Playing.wav").exists()
    finally:
        release.set()
        thread.join()


def test_playlist_across_roots_plans_each_track_once(scenario) -> None:
    database, music, root_id, house, library, sessions, organizer, add, _ = scenario
    first = add("First.wav")
    second_music = music.parent / "second-music"
    (second_music / "Unsorted").mkdir(parents=True)
    second_path = second_music / "Unsorted" / "Second.wav"
    with wave.open(str(second_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)
    second_root = library.add_root(second_music)["id"]
    generation = library.begin_scan(second_root)
    library.upsert_locations(
        second_root,
        [
            (
                "Unsorted/Second.wav",
                second_path,
                SourceRevision.observe(second_path),
                MetadataSnapshot(title=("Second",), technical=TechnicalInfo(duration_us=100)),
            )
        ],
        generation,
    )
    second = library.path_owner(second_path)
    assert second is not None
    decisions = GenreManagerRepository(database)
    decisions.set_genres(second, [house], expected_revision=0, operation_id="second-genre")
    decisions.mark_reviewed(second, expected_revision=1, operation_id="second-review")
    playlist = PlaylistsRepository(database).create(
        "Mixed roots",
        entries=[{"track_id": identity, "snapshot": {}} for identity in (first, second)],
    )
    session = sessions.open_source("playlist", playlist)
    organizer.set_destination(root_id, house, "Sorted")
    organizer.set_destination(second_root, house, "Sorted")
    preview = organizer.preview(session["session_id"])
    assert preview["ready"] == 2
    assert {row["rootId"] for row in preview["rows"]} == {root_id, second_root}
    assert organizer.apply(preview["operationId"])["moved"] == 2
    assert library.source_record(first).path == music / "Sorted" / "First.wav"
    assert library.source_record(second).path == second_music / "Sorted" / "Second.wav"
    assert [entry["track_id"] for entry in PlaylistsRepository(database).entries(playlist)] == [
        first,
        second,
    ]


def test_cancel_stops_next_file_and_keeps_completed_move_in_journal(scenario) -> None:
    database, music, root_id, house, _, sessions, organizer, add, _ = scenario
    add("First.wav")
    add("Second.wav")
    session = sessions.open_source("folder", "Incoming", root_id=root_id)
    organizer.set_destination(root_id, house, "Sorted")
    preview = organizer.preview(session["session_id"])
    calls = 0

    def cancel_after_first() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    result = organizer.apply(preview["operationId"], should_cancel=cancel_after_first)
    assert (result["status"], result["moved"]) == ("cancelled", 1)
    assert len(list((music / "Sorted").glob("*.wav"))) == 1
    assert len(list((music / "Incoming").glob("*.wav"))) == 1
    phases = [
        str(row[0])
        for row in database.connection().execute(
            "SELECT phase FROM gm_organization_items WHERE operation_id=? ORDER BY ordinal",
            (preview["operationId"],),
        )
    ]
    assert phases == ["completed", "prepared"]
    assert organizer.latest_undoable(session["session_id"]) == preview["operationId"]

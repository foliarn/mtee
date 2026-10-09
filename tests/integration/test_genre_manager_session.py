"""Source sessions retain a stable batch and calculate progress without per-row QML I/O."""

from pathlib import Path

from mtee.persistence.database import Database
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.plugins.genre_manager.repository import GenreManagerRepository
from mtee.plugins.genre_manager.sessions import GenreSessionRepository


def test_folder_and_playlist_sessions_resume_with_progress(tmp_path: Path) -> None:
    database = Database(tmp_path / "session.sqlite3")
    database.migrate()
    root_path = tmp_path / "music"
    library = LibraryRepository(database)
    root_id = library.add_root(root_path)["id"]
    playlist_id = PlaylistsRepository(database).create("Evening")
    with database.transaction() as connection:
        for index, folder in enumerate(("House", "House", "Techno")):
            track_id = f"track-{index}"
            path = root_path / folder / f"Track {index}.wav"
            connection.execute("INSERT INTO tracks(track_id) VALUES(?)", (track_id,))
            connection.execute(
                "INSERT INTO track_locations(path_key,track_id,path,size_bytes,mtime_ns,"
                "status,metadata_json) VALUES(?,?,?,?,?,'readable','{}')",
                (str(path).casefold(), track_id, str(path), 1, 1),
            )
            connection.execute(
                "INSERT INTO root_tracks(root_id,track_id,relative_path,seen_generation) "
                "VALUES(?,?,?,0)",
                (root_id, track_id, f"{folder}/Track {index}.wav"),
            )
            connection.execute(
                "INSERT INTO playlist_entries(entry_id,playlist_id,track_id,ordinal,snapshot_json) "
                "VALUES(?,?,?,?, '{}')",
                (f"entry-{index}", playlist_id, track_id, index),
            )
    decisions = GenreManagerRepository(database)
    house = decisions.create_genre("House")
    decisions.set_genres("track-0", [house], expected_revision=0, operation_id="house")
    decisions.mark_reviewed("track-0", expected_revision=1, operation_id="review")
    sessions = GenreSessionRepository(database, library, PlaylistsRepository(database))

    sources = sessions.source_options()
    house_source = next(
        source for source in sources if source["kind"] == "folder" and source["key"] == "House"
    )
    playlist_source = next(source for source in sources if source["kind"] == "playlist")
    assert (house_source["count"], house_source["completion"]) == (2, 50)
    assert (playlist_source["count"], playlist_source["completion"]) == (3, 33)

    folder = sessions.open_source("folder", "House", root_id=root_id)
    assert [row["id"] for row in sessions.rows(folder["session_id"])] == ["track-0", "track-1"]
    sessions.save_view(
        folder["session_id"],
        view_mode="to_review",
        interaction_mode="brush",
        search_text="Track",
        selected_ids=["track-1"],
        brush_kind="genre",
        brush_id=house,
    )
    assert sessions.open_source("folder", "House", root_id=root_id)["view_mode"] == "to_review"
    assert sessions.latest_session()["session_id"] == folder["session_id"]
    playlist = sessions.open_source("playlist", playlist_id)
    assert len(sessions.rows(playlist["session_id"])) == 3
    database.close()

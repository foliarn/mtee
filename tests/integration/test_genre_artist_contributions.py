"""Genre contributions remain calculated, revocable and separate from profile tags."""

from pathlib import Path

from mtee.persistence.database import Database
from mtee.plugins.genre_manager.artist_attribution import ArtistAttribution
from mtee.plugins.genre_manager.repository import GenreManagerRepository


def test_madonna_remix_contributes_only_to_confirmed_remixer(tmp_path: Path) -> None:
    database = Database(tmp_path / "artist.sqlite3")
    database.migrate()
    with database.transaction() as connection:
        connection.execute("INSERT INTO tracks(track_id) VALUES('track')")
        for identity, name, position, role in (
            ("madonna", "Madonna", 0, "artist"),
            ("producer", "Club Producer", 1, "remixer"),
        ):
            connection.execute(
                "INSERT INTO artists(artist_id,display_name,name_key,"
                "created_at_utc,updated_at_utc) "
                "VALUES(?,?,?,'now','now')",
                (identity, name, name.casefold()),
            )
            connection.execute(
                "INSERT INTO track_artist_credits(track_id,artist_id,position,role,confirmed) "
                "VALUES('track',?,?,?,1)",
                (identity, position, role),
            )
        connection.execute(
            "INSERT INTO track_artist_review(track_id,category,initial_category,"
            "original_artists_json,original_title,proposal_source,proposed_title,"
            "confirmed_title,rules_version,created_at_utc,updated_at_utc) "
            "VALUES('track','from_tags','from_tags','[]','Song','test','Song',"
            "'Song (Club Producer Remix)',1,'now','now')"
        )
    repository = GenreManagerRepository(database)
    ukg = repository.create_genre("UK Garage")
    tag = repository.create_tag("banger")
    repository.set_genres("track", [ukg], expected_revision=0, operation_id="genre")
    repository.set_tag("track", tag, present=True, expected_revision=0, operation_id="tag")
    repository.mark_reviewed("track", expected_revision=1, operation_id="review")
    attribution = ArtistAttribution(database)
    attribution.refresh()
    assert attribution.artist_genres("madonna") == []
    assert attribution.artist_genres("producer")[0]["name"] == "UK Garage"
    assert attribution.uncertainties() == []
    repository.set_genres("track", [], expected_revision=1, operation_id="clear")
    attribution.refresh(["track"])
    assert attribution.artist_genres("producer") == []
    database.close()


def test_unmarked_track_waits_for_choice_then_invalidates_on_credit_change(tmp_path: Path) -> None:
    database = Database(tmp_path / "uncertain.sqlite3")
    database.migrate()
    with database.transaction() as connection:
        connection.execute("INSERT INTO tracks(track_id) VALUES('track')")
        connection.execute(
            "INSERT INTO artists(artist_id,display_name,name_key,created_at_utc,updated_at_utc) "
            "VALUES('artist','Singer','singer','now','now')"
        )
        connection.execute(
            "INSERT INTO track_artist_credits(track_id,artist_id,position,role,confirmed) "
            "VALUES('track','artist',0,'artist',1)"
        )
        connection.execute(
            "INSERT INTO track_artist_review(track_id,category,initial_category,"
            "original_artists_json,original_title,proposal_source,proposed_title,"
            "confirmed_title,rules_version,created_at_utc,updated_at_utc) "
            "VALUES('track','from_tags','from_tags','[]','Song','test','Song','Song',1,'now','now')"
        )
    repository = GenreManagerRepository(database)
    genre = repository.create_genre("House")
    repository.set_genres("track", [genre], expected_revision=0, operation_id="genre")
    repository.mark_reviewed("track", expected_revision=1, operation_id="review")
    attribution = ArtistAttribution(database)
    attribution.refresh()
    assert attribution.uncertainties()[0]["trackId"] == "track"
    attribution.choose("track", ["artist"])
    assert attribution.artist_genres("artist")[0]["sources"] == ["manual"]
    with database.transaction() as connection:
        connection.execute("UPDATE artists SET display_name='Singer New' WHERE artist_id='artist'")
    attribution.refresh()
    assert attribution.artist_genres("artist") == []
    assert "changed" in attribution.uncertainties()[0]["reason"]
    database.close()

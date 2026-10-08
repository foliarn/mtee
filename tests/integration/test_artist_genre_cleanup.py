import json

import pytest
from tests.unit.test_folder_genres import _Library

from mtee.domain.genres import GenreError
from mtee.services.artist_genre_cleanup_service import ArtistGenreCleanupService


def test_cleanup_preserves_manual_roles_hidden_links_and_targeted_undo(tmp_path):
    library = _Library(tmp_path)
    library.add("house/a.wav", ["Alpha", "Beta", "Manual"])
    repo = library.repository
    alpha = library.artist("Alpha")
    beta = library.artist("Beta")
    manual = library.artist("Manual")
    repo.save_artist_profile(
        alpha, roles=["producer"], bass_related=False, tags=["Favourite"], hidden=True
    )
    repo.save_artist_profile(manual, roles=[], bass_related=None, tags=["House"], hidden=False)
    witness = library.database.backup_to(tmp_path / "witness.sqlite3")
    for identity in (alpha, beta, manual):
        repo.set_folder_genres(identity, {"House": 1})
    connection = library.database.connection()
    saved = json.loads(
        connection.execute(
            "SELECT record_json FROM artist_enrichment_reviews WHERE artist_id=?", (alpha,)
        ).fetchone()[0]
    )["saved_at"]
    # A later manual addition makes this row ambiguous.
    repo.save_artist_profile(
        beta, roles=[], bass_related=None, tags=["House", "Personal"], hidden=False
    )
    service = ArtistGenreCleanupService(library.database.path)
    plan = service.preview(witness, saved, saved)
    assert plan["summary"] == {"artists": 1, "tags": 1, "ambiguous": 1}
    before = [
        dict(r)
        for r in connection.execute("SELECT * FROM artist_enrichment_reviews ORDER BY artist_id")
    ]
    receipt = service.apply(plan)
    assert receipt["backup"]
    assert repo.artist_profile(alpha).hidden
    assert repo.artist_profile(alpha).tags == ["Favourite"]
    assert repo.artist_profile(alpha).roles == ["Producer"]
    assert repo.artist_profile(manual).tags == ["House"]
    assert repo.artist_profile(beta).tags == ["House", "Personal"]
    service.undo(receipt["operation"])
    assert [
        dict(r)
        for r in connection.execute("SELECT * FROM artist_enrichment_reviews ORDER BY artist_id")
    ] == before
    assert not service.preview()["rows"]
    library.database.close()


def test_cleanup_stale_and_undo_conflicts_refuse_entire_operation(tmp_path):
    library = _Library(tmp_path)
    library.add("house/a.wav", ["Alpha"])
    repo = library.repository
    identity = library.artist("Alpha")
    repo.save_artist_profile(identity, roles=[], bass_related=None, tags=[], hidden=False)
    witness = library.database.backup_to(tmp_path / "witness.sqlite3")
    repo.set_folder_genres(identity, {"House": 1})
    saved = json.loads(
        library.database.connection()
        .execute("SELECT record_json FROM artist_enrichment_reviews")
        .fetchone()[0]
    )["saved_at"]
    service = ArtistGenreCleanupService(library.database.path)
    plan = service.preview(witness, saved, saved)
    receipt = service.apply(plan)
    with pytest.raises(GenreError, match="stale"):
        service.apply(plan)
    repo.save_artist_profile(identity, roles=[], bass_related=None, tags=["Later"], hidden=False)
    with pytest.raises(GenreError, match="conflict"):
        service.undo(receipt["operation"])
    assert repo.artist_profile(identity).tags == ["Later"]
    library.database.close()

"""Roles, tags and hidden state of the artists: storage, catalog filters, migration."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any, cast

import pytest

from mtee.domain.artist_profile import normalize_roles, normalize_tags
from mtee.domain.metadata import MetadataSnapshot, TechnicalInfo
from mtee.domain.tracks import SourceRevision
from mtee.models.artist_manager_model import ArtistListModel, ArtistManagerModel
from mtee.persistence.artist_repository import ArtistRepository
from mtee.persistence.database import Database, split_statements
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.artist_identification_service import ArtistIdentificationService
from mtee.services.artist_manager_service import ArtistManagerError, ArtistManagerService
from mtee.services.jobs import JobService


class _Setup:
    def __init__(self, base: Path) -> None:
        self.music = base / "music"
        self.music.mkdir(parents=True)
        self.database = Database(base / "data" / "mtee.sqlite3")
        self.database.migrate()
        self.library = LibraryRepository(self.database)
        self.root_id = self.library.add_root(self.music)["id"]
        self.repository = ArtistRepository(self.database)
        self.identification = ArtistIdentificationService(self.library, self.repository)

    def add_track(self, name: str, artists: list[str]) -> str:
        path = self.music / name
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 800)
        generation = self.library.begin_scan(self.root_id)
        self.library.upsert_locations(
            self.root_id,
            [
                (
                    name,
                    path,
                    SourceRevision.observe(path),
                    MetadataSnapshot(title=(path.stem,), technical=TechnicalInfo(duration_us=100)),
                )
            ],
            generation,
        )
        owner = self.library.path_owner(path)
        assert owner is not None
        self.identification.sync_tags(owner, artists, None)
        return owner

    def artist(self, name: str) -> dict[str, Any]:
        return next(item for item in self.repository.catalog() if item["name"] == name)


@pytest.fixture
def setup(tmp_path: Path):
    value = _Setup(tmp_path)
    value.add_track("a.wav", ["Hedex", "Bou"])
    value.add_track("b.wav", ["Hedex"])
    value.add_track("c.wav", ["Nia"])
    yield value
    value.database.close()


def test_roles_and_tags_are_normalized() -> None:
    assert normalize_roles(["producer", "DJ", "Rapper", "dj"]) == ["DJ", "Producer"]
    assert normalize_tags(["  Bass  house ", "bass house", "IDGAF", "", "x" * 80]) == [
        "Bass house",
        "x" * 40,
    ]


def test_an_artist_without_a_profile_has_no_type_and_is_visible(setup: _Setup) -> None:
    hedex = setup.artist("Hedex")
    assert hedex["tracks"] == 2
    assert hedex["roles"] == []
    assert hedex["tags"] == []
    assert hedex["hidden"] is False
    assert hedex["bassRelated"] is None


def test_saving_a_profile_creates_the_row_and_the_catalog_shows_it(setup: _Setup) -> None:
    hedex = setup.artist("Hedex")["id"]
    setup.repository.save_artist_profile(
        hedex, roles=["Producer", "DJ"], bass_related=True, tags=["Dnb"], hidden=False
    )
    shown = setup.artist("Hedex")
    assert shown["roles"] == ["DJ", "Producer"]
    assert shown["bassRelated"] is True
    assert shown["tags"] == ["Dnb"]
    row = (
        setup.database.connection()
        .execute("SELECT * FROM artist_enrichment_reviews WHERE artist_id=?", (hedex,))
        .fetchone()
    )
    assert row["decision"] == "keep"
    assert json.loads(row["roles_json"]) == ["DJ", "Producer"]
    assert json.loads(row["record_json"])["roles"] == ["DJ", "Producer"]


def test_idgaf_and_the_exclude_decision_change_together(setup: _Setup) -> None:
    bou = setup.artist("Bou")["id"]
    setup.repository.save_artist_profile(
        bou, roles=["MC"], bass_related=None, tags=["live"], hidden=True
    )
    hidden = setup.artist("Bou")
    assert hidden["hidden"] is True
    assert hidden["tags"] == ["live"]  # idgaf is the hidden state, not a free tag
    connection = setup.database.connection()
    row = connection.execute(
        "SELECT decision, tags_json FROM artist_enrichment_reviews WHERE artist_id=?", (bou,)
    ).fetchone()
    assert row["decision"] == "exclude"
    assert json.loads(row["tags_json"]) == ["idgaf", "live"]

    setup.repository.save_artist_profile(
        bou, roles=["MC"], bass_related=None, tags=["live"], hidden=False
    )
    row = connection.execute(
        "SELECT decision, tags_json FROM artist_enrichment_reviews WHERE artist_id=?", (bou,)
    ).fetchone()
    assert (row["decision"], json.loads(row["tags_json"])) == ("keep", ["live"])
    assert setup.artist("Bou")["hidden"] is False


def test_an_excluded_artist_without_the_tag_is_still_hidden(setup: _Setup) -> None:
    nia = setup.artist("Nia")["id"]
    setup.repository.save_artist_profile(nia, roles=[], bass_related=None, tags=[], hidden=False)
    setup.database.connection().execute(
        "UPDATE artist_enrichment_reviews SET decision='exclude' WHERE artist_id=?", (nia,)
    )
    assert setup.artist("Nia")["hidden"] is True


def test_editing_keeps_links_notes_other_decisions_and_the_observations(setup: _Setup) -> None:
    hedex = setup.artist("Hedex")["id"]
    connection = setup.database.connection()
    connection.execute(
        "INSERT INTO artist_enrichment_reviews VALUES(?, 'uncertain', '[\"DJ\"]', 1, "
        "'https://open.spotify.com/artist/x', 'https://soundcloud.com/x', '[]', 'my note', "
        "'accepted', '2026-10-06T00:00:00+00:00', '{\"decision\": \"uncertain\", "
        '"extra": 7}\', \'{"source": "web"}\')',
        (hedex,),
    )
    connection.commit()
    setup.repository.save_artist_profile(
        hedex, roles=["DJ", "Singer"], bass_related=False, tags=["a"], hidden=False
    )
    row = connection.execute(
        "SELECT * FROM artist_enrichment_reviews WHERE artist_id=?", (hedex,)
    ).fetchone()
    assert row["decision"] == "uncertain"
    assert row["spotify_url"] == "https://open.spotify.com/artist/x"
    assert row["soundcloud_url"] == "https://soundcloud.com/x"
    assert row["notes"] == "my note"
    assert row["observation_json"] == '{"source": "web"}'
    assert row["bass_related"] == 0
    assert json.loads(row["record_json"])["extra"] == 7


def test_an_unknown_artist_is_refused(setup: _Setup) -> None:
    with pytest.raises(ValueError):
        setup.repository.save_artist_profile(
            "missing", roles=[], bass_related=None, tags=[], hidden=False
        )


def test_migration_adopts_a_table_created_by_the_review_tool(tmp_path: Path) -> None:
    database = Database(tmp_path / "old.sqlite3")
    database.migrate()
    connection = database.connection()
    connection.execute("DROP TABLE artist_enrichment_reviews")
    connection.execute("DROP TABLE artist_enrichment_schema")
    tool = Path(__file__).resolve().parents[2] / "scripts/artist-review-migrations"
    for statement in split_statements((tool / "001_artist_enrichment.sql").read_text("utf-8")):
        connection.execute(statement)
    connection.execute("INSERT INTO artist_enrichment_schema VALUES (1, 'then')")
    connection.execute("INSERT INTO artists VALUES ('a','A','a','auto','established',NULL,'t','t')")
    connection.execute(
        "INSERT INTO artist_enrichment_reviews VALUES('a','keep','[\"MC\"]',1,'','','[]','',"
        "'accepted','t','{}','{}')"
    )
    connection.commit()
    sql = next(migration.read_sql() for migration in database.migrations if migration.version == 20)
    for statement in split_statements(sql):
        connection.execute(statement)
    assert connection.execute("SELECT COUNT(*) FROM artist_enrichment_reviews").fetchone()[0] == 1
    stamps = connection.execute("SELECT applied_at_utc FROM artist_enrichment_schema").fetchall()
    assert [row[0] for row in stamps] == ["then"]
    database.close()


@pytest.fixture
def manager(qapp, setup: _Setup):
    service = ArtistManagerService(setup.repository, cast(Any, None))
    model = ArtistManagerModel(service, JobService(qapp, max_thread_count=1))
    yield model
    model.deleteLater()


def _catalog(manager: ArtistManagerModel, setup: _Setup, key: str) -> ArtistListModel:
    model = ArtistListModel(manager, key)
    model.accept(model._generation, setup.repository.catalog())
    return model


def _name_of(model: ArtistListModel, row: int) -> str:
    role = next(r for r, n in model._role_names.items() if n == "name")
    return str(model.data(model.index(row), role))


def _list(model: ArtistListModel) -> list[str]:
    return [_name_of(model, row) for row in range(model.rowCount())]


def test_the_catalog_filters_by_type_with_or_and_by_track_count(
    manager: ArtistManagerModel, setup: _Setup
) -> None:
    save = setup.repository.save_artist_profile
    save(
        setup.artist("Hedex")["id"],
        roles=["Producer", "DJ"],
        bass_related=None,
        tags=[],
        hidden=False,
    )
    save(setup.artist("Bou")["id"], roles=["MC"], bass_related=None, tags=[], hidden=False)
    catalog = _catalog(manager, setup, "catalog")
    assert _list(catalog) == ["Bou", "Hedex", "Nia"]

    catalog.toggleType("MC")
    assert _list(catalog) == ["Bou"]
    catalog.toggleType("Producer")  # OR
    assert _list(catalog) == ["Bou", "Hedex"]
    catalog.toggleType("MC")
    catalog.toggleType("Producer")
    catalog.toggleType("No role")
    assert _list(catalog) == ["Nia"]
    catalog.clearFilters()
    catalog.setMinTracks(2)
    assert _list(catalog) == ["Hedex"]
    catalog.setSearch("hed")
    assert _list(catalog) == ["Hedex"]
    catalog.setMinTracks(3)
    assert _list(catalog) == []


def test_hidden_artists_appear_only_when_asked(manager: ArtistManagerModel, setup: _Setup) -> None:
    setup.repository.save_artist_profile(
        setup.artist("Nia")["id"], roles=["Singer"], bass_related=None, tags=[], hidden=True
    )
    everyone = _catalog(manager, setup, "catalog.all")
    singers = _catalog(manager, setup, "catalog.Singer")
    assert _list(everyone) == ["Bou", "Hedex"]
    assert _list(singers) == []
    manager.setShowHidden(True)
    assert _list(everyone) == ["Bou", "Hedex", "Nia"]
    assert _list(singers) == ["Nia"]
    manager.setShowHidden(False)
    assert _list(singers) == []


def test_saving_through_the_model_refreshes_and_reports_errors(
    manager: ArtistManagerModel, setup: _Setup
) -> None:
    changed: list[str] = []
    manager.artistProfileChanged.connect(changed.append)
    hedex = setup.artist("Hedex")["id"]
    outcome = manager.saveArtistProfile(hedex, ["DJ"], 1, ["x"], False)
    assert outcome == {"ok": True, "error": ""}
    assert changed == [hedex]
    assert manager.artistProfile(hedex)["roles"] == ["DJ"]
    assert manager.artistProfile(hedex)["bassRelated"] is True
    assert manager.setArtistHidden(hedex, True)["ok"] is True
    profile = manager.artistProfile(hedex)
    assert profile["hidden"] is True and profile["roles"] == ["DJ"] and profile["tags"] == ["x"]
    assert manager.saveArtistProfile("missing", [], -1, [], False)["ok"] is False
    with pytest.raises(ArtistManagerError):
        ArtistManagerService(setup.repository, cast(Any, None)).save_artist_profile(
            "missing", roles=[], bass_related=None, tags=[], hidden=False
        )

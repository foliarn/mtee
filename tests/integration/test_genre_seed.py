"""Seeds only fixtures or coherent copies; source bytes and decisions are preserved."""

import copy
import hashlib
import json
import shutil
import sqlite3
import wave
from pathlib import Path

import pytest

from mtee.domain.genres import GenreError, initial_taxonomy
from mtee.domain.metadata import MetadataSnapshot
from mtee.domain.tracks import SourceRevision
from mtee.persistence.database import Database
from mtee.persistence.genre_repository import GenreRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.genre_seed_service import GenreSeedService, readonly, verified_copy


def fixture_library(base: Path, *, old: bool = False) -> tuple[Path, str, list[str]]:
    base.mkdir(parents=True, exist_ok=True)
    path = base / "data" / "mtee.sqlite3"
    migrations = None
    if old:
        migrations = base / "old-migrations"
        migrations.mkdir()
        for migration in Database(base / "unused.sqlite3").migrations:
            if migration.version <= 20:
                shutil.copyfile(migration.path, migrations / migration.file_name)
    database = Database(path, migrations_dir=migrations)
    database.migrate()
    library = LibraryRepository(database)
    music = base / "music"
    music.mkdir()
    root = library.add_root(music)["id"]
    generation = library.begin_scan(root)
    cases = [
        ("d&b/jump up", None),
        ("house", None),
        ("house", None),
        ("hard,rawstyle", None),
        ("breaks - jungle", 87),
        ("breaks - jungle", 159),
        ("breaks - jungle", 160),
        ("breaks - jungle", None),
        ("Artists/Nobody/Album", None),
        ("unknown", None),
    ]
    ids = []
    for index, (folder, bpm) in enumerate(cases):
        relative = f"{folder}/{index}.wav"
        audio = music / relative
        audio.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(audio), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b"\x00\x00" * 800)
        library.upsert_location(
            root,
            relative,
            audio,
            SourceRevision.observe(audio),
            MetadataSnapshot(title=(f"Song {index}",), genre=("File genre",), bpm=123),
            generation,
        )
        identity = library.path_owner(audio)
        assert identity
        ids.append(identity)
        if bpm is not None:
            database.connection().execute(
                "INSERT INTO track_analysis(track_id,bpm) VALUES(?,?)", (identity, bpm)
            )
    database.connection().execute("UPDATE root_tracks SET present=0 WHERE track_id=?", (ids[-1],))
    if not old:
        GenreRepository(database).initialize()
    database.close()
    return path, root, ids


def genre_id(path: str) -> str:
    tree = initial_taxonomy()
    return next(node.genre_id for node in tree.nodes.values() if tree.path(node.genre_id) == path)


@pytest.mark.parametrize("old", [True, False])
def test_preview_apply_restart_idempotence_and_audio_unchanged(tmp_path: Path, old: bool) -> None:
    path, root, ids = fixture_library(tmp_path, old=old)
    source = hashlib.sha256(path.read_bytes()).hexdigest()
    audio_hashes = {
        p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path / "music").rglob("*.wav")
    }
    service = GenreSeedService(path)
    plan = service.preview(root)
    assert source == hashlib.sha256(path.read_bytes()).hexdigest()
    assert plan["summary"]["present"] == 9
    assert plan["summary"]["assigned_tracks"] == 7
    assert plan["summary"]["assignments"] == 9
    assert plan["summary"]["hybrids"] == 1
    assert plan["summary"].get("family:Techno", 0) == 0
    assert plan["summary"]["without_genre"] == 2
    service.write_report(plan, tmp_path / "reports")
    plan = json.loads((tmp_path / "reports" / "plan.json").read_text(encoding="utf-8"))
    receipt = service.apply(plan)
    with readonly(Path(receipt["backup"])) as saved:
        assert saved.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert saved.execute("PRAGMA user_version").fetchone()[0] == (20 if old else 21)
    database = Database(path)
    repository = GenreRepository(database)
    data = repository.track_assignments(ids)
    assert data[ids[0]]["mteeGenres"] == ["Drum & Bass \u203a Jump Up"]
    assert data[ids[0]]["genreFamilies"] == ["Drum & Bass"]
    assert data[ids[1]]["mteeGenres"] == ["House"]
    assert data[ids[6]]["mteeGenres"] == ["Drum & Bass \u203a Jungle"]
    assert data[ids[7]]["mteeGenres"] == []
    metadata = database.connection().execute("SELECT metadata_json FROM track_locations").fetchall()
    assert all(json.loads(row[0])["genre"] == ["File genre"] for row in metadata)
    assert service.apply(plan)["already_applied"] == "true"
    refreshed = service.preview(root)
    assert refreshed["summary"]["preserved"] == 9
    assert refreshed["summary"]["absent"] == 1
    assert service.apply(refreshed)["already_applied"] == "true"
    database.close()
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in audio_hashes} == audio_hashes


def test_stale_or_tampered_or_other_database_plan_cannot_write(tmp_path: Path) -> None:
    path, root, ids = fixture_library(tmp_path / "first")
    service = GenreSeedService(path)
    plan = service.preview(root)
    altered = copy.deepcopy(plan)
    altered["rows"][0]["genres"] = [genre_id("House")]
    with pytest.raises(GenreError, match="stale"):
        service.apply(altered)
    duplicate = tmp_path / "other.sqlite3"
    verified_copy(path, duplicate)
    with pytest.raises(GenreError, match="stale"):
        GenreSeedService(duplicate).apply(plan)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE track_analysis SET bpm=161 WHERE track_id=?", (ids[5],))
    with pytest.raises(GenreError, match="stale"):
        service.apply(plan)
    with readonly(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM track_genres").fetchone()[0] == 0


def test_manual_removal_is_durable_and_seed_undo_refuses_conflicts(tmp_path: Path) -> None:
    path, root, ids = fixture_library(tmp_path)
    service = GenreSeedService(path)
    plan = service.preview(root)
    receipt = service.apply(plan)
    database = Database(path)
    repository = GenreRepository(database)
    repository.change_membership([ids[1]], [genre_id("House")], enabled=False)
    assert repository.track_assignments([ids[1]])[ids[1]]["mteeGenres"] == []
    with pytest.raises(GenreError, match="Undo conflict"):
        service.undo(receipt["operation_id"])
    assert service.preview(root)["summary"]["preserved"] == 9
    service.apply(plan)
    assert repository.track_assignments([ids[1]])[ids[1]]["mteeGenres"] == []
    database.close()


def test_cancellation_rolls_back_entire_seed_and_recovery_is_targeted(tmp_path: Path) -> None:
    path, root, _ids = fixture_library(tmp_path)
    service = GenreSeedService(path)
    calls = 0

    def cancel() -> None:
        nonlocal calls
        calls += 1
        if calls == 5:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        service.apply(service.preview(root), cancel=cancel)
    with readonly(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM track_genres").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM genre_operations").fetchone()[0] == 0
    receipt = service.apply(service.preview(root))
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO settings VALUES('unrelated','kept','now')")
    service.undo(receipt["operation_id"])
    with readonly(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM track_genres").fetchone()[0] == 0
        assert (
            connection.execute("SELECT value FROM settings WHERE key='unrelated'").fetchone()[0]
            == "kept"
        )
        assert connection.execute("SELECT COUNT(*) FROM genre_seed_tracks").fetchone()[0] == 9
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM genre_track_state WHERE manual_edit=1"
            ).fetchone()[0]
            == 0
        )
    assert service.preview(root)["summary"]["assigned_tracks"] == 7


def test_missing_analysis_and_overlapping_mapping_are_reported(tmp_path: Path) -> None:
    path, root, ids = fixture_library(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO track_analysis(track_id,bpm) VALUES(?,?)", (ids[7], float("inf"))
        )
    service = GenreSeedService(path)
    plan = service.preview(root)
    assert plan["summary"]["missing_bpm"] == 1
    service.write_report(plan, tmp_path / "report")  # Strict JSON even for non-finite observed BPM.
    mapping = copy.deepcopy(service.mapping)
    mapping["rules"].append({"folder": "d&b", "scope": "subtree", "genres": []})
    conflicting = GenreSeedService(path, mapping=mapping)
    preview = conflicting.preview(root)
    assert preview["summary"]["mapping_conflict"] == 1
    with pytest.raises(GenreError, match="conflicts"):
        conflicting.apply(preview)


def test_reports_and_backups_refuse_the_collection_and_overwrites(tmp_path: Path) -> None:
    path, root, _ = fixture_library(tmp_path)
    service = GenreSeedService(path)
    with pytest.raises(GenreError, match="protected"):
        service.write_report(service.preview(root), tmp_path / "music" / "report")
    with pytest.raises(GenreError, match="protected"):
        verified_copy(path, tmp_path / "music" / "backup.sqlite3")
    target = tmp_path / "copy.sqlite3"
    verified_copy(path, target)
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        verified_copy(path, target)
    assert target.read_bytes() == before


def test_user_excluded_techno_folders_remain_unassigned(tmp_path: Path) -> None:
    path, root, ids = fixture_library(tmp_path)
    with sqlite3.connect(path) as connection:
        for identity, folder in zip(
            ids[:2], ["hard house - nu trance - bouncy stuff", "techno, trance"], strict=True
        ):
            connection.execute(
                "UPDATE root_tracks SET relative_path=? WHERE track_id=?",
                (folder + "/sample.wav", identity),
            )
    service = GenreSeedService(path)
    preview = service.preview(root)
    targets = [row for row in preview["rows"] if row["track_id"] in ids[:2]]
    assert all(row["reason"] == "excluded" and row["genres"] == [] for row in targets)
    service.apply(preview)
    with readonly(path) as connection:
        for identity in ids[:2]:
            assert not connection.execute(
                "SELECT 1 FROM track_genres WHERE track_id=?", (identity,)
            ).fetchone()


def test_failed_backup_prevents_migration_and_assignments(tmp_path: Path, monkeypatch) -> None:
    path, root, _ = fixture_library(tmp_path, old=True)
    service = GenreSeedService(path)

    def fail_backup(*args):
        raise OSError("backup unavailable")

    monkeypatch.setattr("mtee.services.genre_seed_service.verified_copy", fail_backup)
    with pytest.raises(OSError, match="backup unavailable"):
        service.apply(service.preview(root))
    with readonly(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 20
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='track_genres'"
        ).fetchone()

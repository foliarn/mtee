"""Scanning a root against the database, and hashing the pending items."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from mutagen import File as MutagenFile  # pyright: ignore[reportMissingTypeStubs]
from starlette.applications import Starlette

from conftest import MakeUser
from helpers import make_audio
from mtee_remote import clock
from mtee_remote.config import Settings
from mtee_remote.db import Database
from mtee_remote.ids import new_id
from mtee_remote.library import hashing, scanner, store


@dataclass
class Lib:
    db: Database
    settings: Settings
    user_id: str
    root_id: str
    folder: Path

    def scan(self) -> scanner.ScanResult:
        return scanner.scan_root(self.db, self.settings, self.root_id)

    def kinds(self) -> list[str]:
        rows = self.db.conn().execute(
            "SELECT kind FROM journal WHERE user_id = ? ORDER BY seq", (self.user_id,)
        )
        return [row["kind"] for row in rows]

    def payloads(self, kind: str) -> list[dict[str, Any]]:
        rows = self.db.conn().execute(
            "SELECT payload_json FROM journal WHERE user_id = ? AND kind = ? ORDER BY seq",
            (self.user_id, kind),
        )
        return [json.loads(row["payload_json"]) for row in rows]

    def item(self, relative_path: str) -> Any:
        return (
            self.db.conn()
            .execute(
                "SELECT * FROM items WHERE root_id = ? AND relative_path = ?",
                (self.root_id, relative_path),
            )
            .fetchone()
        )

    def paths(self) -> list[str]:
        rows = self.db.conn().execute(
            "SELECT relative_path FROM items WHERE root_id = ? AND state = 'present'"
            " ORDER BY relative_path",
            (self.root_id,),
        )
        return [row[0] for row in rows]


def add_root(app: Starlette, user: dict[str, Any], name: str = "lib") -> tuple[str, Path]:
    settings: Settings = app.state.settings
    folder = settings.music_dir / user["library_dir"] / name
    folder.mkdir(parents=True, exist_ok=True)
    root_id = new_id()
    with app.state.db.transaction() as tx:
        tx.conn.execute(
            "INSERT INTO roots(root_id, user_id, name, relative_dir, adopted, created_at_utc)"
            " VALUES (?,?,?,?,1,?)",
            (root_id, user["user_id"], name, name, clock.to_iso(clock.utc_now())),
        )
    return root_id, folder


@pytest.fixture
def lib(app: Starlette, make_user: MakeUser) -> Lib:
    user = make_user(app)
    root_id, folder = add_root(app, user)
    return Lib(app.state.db, app.state.settings, user["user_id"], root_id, folder)


def snapshot(folder: Path) -> dict[str, tuple[int, int, str]]:
    """Every file under `folder` with its size, mtime and SHA-256."""
    return {
        path.relative_to(folder).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashing.file_sha256(path),
        )
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def test_scan_adds_audio_files_and_skips_the_rest(lib: Lib) -> None:
    for fmt in ("flac", "mp3", "m4a", "wav", "ogg", "opus", "aiff"):
        make_audio(lib.folder / "rock" / f"song.{fmt}", fmt)
    make_audio(lib.folder / "UPPER.FLAC", "flac")
    (lib.folder / "notes.txt").write_text("x")
    (lib.folder / "cover.jpg").write_bytes(b"x")
    make_audio(lib.folder / ".hidden.flac", "flac")
    make_audio(lib.folder / ".hidden-dir" / "a.flac", "flac")
    result = lib.scan()
    assert result == scanner.ScanResult(added=8, changed=0, moved=0, removed=0, unchanged=0)
    assert lib.paths() == [
        "UPPER.FLAC",
        "rock/song.aiff",
        "rock/song.flac",
        "rock/song.m4a",
        "rock/song.mp3",
        "rock/song.ogg",
        "rock/song.opus",
        "rock/song.wav",
    ]
    row = lib.item("rock/song.flac")
    assert row["hash_state"] == "pending"
    assert row["revision"] == 1
    assert row["size_bytes"] == (lib.folder / "rock" / "song.flac").stat().st_size
    assert row["sha256"] is None
    assert lib.kinds() == ["added"] * 8


def test_scan_skips_symlinked_folders(lib: Lib, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    make_audio(outside / "elsewhere.flac", "flac")
    make_audio(lib.folder / "real.flac", "flac")
    try:
        (lib.folder / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    assert lib.scan().added == 1
    assert lib.paths() == ["real.flac"]


def test_scan_keeps_the_disk_spelling_of_nfd_names(lib: Lib) -> None:
    name = unicodedata.normalize("NFD", "café.flac")
    make_audio(lib.folder / name, "flac")
    lib.scan()
    assert lib.paths() == [name]
    assert (lib.folder / lib.paths()[0]).is_file()
    assert scanner.hash_pending(lib.db, lib.settings) == 1
    assert lib.item(name)["hash_state"] == "done"


def test_rescan_without_changes_does_nothing(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    make_audio(lib.folder / "b.mp3", "mp3")
    lib.scan()
    journal_before = lib.kinds()
    result = lib.scan()
    assert result == scanner.ScanResult(unchanged=2)
    assert lib.kinds() == journal_before


def test_scan_sees_a_tag_change_as_a_new_revision(lib: Lib) -> None:
    path = make_audio(lib.folder / "a.flac", "flac", title="Before")
    lib.scan()
    item_id = lib.item("a.flac")["item_id"]
    audio = MutagenFile(path, easy=True)
    assert audio is not None
    audio["title"] = ["A much longer title than before"]
    audio.save()
    result = lib.scan()
    assert result == scanner.ScanResult(changed=1)
    row = lib.item("a.flac")
    assert (row["item_id"], row["revision"], row["hash_state"]) == (item_id, 2, "pending")
    assert row["size_bytes"] == path.stat().st_size
    assert lib.kinds() == ["added", "replaced"]
    assert lib.payloads("replaced")[0]["revision"] == 2


def test_scan_sees_a_hand_rename_as_a_move(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    lib.scan()
    item_id = lib.item("a.flac")["item_id"]
    (lib.folder / "new").mkdir()
    os.rename(lib.folder / "a.flac", lib.folder / "new" / "renamed.flac")
    result = lib.scan()
    assert result == scanner.ScanResult(moved=1)
    assert lib.paths() == ["new/renamed.flac"]
    assert lib.item("new/renamed.flac")["item_id"] == item_id
    assert lib.item("new/renamed.flac")["revision"] == 1
    assert lib.kinds() == ["added", "moved"]
    assert lib.payloads("moved") == [{"from": "a.flac", "to": "new/renamed.flac"}]


def test_a_rename_with_other_content_also_counts_as_changed(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    lib.scan()
    item_id = lib.item("a.flac")["item_id"]
    os.rename(lib.folder / "a.flac", lib.folder / "b.flac")
    stat = (lib.folder / "b.flac").stat()
    os.utime(lib.folder / "b.flac", ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert lib.scan() == scanner.ScanResult(moved=1)
    row = lib.item("b.flac")
    assert (row["item_id"], row["revision"]) == (item_id, 2)
    assert lib.kinds() == ["added", "moved", "replaced"]


def test_scan_sees_a_hand_delete(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    make_audio(lib.folder / "b.flac", "flac")
    lib.scan()
    item_id = lib.item("a.flac")["item_id"]
    (lib.folder / "a.flac").unlink()
    result = lib.scan()
    assert result == scanner.ScanResult(removed=1, unchanged=1)
    assert lib.paths() == ["b.flac"]
    assert lib.kinds() == ["added", "added", "purged"]
    assert lib.payloads("purged") == [{"relative_path": "a.flac", "reason": "missing"}]
    gone = lib.db.conn().execute("SELECT 1 FROM items WHERE item_id = ?", (item_id,)).fetchone()
    assert gone is None


def test_a_copy_is_a_new_item_not_a_move(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    lib.scan()
    shutil.copyfile(lib.folder / "a.flac", lib.folder / "copy.flac")
    assert lib.scan() == scanner.ScanResult(added=1, unchanged=1)


def test_scan_applies_changes_in_batches(lib: Lib) -> None:
    count = scanner.BATCH_SIZE * 2 + 50
    for number in range(count):
        (lib.folder / f"f{number:04d}.mp3").write_bytes(b"x" * (number + 1))
    assert lib.scan().added == count
    assert len(lib.paths()) == count
    assert lib.scan() == scanner.ScanResult(unchanged=count)


def test_scan_skips_a_file_a_concurrent_writer_took(
    lib: Lib, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("a.mp3", "b.mp3", "c.mp3"):
        (lib.folder / name).write_bytes(b"x")
    real = store.insert_item

    def flaky(tx: Any, **kwargs: Any) -> str:
        if kwargs["relative_path"] == "b.mp3":
            raise sqlite3.IntegrityError("UNIQUE constraint failed")
        return real(tx, **kwargs)

    monkeypatch.setattr(store, "insert_item", flaky)
    assert lib.scan().added == 2
    assert lib.paths() == ["a.mp3", "c.mp3"]


def test_scan_of_a_missing_folder_keeps_the_items(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    lib.scan()
    shutil.rmtree(lib.folder)
    with pytest.raises(FileNotFoundError):
        lib.scan()
    assert lib.paths() == ["a.flac"]


def test_scan_never_touches_the_music_folder(lib: Lib) -> None:
    make_audio(lib.folder / "rock" / "a.flac", "flac", title="A")
    make_audio(lib.folder / "b.mp3", "mp3")
    (lib.folder / "notes.txt").write_text("keep")
    before = snapshot(lib.folder)
    lib.scan()
    scanner.hash_pending(lib.db, lib.settings)
    lib.scan()
    assert snapshot(lib.folder) == before


def test_hash_pending_fills_the_hashes_and_metadata(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac", title="Hello")
    make_audio(lib.folder / "b.mp3", "mp3", title="World")
    lib.scan()
    assert scanner.hash_pending(lib.db, lib.settings) == 2
    row = lib.item("a.flac")
    assert row["hash_state"] == "done"
    assert row["sha256"] == hashing.file_sha256(lib.folder / "a.flac")
    assert row["audio_hash"] == hashing.audio_hash(lib.folder / "a.flac")
    assert row["audio_hash"] is not None
    assert json.loads(row["metadata_json"])["title"] == ["Hello"]
    assert row["duration_us"] == pytest.approx(1_000_000, abs=100_000)
    revision_sha = (
        lib.db.conn()
        .execute("SELECT sha256 FROM item_revisions WHERE item_id = ?", (row["item_id"],))
        .fetchone()[0]
    )
    assert revision_sha == row["sha256"]
    assert lib.kinds().count("metadata") == 2
    assert scanner.hash_pending(lib.db, lib.settings) == 0


def test_hash_pending_honours_the_limit(lib: Lib) -> None:
    for name in ("a.flac", "b.flac", "c.flac"):
        make_audio(lib.folder / name, "flac")
    lib.scan()
    assert scanner.hash_pending(lib.db, lib.settings, limit=2) == 2
    assert scanner.hash_pending(lib.db, lib.settings) == 1


def test_hash_pending_stops_on_request(lib: Lib) -> None:
    import threading

    make_audio(lib.folder / "a.flac", "flac")
    lib.scan()
    stop = threading.Event()
    stop.set()
    assert scanner.hash_pending(lib.db, lib.settings, stop=stop) == 0
    assert lib.item("a.flac")["hash_state"] == "pending"


def test_hash_pending_marks_a_vanished_file_as_error(lib: Lib) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    lib.scan()
    (lib.folder / "a.flac").unlink()
    assert scanner.hash_pending(lib.db, lib.settings) == 1
    row = lib.item("a.flac")
    assert row["hash_state"] == "error"
    assert row["sha256"] is None


def test_an_audio_hash_failure_alone_is_not_an_error(lib: Lib) -> None:
    (lib.folder / "fake.mp3").write_bytes(b"this is not an mp3 at all")
    lib.scan()
    scanner.hash_pending(lib.db, lib.settings)
    row = lib.item("fake.mp3")
    assert row["hash_state"] == "done"
    assert row["audio_hash"] is None
    assert row["sha256"] == hashing.file_sha256(lib.folder / "fake.mp3")


def test_hashes_of_a_replaced_file_are_discarded(lib: Lib, monkeypatch: pytest.MonkeyPatch) -> None:
    make_audio(lib.folder / "a.flac", "flac")
    lib.scan()
    item_id = lib.item("a.flac")["item_id"]
    real = hashing.audio_hash

    def replace_meanwhile(path: Path) -> str | None:
        with lib.db.transaction() as tx:
            store.replace_item_file(tx, item_id, size_bytes=1, mtime_ns=1, inode=None)
        return real(path)

    monkeypatch.setattr(hashing, "audio_hash", replace_meanwhile)
    scanner.hash_pending(lib.db, lib.settings, limit=1)
    row = lib.item("a.flac")
    assert (row["revision"], row["hash_state"], row["sha256"]) == (2, "pending", None)

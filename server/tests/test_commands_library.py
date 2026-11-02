"""The `adopt-root` and `scan` commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.applications import Starlette

from conftest import MakeUser
from helpers import make_audio
from mtee_remote import cli
from mtee_remote.config import Settings
from mtee_remote.library import hashing, scanner
from test_scanner import snapshot


@pytest.fixture
def env(
    settings: Settings, app: Starlette, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> Starlette:
    """An app whose database the commands will open (they read the same environment)."""
    monkeypatch.setenv("MTEE_REMOTE_DATA", str(settings.data_dir))
    monkeypatch.setenv("MTEE_REMOTE_MUSIC", str(settings.music_dir))
    make_user(app, "alice")
    return app


def run(*argv: str) -> int:
    return cli.main(list(argv))


def roots(app: Starlette) -> list[tuple[str, str, int]]:
    rows = app.state.db.conn().execute(
        "SELECT name, relative_dir, adopted FROM roots ORDER BY name"
    )
    return [tuple(row) for row in rows]  # pyright: ignore[reportReturnType]


def adopt(user: str, path: Path, name: str) -> int:
    return run("adopt-root", "--user", user, "--path", str(path), "--name", name)


def test_adopt_a_folder_inside_the_library(
    env: Starlette, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = settings.music_dir / "alice" / "old"
    make_audio(folder / "rock" / "a.flac", "flac")
    make_audio(folder / "b.mp3", "mp3")
    (folder / "readme.txt").write_text("keep")
    assert adopt("alice", folder, "old") == 0
    assert capsys.readouterr().out.strip() == (
        "Adopted old: 2 audio files found. Their hashes are computed by the running server."
    )
    assert roots(env) == [("old", "old", 1)]
    count = (
        env.state.db.conn()
        .execute("SELECT COUNT(*) FROM items WHERE hash_state = 'pending'")
        .fetchone()[0]
    )
    assert count == 2


def test_adopt_the_whole_library_folder(env: Starlette, settings: Settings) -> None:
    library = settings.music_dir / "alice"
    make_audio(library / "x" / "a.flac", "flac")
    assert adopt("alice", library, "all") == 0
    assert roots(env) == [("all", "", 1)]
    row = env.state.db.conn().execute("SELECT relative_path FROM items").fetchone()
    assert row["relative_path"] == "x/a.flac"
    # the whole-library root is the user's only root
    other = library / "y"
    other.mkdir()
    assert adopt("alice", other, "y") == 1


def test_adopt_refuses_a_folder_outside_the_library(
    env: Starlette, settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert adopt("alice", outside, "x") == 1
    assert "inside" in capsys.readouterr().err
    sibling = settings.music_dir / "bob"
    sibling.mkdir()
    assert adopt("alice", sibling, "x") == 1
    # a path that climbs out with '..' is resolved first
    climbing = settings.music_dir / "alice" / ".." / "bob"
    assert adopt("alice", climbing, "x") == 1
    assert roots(env) == []


def test_adopt_refuses_overlaps_and_duplicates(
    env: Starlette, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    library = settings.music_dir / "alice"
    (library / "rock" / "pop").mkdir(parents=True)
    assert adopt("alice", library / "rock", "rock") == 0
    capsys.readouterr()
    assert adopt("alice", library / "rock" / "pop", "pop") == 1  # inside an existing root
    assert "overlaps" in capsys.readouterr().err
    assert adopt("alice", library, "all") == 1  # contains an existing root
    assert "overlaps" in capsys.readouterr().err
    (library / "jazz").mkdir()
    assert adopt("alice", library / "jazz", "rock") == 1  # name taken
    assert "already" in capsys.readouterr().err
    assert roots(env) == [("rock", "rock", 1)]


def test_adopt_refuses_an_unknown_user_a_bad_name_or_a_file(
    env: Starlette, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = settings.music_dir / "alice" / "f"
    folder.mkdir()
    assert adopt("nobody", folder, "f") == 1
    assert "no account" in capsys.readouterr().err
    assert adopt("alice", folder, "a/b") == 1
    capsys.readouterr()
    file = folder / "x.txt"
    file.write_text("x")
    assert adopt("alice", file, "x") == 1
    assert adopt("alice", folder / "missing", "x") == 1
    assert roots(env) == []


def test_adoption_and_hashing_leave_the_folder_identical(
    env: Starlette, settings: Settings
) -> None:
    folder = settings.music_dir / "alice" / "library"
    make_audio(folder / "rock" / "a.flac", "flac", title="A")
    make_audio(folder / "rock" / "b.m4a", "m4a")
    make_audio(folder / "c.mp3", "mp3")
    (folder / "cover.jpg").write_bytes(b"jpeg")
    (folder / "empty").mkdir()
    before = snapshot(folder)
    dirs_before = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_dir())
    assert adopt("alice", folder, "library") == 0
    assert scanner.hash_pending(env.state.db, settings) == 3
    assert run("scan", "--user", "alice") == 0
    assert snapshot(folder) == before
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_dir()) == (
        dirs_before
    )
    stored = {
        row["relative_path"]: row["sha256"]
        for row in env.state.db.conn().execute("SELECT relative_path, sha256 FROM items")
    }
    assert stored == {
        "rock/a.flac": before["rock/a.flac"][2],
        "rock/b.m4a": before["rock/b.m4a"][2],
        "c.mp3": before["c.mp3"][2],
    }
    assert stored["c.mp3"] == hashing.file_sha256(folder / "c.mp3")


def test_scan_command_reports_changes(
    env: Starlette, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = settings.music_dir / "alice" / "one"
    make_audio(folder / "a.flac", "flac")
    other = settings.music_dir / "alice" / "two"
    other.mkdir()
    assert adopt("alice", folder, "one") == 0
    assert adopt("alice", other, "two") == 0
    capsys.readouterr()
    make_audio(other / "n.flac", "flac")
    assert run("scan", "--user", "alice") == 0
    assert capsys.readouterr().out.splitlines() == [
        "one: 0 added, 0 changed, 0 moved, 0 removed, 1 unchanged",
        "two: 1 added, 0 changed, 0 moved, 0 removed, 0 unchanged",
    ]
    (other / "n.flac").unlink()
    assert run("scan", "--user", "alice", "--root", "two") == 0
    assert capsys.readouterr().out.strip() == (
        "two: 0 added, 0 changed, 0 moved, 1 removed, 0 unchanged"
    )


def test_scan_command_errors(env: Starlette, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("scan", "--user", "nobody") == 1
    assert "no account" in capsys.readouterr().err
    assert run("scan", "--user", "alice") == 1
    assert "no root" in capsys.readouterr().err
    assert run("scan", "--user", "alice", "--root", "missing") == 1
    assert "missing" in capsys.readouterr().err


def test_commands_need_their_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MTEE_REMOTE_DATA", raising=False)
    assert run("scan", "--user", "alice") == 1
    assert "MTEE_REMOTE_DATA" in capsys.readouterr().err

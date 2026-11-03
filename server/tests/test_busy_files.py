"""A file another process holds open answers `409 busy`, never a 500 (busy files).

The background hasher can hold a file open on Windows, which makes a move, a trash, a restore
or an upload commit fail with a sharing violation. Those operations retry (`uploads.retry_busy`),
then undo their partial step and answer `busy`: nothing is lost and nothing is overwritten.
"""

from __future__ import annotations

import errno
import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from mtee_remote import uploads
from mtee_remote.errors import file_error, is_busy_error
from test_uploads import Env, blob, snapshot_tree
from test_uploads import env as env

# The waits of five retries; the tests record them instead of sleeping.
SCHEDULE = [0.05, 0.1, 0.2, 0.4, 0.8]


@pytest.fixture(autouse=True)
def pauses(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []
    monkeypatch.setattr(uploads, "_pause", waits.append)
    return waits


def busy_error(winerror: bool) -> OSError:
    """A permission error, or the Windows form (winerror 32) of a busy file."""
    if not winerror:
        return PermissionError(errno.EACCES, "The file is in use.")
    error = OSError(errno.EINVAL, "The process cannot access the file.")
    error.winerror = 32  # pyright: ignore[reportAttributeAccessIssue]
    return error


@contextmanager
def fail_on(
    op: str, path: Path, make_error: Callable[[], OSError], *, times: int | None = None
) -> Iterator[list[Path]]:
    """Make `os.<op>` raise for `path`: its first `times` calls, or every call when None.

    The yielded list gets one entry per call that names `path`.
    """
    real: Callable[..., Any] = getattr(os, op)
    calls: list[Path] = []

    def fake(target: Any, *args: Any, **kwargs: Any) -> Any:
        if Path(target) != path:
            return real(target, *args, **kwargs)
        calls.append(path)
        if times is None or len(calls) <= times:
            raise make_error()
        return real(target, *args, **kwargs)

    with patch.object(os, op, fake):
        yield calls


def busy_file(
    op: str, path: Path, *, times: int | None = None, winerror: bool = False
) -> AbstractContextManager[list[Path]]:
    return fail_on(op, path, lambda: busy_error(winerror), times=times)


def move(env: Env, item_id: str, relative_path: str) -> Any:
    return env.client.post(
        f"/api/v1/items/{item_id}/move", json={"relative_path": relative_path}, headers=env.headers
    )


def trash(env: Env, item_id: str) -> Any:
    return env.client.post(f"/api/v1/items/{item_id}/trash", headers=env.headers)


def restore(env: Env, trash_id: str) -> Any:
    return env.client.post(f"/api/v1/trash/{trash_id}/restore", headers=env.headers)


def staged(env: Env, relative_path: str, data: bytes, **extra: Any) -> str:
    """Create an upload and send all its bytes; the commit is left to the test."""
    created = env.create(relative_path, data, **extra)
    assert created.status_code == 201, created.text
    upload_id: str = created.json()["upload_id"]
    assert env.put(upload_id, data, 0, len(data)).status_code == 200
    return upload_id


def part_of(env: Env, upload_id: str) -> Path:
    return env.library / ".mtee-tmp" / "uploads" / f"{upload_id}.part"


def trashed(env: Env, data: bytes) -> tuple[str, str]:
    """Upload `rock/song.flac`, trash it; return `(item_id, trash_id)`."""
    item = env.upload("rock/song.flac", data)
    response = trash(env, item["item_id"])
    assert response.status_code == 200, response.text
    trash_id: str = response.json()["trash_id"]
    return item["item_id"], trash_id


def assert_busy(response: Any) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "busy"


# -- helpers --------------------------------------------------------------------------


def test_busy_errors_are_recognised_and_other_errors_are_not() -> None:
    assert is_busy_error(PermissionError(errno.EACCES, "denied"))
    assert is_busy_error(busy_error(winerror=True))
    assert not is_busy_error(OSError(errno.EIO, "Input/output error"))


def test_file_errors_map_to_readable_api_errors() -> None:
    missing = file_error(FileNotFoundError(errno.ENOENT, "missing"))
    assert (missing.code, missing.status) == ("not_found", 404)
    busy = file_error(busy_error(winerror=False))
    assert (busy.code, busy.status) == ("busy", 409)
    unexpected = file_error(OSError(errno.EIO, "Input/output error"))
    assert (unexpected.code, unexpected.status) == ("file_error", 500)
    assert "Input/output" not in unexpected.message


# -- move -----------------------------------------------------------------------------


@pytest.mark.parametrize("winerror", [False, True])
def test_move_succeeds_after_two_busy_attempts(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(400)
    item = env.upload("old/song.flac", data)
    source = env.folder / "old" / "song.flac"
    with busy_file("unlink", source, times=2, winerror=winerror) as calls:
        response = move(env, item["item_id"], "new/song.flac")
    assert response.status_code == 200, response.text
    assert len(calls) == 3
    assert pauses == SCHEDULE[:2]
    assert (env.folder / "new" / "song.flac").read_bytes() == data
    assert not source.exists()


@pytest.mark.parametrize("winerror", [False, True])
def test_move_answers_busy_and_keeps_the_file_when_it_stays_busy(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(400)
    item = env.upload("old/song.flac", data)
    source = env.folder / "old" / "song.flac"
    before = snapshot_tree(env.library)
    with busy_file("unlink", source, winerror=winerror):
        response = move(env, item["item_id"], "new/song.flac")
    assert_busy(response)
    assert pauses == SCHEDULE
    assert source.read_bytes() == data
    assert not (env.folder / "new" / "song.flac").exists()
    assert snapshot_tree(env.library) == before
    stored = env.client.get(f"/api/v1/items/{item['item_id']}", headers=env.headers).json()
    assert stored["relative_path"] == "old/song.flac"
    # Once the file is free, the same request works.
    assert move(env, item["item_id"], "new/song.flac").status_code == 200


# -- trash ----------------------------------------------------------------------------


@pytest.mark.parametrize("winerror", [False, True])
def test_trash_succeeds_after_two_busy_attempts(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(400)
    item = env.upload("rock/song.flac", data)
    source = env.folder / "rock" / "song.flac"
    with busy_file("unlink", source, times=2, winerror=winerror):
        response = trash(env, item["item_id"])
    assert response.status_code == 200, response.text
    trash_id = response.json()["trash_id"]
    assert pauses == SCHEDULE[:2]
    assert not source.exists()
    assert (env.library / ".mtee-trash" / trash_id / "song.flac").read_bytes() == data


@pytest.mark.parametrize("winerror", [False, True])
def test_trash_answers_busy_and_keeps_the_file_when_it_stays_busy(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(400)
    item = env.upload("rock/song.flac", data)
    source = env.folder / "rock" / "song.flac"
    before = snapshot_tree(env.library)
    with busy_file("unlink", source, winerror=winerror):
        response = trash(env, item["item_id"])
    assert_busy(response)
    assert pauses == SCHEDULE
    assert source.read_bytes() == data
    assert snapshot_tree(env.library) == before
    assert env.trash_entries() == []
    assert (
        env.client.get(f"/api/v1/items/{item['item_id']}", headers=env.headers).status_code == 200
    )
    assert trash(env, item["item_id"]).status_code == 200


# -- restore --------------------------------------------------------------------------


@pytest.mark.parametrize("winerror", [False, True])
def test_restore_succeeds_after_two_busy_attempts(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(400)
    item_id, trash_id = trashed(env, data)
    stored = env.library / ".mtee-trash" / trash_id / "song.flac"
    with busy_file("unlink", stored, times=2, winerror=winerror):
        response = restore(env, trash_id)
    assert response.status_code == 200, response.text
    assert response.json()["item"]["item_id"] == item_id
    assert pauses == SCHEDULE[:2]
    assert (env.folder / "rock" / "song.flac").read_bytes() == data
    assert env.trash_entries() == []


@pytest.mark.parametrize("winerror", [False, True])
def test_restore_answers_busy_and_keeps_the_trashed_file_when_it_stays_busy(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(400)
    _, trash_id = trashed(env, data)
    stored = env.library / ".mtee-trash" / trash_id / "song.flac"
    before = snapshot_tree(env.library)
    with busy_file("unlink", stored, winerror=winerror):
        response = restore(env, trash_id)
    assert_busy(response)
    assert pauses == SCHEDULE
    assert stored.read_bytes() == data
    assert not (env.folder / "rock" / "song.flac").exists()
    assert snapshot_tree(env.library) == before
    assert [entry["trash_id"] for entry in env.trash_entries()] == [trash_id]
    assert restore(env, trash_id).status_code == 200


# -- upload commit: a new file -----------------------------------------------------------


@pytest.mark.parametrize("winerror", [False, True])
def test_upload_commit_succeeds_after_two_busy_attempts(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(300)
    upload_id = staged(env, "rock/song.flac", data)
    with busy_file("unlink", part_of(env, upload_id), times=2, winerror=winerror):
        response = env.commit(upload_id)
    assert response.status_code == 200, response.text
    assert pauses == SCHEDULE[:2]
    assert (env.folder / "rock" / "song.flac").read_bytes() == data
    assert not part_of(env, upload_id).exists()


@pytest.mark.parametrize("winerror", [False, True])
def test_upload_commit_answers_busy_and_stays_open_when_it_stays_busy(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    data = blob(300)
    upload_id = staged(env, "rock/song.flac", data)
    part = part_of(env, upload_id)
    before = snapshot_tree(env.library)
    with busy_file("unlink", part, winerror=winerror):
        response = env.commit(upload_id)
    assert_busy(response)
    assert pauses == SCHEDULE
    assert part.read_bytes() == data
    assert not (env.folder / "rock" / "song.flac").exists()
    assert snapshot_tree(env.library) == before
    assert env.status(upload_id)["state"] == "open"
    committed = env.commit(upload_id)
    assert committed.status_code == 200, committed.text
    assert (env.folder / "rock" / "song.flac").read_bytes() == data


def test_upload_cancel_answers_busy_and_stays_open(env: Env) -> None:
    upload_id = staged(env, "rock/song.flac", blob(300))
    with busy_file("unlink", part_of(env, upload_id)):
        response = env.client.delete(f"/api/v1/uploads/{upload_id}", headers=env.headers)
    assert_busy(response)
    assert env.status(upload_id)["state"] == "open"
    assert env.client.delete(f"/api/v1/uploads/{upload_id}", headers=env.headers).status_code == 204


# -- upload commit: a replacement ----------------------------------------------------------


def replacement_of(env: Env, item_id: str, data: bytes) -> str:
    return staged(env, "rock/song.flac", data, base_item_id=item_id, base_revision=1)


@pytest.mark.parametrize("winerror", [False, True])
def test_replacement_succeeds_after_two_busy_attempts(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    old, new = blob(300, "old"), blob(500, "new")
    item = env.upload("rock/song.flac", old)
    upload_id = replacement_of(env, item["item_id"], new)
    target = env.folder / "rock" / "song.flac"
    with busy_file("unlink", target, times=2, winerror=winerror):
        response = env.commit(upload_id)
    assert response.status_code == 200, response.text
    assert pauses == SCHEDULE[:2]
    assert target.read_bytes() == new


@pytest.mark.parametrize("winerror", [False, True])
def test_replacement_answers_busy_at_the_old_file_and_keeps_it(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    old, new = blob(300, "old"), blob(500, "new")
    item = env.upload("rock/song.flac", old)
    upload_id = replacement_of(env, item["item_id"], new)
    target = env.folder / "rock" / "song.flac"
    before = snapshot_tree(env.library)
    with busy_file("unlink", target, winerror=winerror):
        response = env.commit(upload_id)
    assert_busy(response)
    assert pauses == SCHEDULE
    assert target.read_bytes() == old
    assert snapshot_tree(env.library) == before
    assert env.trash_entries() == []
    assert env.status(upload_id)["state"] == "open"
    assert env.commit(upload_id).status_code == 200
    assert target.read_bytes() == new


@pytest.mark.parametrize("winerror", [False, True])
def test_replacement_answers_busy_at_the_new_file_and_restores_the_old_one(
    env: Env, pauses: list[float], winerror: bool
) -> None:
    old, new = blob(300, "old"), blob(500, "new")
    item = env.upload("rock/song.flac", old)
    upload_id = replacement_of(env, item["item_id"], new)
    target = env.folder / "rock" / "song.flac"
    before = snapshot_tree(env.library)
    with busy_file("unlink", part_of(env, upload_id), winerror=winerror):
        response = env.commit(upload_id)
    assert_busy(response)
    assert pauses == SCHEDULE
    assert target.read_bytes() == old
    assert snapshot_tree(env.library) == before
    assert env.trash_entries() == []
    assert env.status(upload_id)["state"] == "open"
    assert env.commit(upload_id).status_code == 200
    assert target.read_bytes() == new


# -- unexpected errors ---------------------------------------------------------------------


def test_an_unexpected_os_error_is_a_readable_500_and_changes_nothing(env: Env) -> None:
    data = blob(400)
    item = env.upload("old/song.flac", data)
    source = env.folder / "old" / "song.flac"
    with fail_on("unlink", source, lambda: OSError(errno.EIO, "Input/output error")):
        response = move(env, item["item_id"], "new/song.flac")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "file_error"
    assert "Input/output" not in response.text
    assert source.read_bytes() == data
    assert not (env.folder / "new" / "song.flac").exists()


def test_a_file_that_vanishes_during_a_move_is_not_found(env: Env) -> None:
    item = env.upload("old/song.flac", blob(400))
    source = env.folder / "old" / "song.flac"
    with fail_on("link", source, lambda: FileNotFoundError(errno.ENOENT, "gone")):
        response = move(env, item["item_id"], "new/song.flac")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

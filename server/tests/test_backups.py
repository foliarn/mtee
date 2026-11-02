"""Database backups: upload, download, list, trash, restore, purge, quota, retention (124.7)."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from mtee_remote import clock
from test_uploads import Env, blob, build_env
from test_uploads import env as env

START = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
SetTime = Callable[[datetime], None]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def data_dir(env: Env) -> Path:
    return env.app.state.settings.data_dir


def create_backup(env: Env, data: bytes, *, sha256: str | None = None, **fields: Any) -> Any:
    body = {"purpose": "backup", "size_bytes": len(data), "sha256": sha256 or sha(data), **fields}
    return env.client.post("/api/v1/uploads", json=body, headers=env.headers)


def send_in_two_chunks(env: Env, upload_id: str, data: bytes) -> None:
    half = len(data) // 2
    assert env.put(upload_id, data[:half], 0, len(data)).status_code == 200
    sent = env.put(upload_id, data[half:], half, len(data))
    assert sent.json() == {"received_bytes": len(data)}


def backup(env: Env, data: bytes, **options: Any) -> dict[str, Any]:
    """Create, send in two chunks and commit a backup; return its public view."""
    created = create_backup(env, data, **options)
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload_id"]
    send_in_two_chunks(env, upload_id, data)
    committed = env.commit(upload_id)
    assert committed.status_code == 200, committed.text
    body: dict[str, Any] = committed.json()["backup"]
    return body


def delete(env: Env, backup_id: str) -> Any:
    return env.client.delete(f"/api/v1/backups/{backup_id}", headers=env.headers)


def restore(env: Env, trash_id: str) -> Any:
    return env.client.post(f"/api/v1/trash/{trash_id}/restore", headers=env.headers)


def purge(env: Env, trash_id: str, query: str = "?confirm=yes") -> Any:
    return env.client.delete(f"/api/v1/trash/{trash_id}{query}", headers=env.headers)


def error_code(response: Any) -> str:
    code: str = response.json()["error"]["code"]
    return code


def stored_file(env: Env, user_id: str, backup_id: str) -> Path:
    return data_dir(env) / "backups" / user_id / f"{backup_id}.db"


def trashed_file(env: Env, backup_id: str) -> Path:
    return data_dir(env) / "trash" / "backups" / f"{backup_id}.db"


@pytest.fixture
def clock_at(monkeypatch: pytest.MonkeyPatch) -> SetTime:
    """Replace the server clock with a value the test sets (starts at `START`)."""
    now = [START]
    monkeypatch.setattr(clock, "utc_now", lambda: now[0])

    def set_time(moment: datetime) -> None:
        now[0] = moment

    return set_time


@pytest.fixture
def admin_env(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> Env:
    return build_env(client, app, make_user, make_device, "root", is_admin=True)


@pytest.fixture
def other(client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice) -> Env:
    return build_env(client, app, make_user, make_device, "bob")


@pytest.fixture
def quota_env(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> Env:
    return build_env(client, app, make_user, make_device, "carol", quota_bytes=1000)


# -- upload, list, download --------------------------------------------------------


def test_upload_in_two_chunks_then_list_and_download_back_identical(env: Env) -> None:
    data = blob(20_000, "nightly")
    created = create_backup(env, data, label="Nightly", kind="automatic")
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]
    assert created.json() == {"upload_id": upload_id, "received_bytes": 0, "size_bytes": len(data)}
    # the part file lives in <data>/uploads, not in the library folder
    part = data_dir(env) / "uploads" / f"{upload_id}.part"
    half = len(data) // 2
    assert env.put(upload_id, data[:half], 0, len(data)).status_code == 200
    assert part.stat().st_size == half
    assert not list(env.library.rglob("*.part"))
    assert env.put(upload_id, data[half:], half, len(data)).status_code == 200
    committed = env.commit(upload_id)
    assert committed.status_code == 200
    body = committed.json()
    assert set(body) == {"backup"}
    listed_backup = body["backup"]
    assert set(listed_backup) == {
        "backup_id",
        "label",
        "kind",
        "size_bytes",
        "sha256",
        "device_id",
        "created_at_utc",
    }
    assert (listed_backup["label"], listed_backup["kind"]) == ("Nightly", "automatic")
    assert (listed_backup["size_bytes"], listed_backup["sha256"]) == (len(data), sha(data))
    assert listed_backup["device_id"] is not None
    assert not part.exists()
    assert env.status(upload_id)["state"] == "done"

    backup_id = listed_backup["backup_id"]
    assert stored_file(env, env.user_id, backup_id).read_bytes() == data
    listed = env.client.get("/api/v1/backups", headers=env.headers)
    assert listed.json() == {"backups": [listed_backup]}
    single = env.client.get(f"/api/v1/backups/{backup_id}", headers=env.headers)
    assert single.json() == listed_backup

    downloaded = env.client.get(f"/api/v1/backups/{backup_id}/file", headers=env.headers)
    assert downloaded.status_code == 200
    assert downloaded.content == data
    assert sha(downloaded.content) == sha(data)
    assert downloaded.headers["Content-Type"] == "application/octet-stream"
    assert downloaded.headers["ETag"] == f'"{sha(data)}"'
    assert downloaded.headers["Content-Length"] == str(len(data))

    assert env.kinds() == ["backup_added"]
    assert env.payloads("backup_added") == [
        {"backup_id": backup_id, "label": "Nightly", "kind": "automatic", "size_bytes": len(data)}
    ]


def test_range_on_the_download(env: Env) -> None:
    data = blob(5000, "range")
    backup_id = backup(env, data)["backup_id"]
    response = env.client.get(
        f"/api/v1/backups/{backup_id}/file", headers={**env.headers, "Range": "bytes=100-199"}
    )
    assert response.status_code == 206
    assert response.content == data[100:200]
    assert response.headers["Content-Range"] == f"bytes 100-199/{len(data)}"


def test_default_label_and_kind_and_newest_first_listing(env: Env, clock_at: SetTime) -> None:
    clock_at(START)
    first = backup(env, blob(10, "a"))
    clock_at(START + timedelta(hours=1))
    second = backup(env, blob(10, "b"), label="second")
    assert (first["label"], first["kind"]) == (None, "manual")
    assert second["label"] == "second"
    listed = env.client.get("/api/v1/backups", headers=env.headers).json()["backups"]
    assert [b["backup_id"] for b in listed] == [second["backup_id"], first["backup_id"]]


def test_a_wrong_sha256_is_422_and_the_bytes_are_sent_again(env: Env) -> None:
    data = blob(1000, "wrong")
    created = create_backup(env, data, sha256=sha(b"something else"))
    upload_id = created.json()["upload_id"]
    assert env.put(upload_id, data, 0, len(data)).status_code == 200
    committed = env.commit(upload_id)
    assert (committed.status_code, error_code(committed)) == (422, "bad_hash")
    assert env.status(upload_id) == {
        "upload_id": upload_id,
        "state": "open",
        "received_bytes": 0,
        "size_bytes": len(data),
    }
    assert env.client.get("/api/v1/backups", headers=env.headers).json() == {"backups": []}


@pytest.mark.parametrize(
    "fields",
    [
        {"root_id": "x"},
        {"relative_path": "a.db"},
        {"root_id": None},
        {"base_item_id": "x", "base_revision": 1},
        {"base_revision": 1},
    ],
)
def test_root_and_path_fields_with_purpose_backup_are_400(env: Env, fields: dict[str, Any]) -> None:
    response = create_backup(env, blob(10), **fields)
    assert (response.status_code, error_code(response)) == (400, "bad_request")


def test_a_backup_commit_with_a_path_is_400(env: Env) -> None:
    data = blob(100, "path")
    upload_id = create_backup(env, data).json()["upload_id"]
    env.put(upload_id, data, 0, len(data))
    response = env.commit(upload_id, relative_path="a.db")
    assert (response.status_code, error_code(response)) == (400, "bad_request")


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"kind": "weekly"}, 400),
        ({"kind": 3}, 400),
        ({"label": "x" * 201}, 400),
        ({"label": 7}, 400),
    ],
)
def test_bad_kind_or_label_is_400(env: Env, fields: dict[str, Any], code: int) -> None:
    assert create_backup(env, blob(10), **fields).status_code == code


def test_a_cancelled_backup_upload_removes_its_part_file(env: Env) -> None:
    created = create_backup(env, blob(100))
    upload_id = created.json()["upload_id"]
    part = data_dir(env) / "uploads" / f"{upload_id}.part"
    assert part.exists()
    assert env.client.delete(f"/api/v1/uploads/{upload_id}", headers=env.headers).status_code == 204
    assert not part.exists()


# -- quota -----------------------------------------------------------------------------


def test_quota_counts_present_backups_and_backup_trash(quota_env: Env) -> None:
    env = quota_env
    first = backup(env, blob(600, "q1"))
    over = create_backup(env, blob(500, "q2"))
    assert (over.status_code, error_code(over)) == (413, "quota_exceeded")
    assert create_backup(env, blob(400, "q3")).status_code == 201
    # a backup in the trash still occupies the quota
    assert delete(env, first["backup_id"]).status_code == 204
    again = create_backup(env, blob(500, "q4"))
    assert (again.status_code, error_code(again)) == (413, "quota_exceeded")


# -- trash, restore, purge -------------------------------------------------------------


def test_delete_moves_to_trash_and_restore_lists_it_again(env: Env) -> None:
    data = blob(3000, "trash")
    before = backup(env, data, label="keep me", kind="automatic")
    backup_id = before["backup_id"]
    assert delete(env, backup_id).status_code == 204
    assert env.client.get("/api/v1/backups", headers=env.headers).json() == {"backups": []}
    assert env.client.get(f"/api/v1/backups/{backup_id}", headers=env.headers).status_code == 404
    assert (
        env.client.get(f"/api/v1/backups/{backup_id}/file", headers=env.headers).status_code == 404
    )
    assert delete(env, backup_id).status_code == 404
    assert not stored_file(env, env.user_id, backup_id).exists()
    assert trashed_file(env, backup_id).read_bytes() == data

    entries = env.trash_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry == {
        "trash_id": entry["trash_id"],
        "kind": "backup",
        "item_id": None,
        "backup_id": backup_id,
        "original_root_id": None,
        "original_relative_path": None,
        "size_bytes": len(data),
        "trashed_at_utc": entry["trashed_at_utc"],
    }
    assert env.payloads("backup_trashed") == [{"backup_id": backup_id}]

    response = restore(env, entry["trash_id"])
    assert response.status_code == 200
    assert response.json() == {"backup": before}
    assert env.trash_entries() == []
    assert stored_file(env, env.user_id, backup_id).read_bytes() == data
    assert not trashed_file(env, backup_id).exists()
    downloaded = env.client.get(f"/api/v1/backups/{backup_id}/file", headers=env.headers)
    assert downloaded.content == data
    assert restore(env, entry["trash_id"]).status_code == 404


def test_restore_refuses_a_relative_path(env: Env) -> None:
    backup_id = backup(env, blob(50))["backup_id"]
    delete(env, backup_id)
    trash_id = env.trash_entries()[0]["trash_id"]
    response = env.client.post(
        f"/api/v1/trash/{trash_id}/restore",
        json={"relative_path": "elsewhere.db"},
        headers=env.headers,
    )
    assert (response.status_code, error_code(response)) == (400, "bad_request")


def test_purge_by_an_administrator_removes_the_file(admin_env: Env) -> None:
    data = blob(400, "purge")
    backup_id = backup(admin_env, data)["backup_id"]
    file_path = stored_file(admin_env, admin_env.user_id, backup_id)
    assert delete(admin_env, backup_id).status_code == 204
    trash_id = admin_env.trash_entries()[0]["trash_id"]
    assert purge(admin_env, trash_id, query="").status_code == 400
    assert purge(admin_env, trash_id).status_code == 204
    assert not trashed_file(admin_env, backup_id).exists()
    assert not file_path.exists()
    assert admin_env.trash_entries() == []
    rows = admin_env.app.state.db.conn().execute(
        "SELECT COUNT(*) FROM backups WHERE backup_id = ?", (backup_id,)
    )
    assert rows.fetchone()[0] == 0
    assert purge(admin_env, trash_id).status_code == 404


def test_purge_is_for_administrators_only(env: Env) -> None:
    backup_id = backup(env, blob(40))["backup_id"]
    delete(env, backup_id)
    trash_id = env.trash_entries()[0]["trash_id"]
    response = purge(env, trash_id)
    assert (response.status_code, error_code(response)) == (403, "forbidden")
    assert trashed_file(env, backup_id).exists()


# -- privacy ---------------------------------------------------------------------------


def test_another_users_backups_are_invisible(env: Env, other: Env) -> None:
    backup_id = backup(env, blob(100, "private"))["backup_id"]
    assert other.client.get("/api/v1/backups", headers=other.headers).json() == {"backups": []}
    assert (
        other.client.get(f"/api/v1/backups/{backup_id}", headers=other.headers).status_code == 404
    )
    assert (
        other.client.get(f"/api/v1/backups/{backup_id}/file", headers=other.headers).status_code
        == 404
    )
    assert delete(other, backup_id).status_code == 404
    assert other.client.get("/api/v1/backups", headers=other.headers).json() == {"backups": []}
    assert env.client.get(f"/api/v1/backups/{backup_id}", headers=env.headers).status_code == 200
    delete(env, backup_id)
    trash_id = env.trash_entries()[0]["trash_id"]
    assert restore(other, trash_id).status_code == 404
    assert other.trash_entries() == []


# -- settings --------------------------------------------------------------------------


def test_settings_default_then_store_and_validate(env: Env) -> None:
    assert env.client.get("/api/v1/settings/backups", headers=env.headers).json() == {
        "daily": 30,
        "weekly": 12,
    }
    stored = env.client.put(
        "/api/v1/settings/backups", json={"daily": 7, "weekly": 3}, headers=env.headers
    )
    assert stored.status_code == 200
    assert stored.json() == {"daily": 7, "weekly": 3}
    assert env.client.get("/api/v1/settings/backups", headers=env.headers).json() == {
        "daily": 7,
        "weekly": 3,
    }
    for body in (
        {"daily": 366, "weekly": 3},
        {"daily": 7, "weekly": 105},
        {"daily": -1, "weekly": 3},
        {"daily": "7", "weekly": 3},
        {"daily": True, "weekly": 3},
        {"daily": 7},
    ):
        response = env.client.put("/api/v1/settings/backups", json=body, headers=env.headers)
        assert (response.status_code, error_code(response)) == (400, "bad_request"), body
    assert env.client.get("/api/v1/settings/backups", headers=env.headers).json() == {
        "daily": 7,
        "weekly": 3,
    }


# -- retention -------------------------------------------------------------------------


def expected_keep(history: list[tuple[datetime, str]], daily: int, weekly: int) -> set[str]:
    """The backups that retention must keep, worked out here and not by the server code.

    Weeks start on Monday; the newest backup of each of the `daily` latest dates and of each of
    the `weekly` latest weeks is kept.
    """
    newest_on_day: dict[date, str] = {}
    newest_in_week: dict[date, str] = {}
    for moment, backup_id in sorted(history):
        day = moment.date()
        newest_on_day[day] = backup_id
        newest_in_week[day - timedelta(days=day.weekday())] = backup_id
    keep: set[str] = set()
    for day in sorted(newest_on_day, reverse=True)[:daily]:
        keep.add(newest_on_day[day])
    for monday in sorted(newest_in_week, reverse=True)[:weekly]:
        keep.add(newest_in_week[monday])
    return keep


def build_history(env: Env, clock_at: SetTime) -> tuple[list[tuple[datetime, str]], list[str]]:
    """150 days of automatic backups (two on every fifth day) and some manual ones.

    Returns the automatic `(moment, backup_id)` pairs and the manual backup ids.
    """
    automatic: list[tuple[datetime, str]] = []
    manual: list[str] = []
    for moment in (
        datetime(2025, 3, 10, 9, tzinfo=UTC),
        datetime(2025, 3, 10, 9, 30, tzinfo=UTC),
        datetime(2025, 6, 1, 12, tzinfo=UTC),
    ):
        clock_at(moment)
        manual.append(backup(env, blob(40, moment.isoformat()), kind="manual")["backup_id"])
    for day in range(150):
        base = START + timedelta(days=day)
        if day == 40:
            clock_at(base - timedelta(hours=1))
            manual.append(backup(env, blob(40, "middle"), kind="manual")["backup_id"])
        moments = [base] + ([base.replace(hour=15)] if day % 5 == 0 else [])
        for moment in moments:
            clock_at(moment)
            data = blob(40, moment.isoformat())
            automatic.append((moment, backup(env, data, kind="automatic")["backup_id"]))
    return automatic, manual


def present_ids(env: Env) -> set[str]:
    listed = env.client.get("/api/v1/backups", headers=env.headers).json()["backups"]
    return {b["backup_id"] for b in listed}


def test_retention_keeps_the_expected_set(env: Env, clock_at: SetTime) -> None:
    automatic, manual = build_history(env, clock_at)
    assert len(automatic) == 180
    expected = expected_keep(automatic, daily=30, weekly=12)
    daily_only = expected_keep(automatic, daily=30, weekly=0)
    # the weekly rule adds backups beyond the daily window, so this test exercises it
    assert expected > daily_only
    present = present_ids(env)
    assert {i for _, i in automatic if i in present} == expected
    assert set(manual) <= present
    assert len(present) == len(expected) + len(manual)
    trashed = [e for e in env.trash_entries() if e["kind"] == "backup"]
    assert {e["backup_id"] for e in trashed} == {i for _, i in automatic} - expected
    for entry in trashed:
        assert trashed_file(env, entry["backup_id"]).is_file()
    for backup_id in expected:
        assert (
            env.client.get(f"/api/v1/backups/{backup_id}", headers=env.headers).status_code == 200
        )
    assert len(env.payloads("backup_trashed")) == len(automatic) - len(expected)
    assert len(env.payloads("backup_added")) == len(automatic) + len(manual)


def test_lowering_the_settings_trashes_more_and_keeps_manual(env: Env, clock_at: SetTime) -> None:
    automatic, manual = build_history(env, clock_at)
    kept_before = expected_keep(automatic, daily=30, weekly=12)
    still_present = [(m, i) for m, i in automatic if i in kept_before]

    response = env.client.put(
        "/api/v1/settings/backups", json={"daily": 5, "weekly": 2}, headers=env.headers
    )
    assert response.status_code == 200
    expected_after = expected_keep(still_present, daily=5, weekly=2)
    present = present_ids(env)
    assert {i for _, i in automatic if i in present} == expected_after
    assert set(manual) <= present
    assert len(expected_after) < len(kept_before)

    # the same settings again change nothing
    env.client.put("/api/v1/settings/backups", json={"daily": 5, "weekly": 2}, headers=env.headers)
    assert present_ids(env) == present


def test_manual_backups_are_never_trashed(env: Env, clock_at: SetTime) -> None:
    clock_at(datetime(2024, 1, 1, 10, tzinfo=UTC))
    manual = [backup(env, blob(30, f"m{i}"), kind="manual")["backup_id"] for i in range(3)]
    env.client.put("/api/v1/settings/backups", json={"daily": 0, "weekly": 0}, headers=env.headers)
    assert present_ids(env) == set(manual)
    assert env.trash_entries() == []


def test_daily_zero_and_weekly_zero_trash_every_automatic_backup(
    env: Env, clock_at: SetTime
) -> None:
    clock_at(START)
    automatic = backup(env, blob(30, "z1"), kind="automatic")["backup_id"]
    kept_manual = backup(env, blob(30, "z2"), kind="manual")["backup_id"]
    assert present_ids(env) == {automatic, kept_manual}
    # with zero days and zero weeks no automatic backup survives; the manual one stays
    env.client.put("/api/v1/settings/backups", json={"daily": 0, "weekly": 0}, headers=env.headers)
    assert present_ids(env) == {kept_manual}
    # a new automatic backup is stored (201/200) and retention trashes it at once
    late = backup(env, blob(30, "z3"), kind="automatic")
    assert present_ids(env) == {kept_manual}
    assert late["backup_id"] in {e["backup_id"] for e in env.trash_entries()}


# -- journal and sqlite sanity ---------------------------------------------------------


def test_the_database_rows_match_the_files(env: Env) -> None:
    backup_id = backup(env, blob(77, "rows"), kind="automatic")["backup_id"]
    conn: sqlite3.Connection = env.app.state.db.conn()
    row = conn.execute(
        "SELECT stored_path, state, kind, size_bytes FROM backups WHERE backup_id = ?", (backup_id,)
    ).fetchone()
    assert (row["state"], row["kind"], row["size_bytes"]) == ("present", "automatic", 77)
    assert (data_dir(env) / row["stored_path"]).is_file()

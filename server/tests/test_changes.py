"""The change journal route, long polling and the device cursor (milestone 124.6)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser
from mtee_remote import journal

CHANGES = "/api/v1/changes"
CURSOR = "/api/v1/devices/me/cursor"


def _append(app: Starlette, user: dict[str, Any], name: str) -> int:
    with app.state.db.transaction() as tx:
        return journal.append(tx, user["user_id"], "added", None, {"relative_path": name})


def _names(body: dict[str, Any]) -> list[str]:
    return [change["payload"]["relative_path"] for change in body["changes"]]


def test_two_devices_read_each_change_once(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device_a = make_device(app, alice, name="A")
    device_b = make_device(app, alice, name="B")
    for name in ("a.flac", "b.flac", "c.flac"):
        _append(app, alice, name)

    first = client.get(f"{CHANGES}?since=0", headers=device_b["headers"]).json()
    assert _names(first) == ["a.flac", "b.flac", "c.flac"]
    assert first["next"] == 3
    assert first["more"] is False
    change = first["changes"][0]
    assert set(change) == {"seq", "item_id", "kind", "payload", "at_utc"}
    assert change["seq"] == 1
    assert change["kind"] == "added"
    assert change["at_utc"].endswith("Z")

    stored = client.put(CURSOR, json={"seq": first["next"]}, headers=device_b["headers"])
    assert stored.status_code == 204
    assert client.get(CURSOR, headers=device_b["headers"]).json() == {"seq": 3}

    again = client.get(f"{CHANGES}?since=3", headers=device_b["headers"]).json()
    assert again == {"changes": [], "next": 3, "more": False}

    # A later change is read once, from the stored cursor, and not again afterwards.
    _append(app, alice, "d.flac")
    later = client.get(f"{CHANGES}?since=3", headers=device_b["headers"]).json()
    assert _names(later) == ["d.flac"]
    assert later["next"] == 4
    assert client.get(f"{CHANGES}?since=4", headers=device_b["headers"]).json()["changes"] == []

    # Device A keeps its own position, independent of device B.
    assert client.get(CURSOR, headers=device_a["headers"]).json() == {"seq": 0}


def test_paging_follows_next_to_the_end(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    for index in range(5):
        _append(app, alice, f"{index}.flac")

    first = client.get(f"{CHANGES}?since=0&limit=2", headers=device["headers"]).json()
    assert [c["seq"] for c in first["changes"]] == [1, 2]
    assert first["more"] is True
    assert first["next"] == 2

    seen: list[int] = [c["seq"] for c in first["changes"]]
    since = first["next"]
    while True:
        page = client.get(f"{CHANGES}?since={since}&limit=2", headers=device["headers"]).json()
        seen.extend(c["seq"] for c in page["changes"])
        since = page["next"]
        if not page["more"]:
            break
    assert seen == [1, 2, 3, 4, 5]
    assert since == 5


def test_empty_journal_returns_an_empty_page(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    body = client.get(CHANGES, headers=device["headers"]).json()
    assert body == {"changes": [], "next": 0, "more": False}


def test_changes_of_other_users_never_appear(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    bob = make_user(app, "bob")
    alice_device = make_device(app, alice)
    bob_device = make_device(app, bob)
    _append(app, alice, "alice.flac")
    _append(app, bob, "bob-1.flac")
    _append(app, bob, "bob-2.flac")

    alice_view = client.get(f"{CHANGES}?since=0", headers=alice_device["headers"]).json()
    assert _names(alice_view) == ["alice.flac"]
    bob_view = client.get(f"{CHANGES}?since=0", headers=bob_device["headers"]).json()
    assert _names(bob_view) == ["bob-1.flac", "bob-2.flac"]
    # Sequence numbers are per user: bob's rows start at 1 as well.
    assert [c["seq"] for c in bob_view["changes"]] == [1, 2]


def test_long_poll_returns_a_change_appended_while_waiting(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    timer = threading.Timer(0.3, _append, args=(app, alice, "late.flac"))
    timer.start()
    try:
        started = time.monotonic()
        response = client.get(f"{CHANGES}?since=0&wait=5", headers=device["headers"])
        elapsed = time.monotonic() - started
    finally:
        timer.join()

    assert response.status_code == 200
    body = response.json()
    assert _names(body) == ["late.flac"]
    assert body["next"] == 1
    assert elapsed < 3


def test_long_poll_without_changes_times_out_empty(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    started = time.monotonic()
    response = client.get(f"{CHANGES}?since=0&wait=1", headers=device["headers"])
    elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert response.json() == {"changes": [], "next": 0, "more": False}
    assert elapsed >= 0.9


def test_wait_accepts_decimals(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    response = client.get(f"{CHANGES}?wait=0.2", headers=device["headers"])
    assert response.status_code == 200
    assert response.json()["changes"] == []


def test_cursor_defaults_to_zero_and_round_trips(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    assert client.get(CURSOR, headers=device["headers"]).json() == {"seq": 0}

    # Storing 0 is allowed on an empty journal.
    assert client.put(CURSOR, json={"seq": 0}, headers=device["headers"]).status_code == 204

    _append(app, alice, "a.flac")
    _append(app, alice, "b.flac")
    assert client.put(CURSOR, json={"seq": 2}, headers=device["headers"]).status_code == 204
    assert client.get(CURSOR, headers=device["headers"]).json() == {"seq": 2}

    # Moving the cursor again replaces the stored value.
    assert client.put(CURSOR, json={"seq": 1}, headers=device["headers"]).status_code == 204
    assert client.get(CURSOR, headers=device["headers"]).json() == {"seq": 1}


def test_cursor_beyond_the_newest_change_is_refused(
    app: Starlette, client: TestClient, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    _append(app, alice, "a.flac")

    response = client.put(CURSOR, json={"seq": 2}, headers=device["headers"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
    assert client.get(CURSOR, headers=device["headers"]).json() == {"seq": 0}

    empty_user = make_user(app, "carol")
    empty_device = make_device(app, empty_user)
    response = client.put(CURSOR, json={"seq": 1}, headers=empty_device["headers"])
    assert response.status_code == 400


@pytest.mark.parametrize(
    "body",
    [{"seq": -1}, {"seq": "2"}, {"seq": 1.5}, {"seq": True}, {}, []],
)
def test_cursor_body_must_be_a_non_negative_integer(
    app: Starlette,
    client: TestClient,
    make_user: MakeUser,
    make_device: MakeDevice,
    body: Any,
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    response = client.put(CURSOR, json=body, headers=device["headers"])
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


@pytest.mark.parametrize(
    "query",
    [
        "since=-1",
        "since=abc",
        "since=1.5",
        "since=",
        "limit=0",
        "limit=1001",
        "limit=many",
        "wait=31",
        "wait=-1",
        "wait=abc",
        "wait=nan",
        "wait=inf",
    ],
)
def test_bad_query_values_are_refused_and_name_the_parameter(
    app: Starlette,
    client: TestClient,
    make_user: MakeUser,
    make_device: MakeDevice,
    query: str,
) -> None:
    alice = make_user(app, "alice")
    device = make_device(app, alice)
    response = client.get(f"{CHANGES}?{query}", headers=device["headers"])
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "bad_request"
    assert query.split("=")[0] in error["message"]


def test_the_routes_refuse_a_request_without_a_token(app: Starlette, client: TestClient) -> None:
    assert client.get(CHANGES).status_code == 401
    assert client.get(CURSOR).status_code == 401
    response = client.put(CURSOR, json={"seq": 0})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

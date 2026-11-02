"""Device list and revocation (milestone 124.3)."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.testclient import TestClient

from conftest import MakeDevice, MakeUser


def test_list_shows_the_live_devices_and_marks_the_current_one(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    current = make_device(app, alice, name="this laptop", kind="desktop")
    other = make_device(app, alice, name="phone", kind="phone")

    response = client.get("/api/v1/devices", headers=current["headers"])
    assert response.status_code == 200
    devices = response.json()["devices"]
    # Devices created within the same clock tick may come in either order.
    by_id = {d["device_id"]: d for d in devices}
    assert set(by_id) == {current["device_id"], other["device_id"]}
    assert by_id[current["device_id"]]["current"] is True
    assert by_id[other["device_id"]]["current"] is False
    assert by_id[other["device_id"]]["name"] == "phone"
    assert by_id[other["device_id"]]["kind"] == "phone"
    assert set(devices[0]) == {
        "device_id",
        "name",
        "kind",
        "created_at_utc",
        "last_seen_utc",
        "current",
    }


def test_list_needs_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/devices")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_revoking_another_device_signs_it_out(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    current = make_device(app, alice)
    other = make_device(app, alice, name="phone", kind="phone")

    response = client.delete(f"/api/v1/devices/{other['device_id']}", headers=current["headers"])
    assert response.status_code == 204

    # The revoked device's token no longer works.
    assert client.get("/api/v1/devices", headers=other["headers"]).status_code == 401
    # The list no longer shows it.
    listed = client.get("/api/v1/devices", headers=current["headers"]).json()["devices"]
    assert [d["device_id"] for d in listed] == [current["device_id"]]


def test_revoking_is_refused_for_unknown_or_already_revoked_devices(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    current = make_device(app, alice)
    other = make_device(app, alice, name="phone", kind="phone")

    unknown = client.delete("/api/v1/devices/" + "0" * 32, headers=current["headers"])
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"

    assert (
        client.delete(
            f"/api/v1/devices/{other['device_id']}", headers=current["headers"]
        ).status_code
        == 204
    )
    again = client.delete(f"/api/v1/devices/{other['device_id']}", headers=current["headers"])
    assert again.status_code == 404


def test_another_users_device_looks_unknown(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    bob = make_user(app, "bob")
    alice_device = make_device(app, alice)
    bob_device = make_device(app, bob)

    response = client.delete(
        f"/api/v1/devices/{bob_device['device_id']}", headers=alice_device["headers"]
    )
    assert response.status_code == 404
    # Bob's device still works.
    assert client.get("/api/v1/devices", headers=bob_device["headers"]).status_code == 200


def test_a_device_can_revoke_itself(
    client: TestClient, app: Starlette, make_user: MakeUser, make_device: MakeDevice
) -> None:
    alice = make_user(app, "alice")
    only = make_device(app, alice)
    assert (
        client.delete(f"/api/v1/devices/{only['device_id']}", headers=only["headers"]).status_code
        == 204
    )
    assert client.get("/api/v1/devices", headers=only["headers"]).status_code == 401

from __future__ import annotations

from starlette.testclient import TestClient

from mtee_remote import __version__


def test_health_needs_no_token(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_unknown_route_without_token_is_refused(client: TestClient) -> None:
    response = client.get("/nothing-here")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

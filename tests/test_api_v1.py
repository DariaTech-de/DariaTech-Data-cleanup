from __future__ import annotations

from fastapi.testclient import TestClient

from app.asgi import app


def test_capabilities_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v1"
    assert payload["background_scans"] is True

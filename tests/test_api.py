from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app.api_v1 as api_v1
from app.asgi import app
from app.enterprise_store import EnterpriseStore
from app.job_runner import ScanJobRunner


def test_capabilities_advertises_new_features() -> None:
    client = TestClient(app)
    payload = client.get("/api/v1/capabilities").json()
    assert payload["api_version"] == "v1"
    assert payload["consolidation"] is True
    assert payload["live_progress"] is True


def test_sync_scan_endpoint_finds_duplicates(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("identical", encoding="utf-8")
    (tmp_path / "b.txt").write_text("identical", encoding="utf-8")

    client = TestClient(app)
    response = client.post("/api/scan", json={"folders": [str(tmp_path)], "include_all_files": True})
    assert response.status_code == 200
    assert response.json()["summary"]["duplicate_groups"] == 1


def test_sync_consolidate_endpoint(tmp_path: Path) -> None:
    src = tmp_path / "A"
    src.mkdir()
    (src / "a.txt").write_text("identical", encoding="utf-8")
    (src / "b.txt").write_text("identical", encoding="utf-8")
    target = tmp_path / "Clean"

    client = TestClient(app)
    response = client.post(
        "/api/consolidate",
        json={"folders": [str(src)], "target": str(target), "include_all_files": True, "structure": "flat"},
    )
    assert response.status_code == 200
    assert response.json()["summary"]["output_files"] == 1


def test_consolidate_endpoint_rejects_bad_target(tmp_path: Path) -> None:
    src = tmp_path / "A"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/consolidate",
        json={"folders": [str(src)], "target": str(src / "inside"), "include_all_files": True},
    )
    assert response.status_code == 400


def test_profiles_roundtrip(tmp_path: Path, monkeypatch) -> None:
    runner = ScanJobRunner(store=EnterpriseStore(tmp_path / "profiles.sqlite3"), workers=1)
    monkeypatch.setattr(api_v1, "runner", runner)

    client = TestClient(app)
    created = client.post("/api/v1/profiles", json={"name": "Kunde Mueller", "config": {"folders": ["X"]}})
    assert created.status_code == 201

    listed = client.get("/api/v1/profiles").json()["items"]
    assert any(profile["name"] == "Kunde Mueller" for profile in listed)

    deleted = client.delete("/api/v1/profiles/Kunde Mueller")
    assert deleted.status_code == 200

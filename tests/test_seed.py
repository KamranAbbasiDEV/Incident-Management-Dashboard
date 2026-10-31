from fastapi.testclient import TestClient

from app.main import app
from app.seed_demo import main as seed


def test_seeding_empty_db_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("INCIDENT_DB_PATH", str(tmp_path / "seed.db"))
    assert seed() == 0
    assert seed() == 0
    with TestClient(app) as client:
        incidents = client.get("/api/incidents").json()
        assert incidents["total"] == 8
        assert all("Synthetic:" in x["description"] for x in incidents["items"])
        metrics = client.get("/api/metrics").json()
        assert metrics["resolved"] == 2
        assert metrics["active"] == 6

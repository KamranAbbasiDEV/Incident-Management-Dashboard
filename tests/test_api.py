"""End-to-end API tests: temporary SQLite per test, no external services."""
import csv
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INCIDENT_DB_PATH", str(tmp_path / "isolated-test.db"))
    with TestClient(app) as browser:
        yield browser


def incident(title="API latency spike", severity="P2", service="Payments"):
    return {
        "title": title,
        "description": "Synthetic example incident. No customer data.",
        "severity": severity,
        "service": service,
        "owner": "Support Team",
    }


def create(client, **changes):
    payload = {**incident(), **changes}
    response = client.post("/api/incidents", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_root_serves_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "IncidentOps" in response.text
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_health_endpoint(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_empty_metrics(client):
    data = client.get("/api/metrics").json()
    assert data["total"] == 0
    assert data["active"] == 0
    assert data["mean_time_to_resolve_hours"] is None


def test_create_and_read_incident(client):
    item = create(client)
    assert item["id"] == 1
    assert item["status"] == "open"
    assert item["severity"] == "P2"
    result = client.get("/api/incidents/1")
    assert result.status_code == 200
    assert result.json()["description"].startswith("Synthetic")


def test_create_rejects_invalid_data(client):
    assert client.post("/api/incidents", json=incident(title="x")).status_code == 422
    assert client.post("/api/incidents", json=incident(severity="P0")).status_code == 422
    assert client.post("/api/incidents", json={**incident(), "is_admin": True}).status_code == 422


def test_missing_incident_returns_404(client):
    assert client.get("/api/incidents/999").status_code == 404
    assert client.patch("/api/incidents/999", json={"owner": "Test"}).status_code == 404
    assert client.get("/api/incidents/999/events").status_code == 404


def test_list_filters_and_text_search(client):
    create(client, title="Checkout API failing", severity="P1", service="Orders")
    create(client, title="Email queue delayed", severity="P3", service="Mail")
    assert client.get("/api/incidents").json()["total"] == 2
    assert client.get("/api/incidents", params={"severity": "P1"}).json()["total"] == 1
    assert client.get("/api/incidents", params={"q": "mail"}).json()["total"] == 1
    assert client.get("/api/incidents", params={"q": "checkout"}).json()["items"][0]["title"] == "Checkout API failing"
    assert client.get("/api/incidents", params={"status": "resolved"}).json()["total"] == 0


def test_filter_validation(client):
    assert client.get("/api/incidents", params={"limit": 0}).status_code == 422
    assert client.get("/api/incidents", params={"limit": 201}).status_code == 422
    assert client.get("/api/incidents", params={"status": "deleted"}).status_code == 422


def test_status_transitions_and_reopening(client):
    item = create(client)
    identity = item["id"]
    invalid = client.patch(f"/api/incidents/{identity}", json={"status": "mitigated"})
    assert invalid.status_code == 409
    for status in ("investigating", "mitigated", "resolved"):
        response = client.patch(f"/api/incidents/{identity}", json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status
    assert response.json()["resolved_at"] is not None
    reopened = client.patch(f"/api/incidents/{identity}", json={"status": "investigating"})
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None


def test_invalid_updates(client):
    identity = create(client)["id"]
    assert client.patch(f"/api/incidents/{identity}", json={}).status_code == 400
    assert client.patch(f"/api/incidents/{identity}", json={"status": None}).status_code == 422
    assert client.patch(f"/api/incidents/{identity}", json={"owner": 2}).status_code == 422


def test_update_owner_and_severity(client):
    identity = create(client)["id"]
    response = client.patch(f"/api/incidents/{identity}", json={"owner": "SRE", "severity": "P1"})
    assert response.status_code == 200
    assert response.json()["owner"] == "SRE"
    assert response.json()["severity"] == "P1"
    messages = [x["detail"] for x in client.get(f"/api/incidents/{identity}/events").json()["items"]]
    assert any("severity:" in msg for msg in messages)


def test_notes_and_timeline(client):
    identity = create(client)["id"]
    assert client.post(f"/api/incidents/{identity}/notes", json={"note": "hi"}).status_code == 422
    response = client.post(f"/api/incidents/{identity}/notes", json={"note": "Reviewed synthetic service logs"})
    assert response.status_code == 201
    events = client.get(f"/api/incidents/{identity}/events").json()["items"]
    assert events[0]["event_type"] == "note"
    assert events[0]["detail"] == "Reviewed synthetic service logs"
    assert events[-1]["event_type"] == "created"


def test_metrics_reflect_resolutions(client):
    first = create(client, severity="P1")
    create(client, title="Medium priority issue", severity="P3")
    data = client.get("/api/metrics").json()
    assert (data["total"], data["active"], data["resolved"], data["p1_active"]) == (2, 2, 0, 1)
    response = client.patch(f"/api/incidents/{first['id']}", json={"status": "resolved"})
    assert response.status_code == 200
    data = client.get("/api/metrics").json()
    assert (data["active"], data["resolved"], data["p1_active"]) == (1, 1, 0)
    assert data["mean_time_to_resolve_hours"] >= 0


def test_csv_export_and_formula_defense(client):
    create(client, title="=2+2 malicious test", service="@cmd", owner="+fake")
    response = client.get("/api/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["title"].startswith("'=")
    assert rows[0]["service"].startswith("'@")
    assert rows[0]["owner"].startswith("'+")


def test_csv_export_empty(client):
    response = client.get("/api/export.csv")
    assert response.status_code == 200
    assert "id,title,service" in response.text


def test_data_isolated_between_db_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("INCIDENT_DB_PATH", str(tmp_path / "db-1.sqlite"))
    with TestClient(app) as first:
        create(first)
        assert first.get("/api/incidents").json()["total"] == 1
    monkeypatch.setenv("INCIDENT_DB_PATH", str(tmp_path / "db-2.sqlite"))
    with TestClient(app) as second:
        assert second.get("/api/incidents").json()["total"] == 0

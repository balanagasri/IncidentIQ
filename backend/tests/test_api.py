from fastapi.testclient import TestClient
from app.main import app


def test_health_discloses_configuration_status_not_secret():
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert "hindsight_configured" in response.json()
    assert "api_key" not in response.json()


def test_demo_scenario_is_explicitly_synthetic():
    with TestClient(app) as client:
        response = client.get("/api/demo/incidents")
    assert response.status_code == 200
    assert response.json()["synthetic"] is True
    assert response.json()["historical_count"] >= 3


def test_first_demo_incident_creates_with_timestamp():
    with TestClient(app) as client:
        response = client.post("/api/demo/first")
    assert response.status_code == 201
    assert response.json()["id"] == "INC-DEMO-FIRST"
    assert response.json()["timestamp"].startswith("2026-09-28")


def test_incident_and_action_api_workflow():
    with TestClient(app) as client:
        created = client.post("/api/incidents", json={
            "title": "API workflow check", "service": "checkout-api",
            "symptoms": ["checkout timeout"], "deployment": "checkout-test",
        })
        assert created.status_code == 201
        incident_id = created.json()["id"]
        action = client.post(f"/api/incidents/{incident_id}/actions", json={
            "action": "Check connection pool utilization", "outcome": "inconclusive", "notes": "Need dashboard evidence",
        })
        assert action.status_code == 201
        loaded = client.get(f"/api/incidents/{incident_id}")
        assert loaded.status_code == 200
        assert loaded.json()["actions"][0]["outcome"] == "inconclusive"

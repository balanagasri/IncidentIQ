from fastapi.testclient import TestClient
import app.main as main
from app.main import app
from app.schemas import Recommendation


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


def test_analyze_api_returns_validated_hindsight_citation_ids(monkeypatch):
    async def recall(query):
        return [{
            "id": "hindsight-memory-041",
            "metadata": {"incident_id": "INC-2026-041", "service": "checkout-api"},
            "text": "Confirmed root cause: undersized connection pool; increasing it succeeded.",
        }]

    async def recommend(incident, memories):
        result = Recommendation.model_validate({
            "summary": "Inspect connection-pool utilization.",
            "hypotheses": [],
            "recommended_steps": [],
            "safety_notes": [],
            "evidence_memory_ids": ["INC-2026-041"],
            "memory_evidence": [{
                "incident_id": "INC-2026-041",
                "reason": "Selected memory citation.",
                "outcome_summary": "Increasing the connection pool succeeded.",
            }],
            "unknowns": [],
        })
        return result, {"recalled": 1, "selected_for_reasoning": 1, "llm_payload_characters": 100}

    monkeypatch.setattr(main.hindsight, "recall", recall)
    monkeypatch.setattr(main, "recommend", recommend)

    with TestClient(app) as client:
        client.post("/api/demo/first")
        response = client.post("/api/incidents/INC-DEMO-FIRST/analyze")

    assert response.status_code == 200
    assert response.json()["recommendation"]["evidence_memory_ids"] == ["INC-2026-041"]
    assert response.json()["recommendation"]["memory_evidence"][0]["incident_id"] == "INC-2026-041"

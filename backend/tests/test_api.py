from fastapi.testclient import TestClient
import app.main as main
from app.main import app
from app.schemas import Recommendation
from app.models import RecommendationFeedback
from uuid import uuid4


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


def test_duplicate_action_submission_id_does_not_duplicate_engineer_outcome():
    with TestClient(app) as client:
        created = client.post("/api/incidents", json={"title": "Idempotency check", "service": "checkout-api"})
        incident_id = created.json()["id"]
        body = {"action": "Inspect pool", "outcome": "failed", "notes": "No saturation", "submission_id": f"submission-test-{uuid4()}"}
        first = client.post(f"/api/incidents/{incident_id}/actions", json=body)
        duplicate = client.post(f"/api/incidents/{incident_id}/actions", json=body)
        loaded = client.get(f"/api/incidents/{incident_id}")

    assert first.status_code == duplicate.status_code == 201
    assert first.json()["id"] == duplicate.json()["id"]
    assert len(loaded.json()["actions"]) == 1


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
    assert response.json()["similar_incidents"][0]["incident_id"] == "INC-2026-041"
    assert response.json()["similar_incidents"][0]["memory_id"] == "hindsight-memory-041"


def test_evaluation_endpoint_uses_recall_service_and_persists_actual_result(monkeypatch):
    async def recall(query):
        if "55P03" in query:
            incident_id = "INC-2026-037"
        elif "TLS handshake failed" in query:
            incident_id = "INC-2026-029"
        elif "consumer heartbeat missed" in query:
            incident_id = "INC-2026-021"
        elif "TaxAllocationInvariant" in query:
            return []
        else:
            incident_id = "INC-2026-041"
        return [{"metadata": {"incident_id": incident_id}, "text": f"Incident {incident_id}. Symptoms: checkout timeout. Actions: pool check successful."}]

    monkeypatch.setattr(main.hindsight, "recall", recall)
    with TestClient(app) as client:
        response = client.post("/api/evaluations/run")
        latest = client.get("/api/evaluations/latest")

    assert response.status_code == 201
    result = response.json()["result"]
    assert result["memory_assisted"]["retrieval_recall"] == 1.0
    assert result["memory_assisted"]["failed_cases"] == 0
    assert latest.json()["id"] == response.json()["id"]


def test_seed_records_retention_only_after_real_adapter_returns(monkeypatch):
    async def retain(_incident, document_id):
        return {"document_id": document_id}

    monkeypatch.setattr(main.hindsight, "retain", retain)
    with TestClient(app) as client:
        response = client.post("/api/demo/seed-hindsight")
        analytics = client.get("/api/analytics")

    assert response.status_code == 200
    assert response.json()["seeded"] == 4
    assert analytics.json()["successful_hindsight_retains"] >= 4
    assert analytics.json()["distinct_incidents_with_retained_outcomes"] >= 4


def test_feedback_upserts_one_latest_decision_per_analysis(monkeypatch):
    async def recall(_query):
        return []

    async def recommend(_incident, _memories):
        return Recommendation.model_validate({
            "summary": "Inspect current request errors.", "hypotheses": [], "recommended_steps": [],
            "safety_notes": [], "evidence_memory_ids": [], "memory_evidence": [], "unknowns": ["Current error rate"],
        }), {"recalled": 0, "selected_for_reasoning": 0, "llm_payload_characters": 1}

    monkeypatch.setattr(main.hindsight, "recall", recall)
    monkeypatch.setattr(main, "recommend", recommend)
    with TestClient(app) as client:
        created = client.post("/api/incidents", json={"title": "Feedback audit", "service": "checkout-api"})
        analysis = client.post(f"/api/incidents/{created.json()['id']}/analyze")
        analysis_id = analysis.json()["analysis_id"]
        client.post(f"/api/analyses/{analysis_id}/feedback", json={"accepted": True, "note": "Initial"})
        final = client.post(f"/api/analyses/{analysis_id}/feedback", json={"accepted": False, "note": "Needs better evidence"})
        metrics = client.get("/api/analytics")

    assert final.json()["accepted"] is False
    assert final.json()["note"] == "Needs better evidence"
    assert metrics.json()["recommendation_feedback"] == {"accepted": 0, "rejected": 1, "recorded": 1}


def test_postmortem_draft_can_be_edited_finalized_and_retained_once(monkeypatch):
    retained = []

    async def retain(incident, document_id):
        retained.append(document_id)
        return {"stored": True}

    monkeypatch.setattr(main.hindsight, "retain", retain)
    with TestClient(app) as client:
        created = client.post("/api/incidents", json={
            "title": "Postmortem workflow", "service": "checkout-api", "symptoms": ["checkout timeout"],
        })
        incident_id = created.json()["id"]
        client.post(f"/api/incidents/{incident_id}/actions", json={
            "action": "Restart pod", "outcome": "failed", "notes": "Timeout returned", "submission_id": f"postmortem-action-{uuid4()}",
        })
        generated = client.post(f"/api/incidents/{incident_id}/postmortem/generate")
        edited_text = generated.json()["markdown"] + "\n## Engineer review\nReviewed by on-call.\n"
        saved = client.put(f"/api/incidents/{incident_id}/postmortem", json={"markdown": edited_text})
        finalized = client.post(f"/api/incidents/{incident_id}/postmortem/finalize", json={"markdown": edited_text})
        repeated = client.post(f"/api/incidents/{incident_id}/postmortem/finalize", json={"markdown": edited_text})

    assert generated.status_code == 200
    assert generated.json()["report"]["impact"].startswith("Unknown:")
    assert generated.json()["report"]["confirmed_root_cause"].startswith("Unknown:")
    assert generated.json()["report"]["actions"][0]["outcome"] == "failed"
    assert saved.json()["markdown"] == edited_text
    assert finalized.json()["finalized"] is True
    assert repeated.json()["retained_at"] == finalized.json()["retained_at"]
    assert len(retained) == 1
    assert retained[0] == f"incident:{incident_id}"


def test_analysis_reports_hindsight_unavailability_as_structured_api_error(monkeypatch):
    from app.hindsight import HindsightError

    async def recall(_query):
        raise HindsightError("Hindsight recall failed after 3 attempts due to ConnectError")

    monkeypatch.setattr(main.hindsight, "recall", recall)
    with TestClient(app) as client:
        created = client.post("/api/incidents", json={"title": "Hindsight unavailable", "service": "checkout-api"})
        response = client.post(f"/api/incidents/{created.json()['id']}/analyze")

    assert response.status_code == 502
    assert "Hindsight recall failed" in response.json()["detail"]


def test_analysis_reports_llm_unavailability_as_structured_api_error(monkeypatch):
    async def recall(_query):
        return []

    async def recommend(_incident, _memories):
        raise RuntimeError("LLM_API_KEY is required to analyze incidents")

    monkeypatch.setattr(main.hindsight, "recall", recall)
    monkeypatch.setattr(main, "recommend", recommend)
    with TestClient(app) as client:
        created = client.post("/api/incidents", json={"title": "LLM unavailable", "service": "checkout-api"})
        response = client.post(f"/api/incidents/{created.json()['id']}/analyze")

    assert response.status_code == 502
    assert "LLM analysis failed" in response.json()["detail"]

from app.hindsight import HindsightService
from app.agent import _incident_id
from app.main import _memory_service


def test_narrative_preserves_failed_and_successful_actions():
    text = HindsightService._narrative({
        "id": "INC-10", "service": "checkout-api", "actions": [
            {"action": "Restart", "outcome": "failed", "notes": "It returned."},
            {"action": "Raise pool", "outcome": "successful", "notes": "Latency recovered."},
        ]
    })
    assert "Restart: failed" in text
    assert "Raise pool: successful" in text
    assert "confirmed" in text.lower()


def test_recall_payload_requests_raw_chunks_as_object():
    payload = HindsightService._recall_payload("checkout timeouts")
    chunks = payload["include"]["chunks"]

    assert type(chunks) is dict
    assert chunks == {}


def test_memory_id_comes_from_returned_hindsight_result():
    assert _incident_id({"metadata": {"incident_id": "INC-22"}}) == "INC-22"
    assert _incident_id({"text": "Incident INC-23 (2026-08-01) had checkout timeouts"}) == "INC-23"
    assert _incident_id({"text": "No incident identity here"}) == ""


def test_recalled_service_uses_hindsight_provenance():
    assert _memory_service({"metadata": {"service": "payments-worker"}}, "checkout-api") == "payments-worker"
    assert _memory_service({"tags": ["service:payments-gateway"]}, "checkout-api") == "payments-gateway"


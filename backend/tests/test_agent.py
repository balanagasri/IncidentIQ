import json
from types import SimpleNamespace

import pytest

import app.agent as agent
from app.schemas import Recommendation


def _memory(index: int, *, score: int | None = None, text: str | None = None):
    return {
        "id": f"hindsight-memory-{index}",
        "timestamp": f"2026-09-{index + 1:02d}T10:00:00Z",
        "score": score if score is not None else index,
        "metadata": {"incident_id": f"INC-{index:02d}", "service": "checkout-api"},
        "text": text or (
            f"Incident INC-{index:02d} (2026-09-{index + 1:02d}) affected checkout-api at severity SEV-2.\n"
            "Symptoms: checkout timeout; elevated pool wait\n"
            "Error signatures: AcquireTimeout\n"
            "Suspected causes (unconfirmed): pool saturation\n"
            "Attempted interventions and reported outcomes:\n"
            "- Restart service: failed — no change\n"
            "- Increase pool: successful — latency recovered\n"
            "Confirmed root cause: connection pool undersized\n"
            "Resolution: increased pool; resolution time: 12 minutes."
        ),
    }


def _valid_recommendation(incident_id="INC-26"):
    return json.dumps({
        "summary": "Investigate pool saturation using the recalled outcome.",
        "hypotheses": [{
            "cause": "Connection pool saturation",
            "confidence": 0.8,
            "rationale": "The current symptoms resemble a recalled incident.",
            "classification": "HYPOTHESIS",
        }],
        "recommended_steps": [{
            "step": "Inspect connection pool utilization and wait time.",
            "priority": "high",
            "expected_observation": "Pool saturation would coincide with elevated acquisition waits.",
            "safety_note": "Read-only metrics inspection.",
            "evidence_ids": [incident_id, "INC-NOT-IN-RECALL"],
        }],
        "safety_notes": ["Do not restart or change configuration without confirming the cause."],
        "memory_evidence": [{
            "incident_id": incident_id,
            "reason": "Similar symptoms and recorded intervention outcomes.",
            "outcome_summary": "model text is replaced with Hindsight evidence",
        }],
        "unknowns": ["Current pool utilization has not been measured."],
    })


@pytest.mark.asyncio
async def test_recommend_sends_only_bounded_compact_evidence_and_validates_schema(monkeypatch):
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=_valid_recommendation()))])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr(agent, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(
        llm_api_key="test-key", llm_base_url="https://api.groq.com/openai/v1", llm_model="openai/gpt-oss-120b"
    ))
    memories = [_memory(i) for i in range(27)]

    recommendation, stats = await agent.recommend({"id": "INC-CURRENT", "symptoms": ["timeout"]}, memories)

    sent = json.loads(captured["messages"][1]["content"])["hindsight_memories"]
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["schema"] == Recommendation.model_json_schema()
    assert stats["recalled"] == 27
    assert stats["selected_for_reasoning"] == 6
    assert len(sent) == 6
    assert {item["incident_id"] for item in sent} == {f"INC-{i:02d}" for i in range(21, 27)}
    assert sent[0]["provenance"]["memory_id"] == "hindsight-memory-26"
    assert "successful — latency recovered" in sent[0]["evidence_summary"]
    assert "failed — no change" in sent[0]["evidence_summary"]
    assert "suspected causes (unconfirmed)" in sent[0]["evidence_summary"].lower()
    assert recommendation.hypotheses[0].classification == "HYPOTHESIS"
    assert recommendation.recommended_steps[0].evidence_ids == ["INC-26"]
    assert recommendation.memory_evidence[0].outcome_summary == sent[0]["evidence_summary"]
    assert isinstance(recommendation, Recommendation)
    assert stats["llm_payload_characters"] == len(captured["messages"][1]["content"])


def test_select_evidence_deduplicates_incidents_and_truncates_long_fields():
    long_text = (
        "Incident INC-LONG affected checkout-api at severity SEV-2.\n"
        "Symptoms: " + ("prolonged database connection acquisition wait " * 100)
    )
    memories = [
        {"id": "memory-first", "metadata": {"incident_id": "INC-DUP", "service": "checkout-api"}, "text": "Incident INC-DUP affected checkout-api at severity SEV-2."},
        {"id": "memory-duplicate", "metadata": {"incident_id": "INC-DUP", "service": "checkout-api"}, "text": "duplicate result", "score": 99},
        {"id": "memory-long", "metadata": {"incident_id": "INC-LONG", "service": "checkout-api"}, "text": long_text},
    ]

    selected = agent.select_evidence(memories)

    assert [item["incident_id"] for item in selected] == ["INC-DUP", "INC-LONG"]
    long_memory = selected[1]
    assert long_memory["provenance"]["memory_id"] == "memory-long"
    assert len(long_memory["evidence_summary"]) <= agent.MAX_EVIDENCE_SUMMARY_CHARS
    assert long_memory["evidence_summary"].endswith("…")
    assert len(agent.select_evidence(memories, limit=0)) == 0


def test_recommendation_schema_validation_still_rejects_invalid_classification():
    body = json.loads(_valid_recommendation())
    body["hypotheses"][0]["classification"] = "CERTAIN"

    with pytest.raises(Exception):
        Recommendation.model_validate(body)

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


def _valid_recommendation(incident_id="INC-26", evidence_memory_ids=None):
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
        "evidence_memory_ids": evidence_memory_ids if evidence_memory_ids is not None else [incident_id],
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
    payload = json.loads(captured["messages"][1]["content"])
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["schema"] == Recommendation.model_json_schema()
    assert stats["recalled"] == 27
    assert stats["selected_for_reasoning"] == 6
    assert len(sent) == 6
    assert {item["incident_id"] for item in sent} == {f"INC-{i:02d}" for i in range(21, 27)}
    assert sent[0]["provenance"]["memory_id"] == "hindsight-memory-26"
    assert "successful — latency recovered" in sent[0]["evidence_summary"]
    assert "failed — no change" in sent[0]["evidence_summary"]
    assert payload["citation_allowlist"][0]["incident_id"] == "INC-26"
    assert "Increase pool: successful" in payload["citation_allowlist"][0]["relevant_interventions_outcomes"]
    assert "connection-pool statistics" in payload["citation_instruction"]
    assert "MUST cite at least one" in captured["messages"][0]["content"]
    assert "suspected causes (unconfirmed)" in sent[0]["evidence_summary"].lower()
    assert recommendation.hypotheses[0].classification == "HYPOTHESIS"
    assert recommendation.recommended_steps[0].evidence_ids == ["INC-26"]
    assert recommendation.evidence_memory_ids == ["INC-26"]
    assert recommendation.memory_evidence[0].outcome_summary == sent[0]["evidence_summary"]
    assert isinstance(recommendation, Recommendation)
    assert recommendation.model_dump(mode="json")["evidence_memory_ids"] == ["INC-26"]
    assert stats["llm_payload_characters"] == len(captured["messages"][1]["content"])


@pytest.mark.asyncio
@pytest.mark.parametrize(("returned_ids", "expected_ids"), [
    (["INC-26", "INC-NOT-SELECTED", "INC-26"], ["INC-26"]),
    ([], ["INC-26"]),
])
async def test_recommendation_citations_are_allowlisted_and_no_citation_is_preserved(
    monkeypatch, returned_ids, expected_ids
):
    async def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=_valid_recommendation(evidence_memory_ids=returned_ids)
        ))])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr(agent, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(
        llm_api_key="test-key", llm_base_url="https://api.groq.com/openai/v1", llm_model="openai/gpt-oss-120b"
    ))

    recommendation, _ = await agent.recommend({"id": "INC-CURRENT"}, [_memory(26)])

    assert recommendation.evidence_memory_ids == expected_ids
    assert [item.incident_id for item in recommendation.memory_evidence] == expected_ids
    serialized = recommendation.model_dump(mode="json")
    assert Recommendation.model_validate(serialized).model_dump(mode="json") == serialized


@pytest.mark.asyncio
async def test_empty_model_citations_fall_back_to_relevant_selected_intervention(monkeypatch):
    async def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=_valid_recommendation(evidence_memory_ids=[])
        ))])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr(agent, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(
        llm_api_key="test-key", llm_base_url="https://api.groq.com/openai/v1", llm_model="openai/gpt-oss-120b"
    ))

    recommendation, _ = await agent.recommend({"id": "INC-CURRENT"}, [_memory(26)])

    assert recommendation.evidence_memory_ids == ["INC-26"]
    assert recommendation.memory_evidence[0].incident_id == "INC-26"
    assert "deterministic relevance check" in recommendation.memory_evidence[0].reason


@pytest.mark.asyncio
async def test_empty_model_citations_stay_empty_without_meaningful_support(monkeypatch):
    async def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=_valid_recommendation(evidence_memory_ids=[])
        ))])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr(agent, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(
        llm_api_key="test-key", llm_base_url="https://api.groq.com/openai/v1", llm_model="openai/gpt-oss-120b"
    ))
    unrelated = _memory(7, text=(
        "Incident INC-07 affected checkout-api at severity SEV-2.\n"
        "Symptoms: browser cache rendering stale product images\n"
        "Attempted interventions and reported outcomes:\n- Clear browser cache: successful — images refreshed\n"
        "Confirmed root cause: stale browser cache\nResolution: cache cleared"
    ))

    recommendation, _ = await agent.recommend({"id": "INC-CURRENT"}, [unrelated])

    assert recommendation.evidence_memory_ids == []
    assert recommendation.memory_evidence == []


@pytest.mark.asyncio
async def test_invalid_nonempty_citations_are_removed_without_fallback(monkeypatch):
    async def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=_valid_recommendation(evidence_memory_ids=["INC-NOT-SELECTED"])
        ))])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr(agent, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(
        llm_api_key="test-key", llm_base_url="https://api.groq.com/openai/v1", llm_model="openai/gpt-oss-120b"
    ))

    recommendation, _ = await agent.recommend({"id": "INC-CURRENT"}, [_memory(26)])

    assert recommendation.evidence_memory_ids == []
    assert recommendation.memory_evidence == []


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


def test_fallback_never_creates_ids_missing_from_selected_hindsight_results():
    recommendation = Recommendation.model_validate_json(_valid_recommendation(evidence_memory_ids=[]))
    selected_without_incident_id = [{
        "incident_id": "",
        "evidence_summary": "Symptoms: connection pool saturation; increase pool: successful.",
    }]

    assert agent._fallback_evidence_ids(recommendation, selected_without_incident_id) == []

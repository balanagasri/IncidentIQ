import json
import re
from datetime import date, datetime
from typing import Any
from openai import AsyncOpenAI
from .config import get_settings
from .schemas import MemoryEvidence, Recommendation


SYSTEM_PROMPT = """You are IncidentIQ, an incident response assistant. Recommend safe investigation steps, never execute remediation.
Separate supplied FACTS from HYPOTHESES. Historical evidence may only come from the Hindsight memories supplied in this request.
Do not invent incident IDs, outcomes, confirmed causes, or memory evidence. When evidence is absent, say so and list unknowns.
Only cite incident IDs present in the supplied evidence, and only describe outcomes stated there. Prefer read-only diagnostics before changes.
Treat `suspected_causes_unconfirmed` as hypotheses, and `confirmed_root_cause`/`resolution` as facts only when explicitly present. Do not promote hypotheses to facts.
For `evidence_memory_ids`, cite exact incident IDs from `citation_allowlist` that directly support one or more actual recommended investigation steps. Explicitly connect each cited memory's intervention/outcome evidence to the step it supports. When a selected memory contains relevant evidence, you MUST cite at least one such memory; you may cite multiple. Similarity alone is not support: do not cite a memory unless its facts or intervention outcome meaningfully support a step. Never invent or alter an ID. Use an empty list only when no selected memory genuinely supports any recommended step.
Return only an object matching the supplied Recommendation output schema, with every required field."""

MAX_REASONING_MEMORIES = 6
MAX_EVIDENCE_SUMMARY_CHARS = 1400


async def recommend(incident: dict, evidence: list[dict]) -> tuple[Recommendation, dict[str, int]]:
    settings = get_settings()
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required to analyze incidents")
    selected = select_evidence(evidence)
    allowed_evidence_memory_ids = list(dict.fromkeys(
        _incident_id(memory) for memory in selected if _incident_id(memory)
    ))
    citation_allowlist = [
        {
            "incident_id": memory["incident_id"],
            "memory_id": (memory.get("provenance") or {}).get("memory_id"),
            "evidence_summary": memory["evidence_summary"],
            "relevant_interventions_outcomes": _intervention_outcomes(memory["evidence_summary"]),
        }
        for memory in selected if memory.get("incident_id")
    ]
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    payload = {
        "current_incident": incident,
        "hindsight_memories": selected,
        "allowed_evidence_memory_ids": allowed_evidence_memory_ids,
        "citation_allowlist": citation_allowlist,
        "citation_instruction": (
            "Compare each recommended investigation step with the citation allowlist. "
            "For example, if a step investigates connection-pool statistics and a selected memory "
            "records pool saturation resolved by increasing pool capacity, cite that incident ID. "
            "Cite only when the historical evidence supports the step, not merely because symptoms are similar."
        ),
    }
    user_content = json.dumps(payload, default=str)
    completion = await client.chat.completions.create(
        model=settings.llm_model,
        temperature=0.15,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "incidentiq_recommendation",
                "strict": False,
                "schema": Recommendation.model_json_schema(),
            },
        },
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
    )
    raw = completion.choices[0].message.content or "{}"
    result = Recommendation.model_validate_json(raw)
    by_id = {_incident_id(m): m for m in selected if _incident_id(m)}
    allowed_ids = set(by_id)
    model_returned_citations = bool(result.evidence_memory_ids)
    result.evidence_memory_ids = list(dict.fromkeys(
        memory_id for memory_id in result.evidence_memory_ids if memory_id in allowed_ids
    ))
    citation_source = "model"
    if not model_returned_citations:
        result.evidence_memory_ids = _fallback_evidence_ids(result, selected)
        if result.evidence_memory_ids:
            citation_source = "deterministic relevance check"
    result.memory_evidence = [
        MemoryEvidence(
            incident_id=memory_id,
            reason=("Selected Hindsight memory matched to a recommended investigation step by a "
                    f"{citation_source}."),
            outcome_summary=str(by_id[memory_id].get("evidence_summary")
                                or by_id[memory_id].get("text")
                                or by_id[memory_id].get("content")
                                or "Hindsight returned this incident memory."),
        )
        for memory_id in result.evidence_memory_ids
    ]
    for step in result.recommended_steps:
        step.evidence_ids = [i for i in step.evidence_ids if i in allowed_ids]
    return result, {
        "recalled": len(evidence),
        "selected_for_reasoning": len(selected),
        "llm_payload_characters": len(user_content),
    }


_STOPWORDS = {
    "about", "after", "again", "also", "an", "and", "are", "as", "at", "be", "before", "by",
    "cause", "confirmed", "current", "during", "for", "from", "had", "has", "have", "in", "into",
    "is", "it", "its", "may", "memory", "of", "on", "or", "our", "record", "reported", "resolve",
    "resolved", "resolution", "root", "service", "should", "similar", "step", "symptom", "system", "the",
    "their", "this", "through", "to", "using", "was", "were", "what", "when", "which", "with", "would",
    "incident", "intervention", "interventions", "outcome", "outcomes", "successful", "failed", "unknown",
    "check", "checking", "inspect", "inspecting", "investigate", "investigating", "examine", "examining",
    "statistics", "statistic", "metric", "metrics", "data", "evidence", "history", "historical", "recommendation",
}


def _tokens(value: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        if len(token) < 3 or token in _STOPWORDS:
            continue
        if token.endswith("ies") and len(token) > 5:
            token = token[:-3] + "y"
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def _intervention_outcomes(summary: str) -> str:
    match = re.search(r"Interventions and outcomes:\s*(.*?)(?=\s+(?:Confirmed root cause|Resolution):|$)", summary, re.I)
    return match.group(1).strip() if match else ""


def _fallback_evidence_ids(recommendation: Recommendation, selected: list[dict[str, Any]]) -> list[str]:
    """Cite only selected memories with meaningful overlap to an actual recommended step."""
    recommendation_text = " ".join(
        [recommendation.summary]
        + [f"{step.step} {step.expected_observation}" for step in recommendation.recommended_steps]
    )
    recommendation_tokens = _tokens(recommendation_text)
    ranked: list[tuple[int, int, str]] = []
    for memory in selected:
        incident_id = str(memory.get("incident_id") or "")
        summary = str(memory.get("evidence_summary") or "")
        if not incident_id or not summary:
            continue
        overlap = recommendation_tokens & _tokens(summary)
        # Two shared substantive terms provide clear textual grounding. A single highly
        # specific term is sufficient only alongside an explicitly recorded intervention outcome.
        has_outcome = bool(re.search(r"\b(successful|failed|inconclusive)\b", summary, re.I))
        specific_anchor = overlap & {"connection", "pool", "deadlock", "certificate", "gateway", "queue", "dns", "tls", "throttle", "replica", "lock", "token", "credential", "timeout"}
        if len(overlap) < 2 and not (specific_anchor and has_outcome):
            continue
        ranked.append((len(overlap), int(has_outcome), incident_id))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return list(dict.fromkeys(item[2] for item in ranked[:2]))


def select_evidence(memories: list[dict[str, Any]], limit: int = MAX_REASONING_MEMORIES) -> list[dict[str, Any]]:
    """Rank and compact Hindsight results for the LLM; UI evidence remains untouched."""
    if limit <= 0:
        return []
    ranked = sorted(enumerate(memories), key=lambda pair: (-_relevance(pair[1]), pair[0]))
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, memory in ranked:
        incident_id = _incident_id(memory)
        memory_id = _memory_id(memory)
        identity = incident_id or memory_id or f"result:{index}"
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(_compact_memory(memory, incident_id, memory_id))
        if len(selected) >= max(0, limit):
            break
    return selected


def _relevance(memory: dict[str, Any]) -> float:
    for key in ("score", "final_score", "relevance"):
        value = memory.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    return 0.0


def _memory_id(memory: dict[str, Any]) -> str:
    metadata = memory.get("metadata") or {}
    value = (memory.get("memory_id") or memory.get("id") or memory.get("document_id")
             or (metadata.get("memory_id") if isinstance(metadata, dict) else None)
             or (metadata.get("document_id") if isinstance(metadata, dict) else None))
    return str(value) if value is not None else ""


def _compact_memory(memory: dict[str, Any], incident_id: str, memory_id: str) -> dict[str, Any]:
    metadata = memory.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    text = str(memory.get("text") or memory.get("content") or "")
    tags = memory.get("tags") or []
    service = memory.get("service") or metadata.get("service")
    if not service and isinstance(tags, list):
        service = next((str(tag).split(":", 1)[1] for tag in tags if str(tag).startswith("service:")), None)
    if not service:
        match = re.search(r"affected\s+([\w.-]+)\s+at severity", text, re.I)
        service = match.group(1) if match else "unknown"
    timestamp = (memory.get("timestamp") or memory.get("when") or memory.get("created_at")
                 or metadata.get("timestamp") or metadata.get("date"))
    summary = _evidence_summary(memory, text, incident_id, str(service), MAX_EVIDENCE_SUMMARY_CHARS)
    return {
        "incident_id": incident_id,
        "date": _plain(timestamp),
        "service": _clip(str(service), 100),
        "evidence_summary": summary,
        "metadata": {"incident_id": incident_id, "service": _clip(str(service), 100)},
        "provenance": {
            "memory_id": memory_id or None,
            "document_id": _plain(memory.get("document_id") or metadata.get("document_id")),
        },
        "relevance": _relevance(memory),
    }


def _evidence_summary(memory: dict[str, Any], text: str, incident_id: str, service: str, limit: int) -> str:
    metadata = memory.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        rendered = _plain(value)
        if rendered:
            lines.append(f"{label}: {rendered}")

    if incident_id:
        add("Incident ID", incident_id)
    add("Date/time", memory.get("timestamp") or memory.get("when") or memory.get("created_at") or metadata.get("timestamp"))
    add("Service", service)
    deployment = memory.get("deployment") or metadata.get("deployment")
    configuration = memory.get("configuration_context") or metadata.get("configuration_context")
    if deployment or configuration:
        add("Deployment/configuration", "; ".join(filter(None, [_plain(deployment), _plain(configuration)])))
    elif text:
        match = re.search(r"^Deployment/version:\s*(.+)$", text, re.I | re.M)
        if match:
            add("Deployment/configuration", match.group(1))
    for key, label in (("symptoms", "Symptoms"), ("error_signatures", "Error signatures")):
        value = memory.get(key) or metadata.get(key)
        if value:
            add(label, value)
        else:
            match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.I | re.M)
            if match:
                add(label, match.group(1))

    suspected = memory.get("suspected_causes") or metadata.get("suspected_causes")
    if suspected:
        add("Suspected causes (unconfirmed)", suspected)
    else:
        match = re.search(r"^Suspected causes\s*\(unconfirmed\):\s*(.+)$", text, re.I | re.M)
        if match and match.group(1).strip().lower() not in {"none recorded", "none"}:
            add("Suspected causes (unconfirmed)", match.group(1))

    actions = memory.get("actions") or metadata.get("actions")
    if isinstance(actions, list) and actions:
        action_lines = []
        for action in actions[:5]:
            if isinstance(action, dict):
                action_lines.append("; ".join(filter(None, [
                    _plain(action.get("action") or action.get("intervention")),
                    _plain(action.get("outcome")),
                    _plain(action.get("notes")),
                ])))
            else:
                action_lines.append(_plain(action))
        add("Interventions and outcomes", action_lines)
    else:
        action_match = re.search(r"^Attempted interventions and reported outcomes:\s*\n(.*?)(?=^Confirmed root cause:|\Z)", text, re.I | re.M | re.S)
        if action_match:
            add("Interventions and outcomes", action_match.group(1).strip())

    root_cause = memory.get("confirmed_root_cause") or metadata.get("confirmed_root_cause")
    if root_cause:
        add("Confirmed root cause", root_cause)
    else:
        match = re.search(r"^Confirmed root cause:\s*(.+)$", text, re.I | re.M)
        if match:
            add("Confirmed root cause", match.group(1))
    resolution = memory.get("resolution") or metadata.get("resolution")
    if resolution:
        add("Resolution", resolution)
    else:
        match = re.search(r"^Resolution:\s*(.+)$", text, re.I | re.M)
        if match:
            add("Resolution", match.group(1))

    summary = "\n".join(lines) if lines else text
    return _clip(summary, limit)


def _plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(filter(None, (_plain(item) for item in value)))
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_plain(item)}" for key, item in value.items() if item is not None)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _clip(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _incident_id(memory: dict) -> str:
    metadata = memory.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("incident_id"):
        return str(metadata["incident_id"])
    text = str(memory.get("text") or memory.get("content") or "")
    import re
    match = re.search(r"Incident\s+(INC-[A-Za-z0-9_-]+)", text, re.I)
    if match:
        return match.group(1)
    metadata = memory.get("metadata") or {}
    return str(metadata.get("incident_id", "")) if isinstance(metadata, dict) else ""


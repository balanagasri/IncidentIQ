"""Grounded, display-oriented comparison of current and recalled incident signals."""
import re
from typing import Any


_COMPARABLE_LABELS = (
    "Symptoms", "Error signatures", "Deployment/configuration",
    "Interventions and outcomes", "Confirmed root cause", "Resolution",
)
_STOPWORDS = {
    "and", "the", "for", "with", "from", "that", "this", "were", "was", "when",
    "after", "during", "into", "below", "above", "unknown", "none", "recorded",
    "confirmed", "root", "cause", "incident", "service", "checkout", "severity",
}


def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 3 and token not in _STOPWORDS
    }


def _section(summary: str, label: str) -> str:
    labels = "|".join(re.escape(item) for item in _COMPARABLE_LABELS)
    match = re.search(rf"(?:^|\s){re.escape(label)}:\s*(.*?)(?=\s+(?:{labels}):|$)", summary, re.I)
    return match.group(1).strip(" ;") if match else ""


def build_comparisons(current: dict[str, Any], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare comparison cards using only the current incident and selected Hindsight evidence."""
    current_signals = [str(value) for value in (current.get("symptoms") or []) + (current.get("error_signatures") or [])]
    current_terms = _terms(" ".join(current_signals))
    comparisons = []
    for memory in selected:
        summary = str(memory.get("evidence_summary") or "")
        historical_signals = [
            value for value in (_section(summary, "Symptoms"), _section(summary, "Error signatures")) if value
        ]
        historical_terms = _terms(" ".join(historical_signals))
        shared = sorted(current_terms & historical_terms)
        current_only = sorted(current_terms - historical_terms)
        historical_only = sorted(historical_terms - current_terms)
        service = str(memory.get("service") or "unknown")
        deployment = _section(summary, "Deployment/configuration")
        current_deployment = str(current.get("deployment") or "unknown")
        differences = []
        if service == str(current.get("service") or ""):
            differences.append("Same service")
        elif service != "unknown":
            differences.append(f"Different service: {service}")
        if deployment and current_deployment != "unknown" and deployment != current_deployment:
            differences.append(f"Historical deployment/configuration: {deployment}")
        if current_only:
            differences.append("Current-only signal terms: " + ", ".join(current_only[:8]))
        if historical_only:
            differences.append("Historical-only signal terms: " + ", ".join(historical_only[:8]))
        why = (
            "Shared symptom/error terms: " + ", ".join(shared)
            if shared else
            "Returned by Hindsight for this incident query; no direct symptom/error term overlap was found in the compact summary."
        )
        provenance = memory.get("provenance") or {}
        comparisons.append({
            "incident_id": memory.get("incident_id") or "",
            "memory_id": provenance.get("memory_id"),
            "date": memory.get("date"),
            "service": service,
            "deployment_context": deployment or "Unknown in recalled evidence",
            "symptoms": _section(summary, "Symptoms"),
            "error_signals": _section(summary, "Error signatures"),
            "actions_and_outcomes": _section(summary, "Interventions and outcomes") or "No intervention outcome was present in this memory summary.",
            "confirmed_root_cause": _section(summary, "Confirmed root cause") or "Not confirmed in recalled evidence",
            "resolution": _section(summary, "Resolution") or "Not recorded in recalled evidence",
            "similarity_terms": shared,
            "differences": differences,
            "why_relevant": why,
            "relevance": memory.get("relevance"),
        })
    return comparisons

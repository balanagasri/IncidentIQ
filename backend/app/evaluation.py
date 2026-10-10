"""Repeatable, labeled synthetic retrieval evaluation against real Hindsight recall."""
from typing import Any, Awaitable, Callable
from .agent import _incident_id, select_evidence


EVALUATION_CASES = [
    {
        "case_id": "pool-saturation",
        "current_incident": {
            "id": "EVAL-POOL", "service": "checkout-api", "symptoms": ["checkout timeout", "pool wait at capacity"],
            "error_signatures": ["AcquireTimeout"], "deployment": "checkout-eval", "configuration_context": "Traffic increase; pool metrics available.",
        },
        "relevant_incident_ids": ["INC-2026-041"],
    },
    {
        "case_id": "lock-contention",
        "current_incident": {
            "id": "EVAL-LOCK", "service": "checkout-api", "symptoms": ["checkout timeout", "database pool wait elevated"],
            "error_signatures": ["SQLSTATE 55P03", "row lock wait"], "deployment": "checkout-eval", "configuration_context": "Backfill may be running.",
        },
        "relevant_incident_ids": ["INC-2026-037"],
    },
    {
        "case_id": "certificate-rotation",
        "current_incident": {
            "id": "EVAL-CERT", "service": "checkout-api", "symptoms": ["payment authorization failures", "checkout 502s"],
            "error_signatures": ["x509 unknown authority", "TLS handshake failed"], "deployment": "checkout-eval", "configuration_context": "Gateway certificate rotated.",
        },
        "relevant_incident_ids": ["INC-2026-029"],
    },
    {
        "case_id": "queue-concurrency",
        "current_incident": {
            "id": "EVAL-QUEUE", "service": "checkout-api", "symptoms": ["confirmation delay", "order queue age rising"],
            "error_signatures": ["consumer heartbeat missed"], "deployment": "checkout-eval", "configuration_context": "Consumer concurrency recently changed.",
        },
        "relevant_incident_ids": ["INC-2026-021"],
    },
    {
        "case_id": "unmatched-tax-error",
        "current_incident": {
            "id": "EVAL-NOVEL", "service": "checkout-api", "symptoms": ["tax rounding mismatch for split tender"],
            "error_signatures": ["TaxAllocationInvariant"], "deployment": "checkout-eval", "configuration_context": "No matching checkout change reported.",
        },
        "relevant_incident_ids": [],
    },
]


def _query(incident: dict[str, Any]) -> str:
    return (
        f"Comparable incident outcomes for {incident['service']}. Symptoms: {'; '.join(incident['symptoms'])}. "
        f"Errors: {'; '.join(incident['error_signatures'])}. Deployment/configuration: "
        f"{incident['deployment']}; {incident['configuration_context']}."
    )


async def run_retrieval_evaluation(recall: Callable[[str], Awaitable[list[dict[str, Any]]]],
                                   retained_case: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run labeled scenarios against the supplied real recall callable; retain failures as failures."""
    rows = []
    expected_total = 0
    retrieved_relevant_total = 0
    selected_relevant_total = 0
    selected_total = 0
    failures = 0
    unmatched_returned = 0
    cases = [*EVALUATION_CASES, *([retained_case] if retained_case else [])]
    for case in cases:
        expected = set(case["relevant_incident_ids"])
        try:
            recalled = await recall(_query(case["current_incident"]))
        except Exception as exc:
            failures += 1
            rows.append({"case_id": case["case_id"], "status": "error", "error_type": type(exc).__name__,
                         "expected_relevant_ids": sorted(expected), "recalled_ids": [], "selected_ids": []})
            continue
        expected_total += len(expected)
        recalled_ids = list(dict.fromkeys(_incident_id(item) for item in recalled if _incident_id(item)))
        selected = select_evidence(recalled)
        selected_ids = list(dict.fromkeys(item["incident_id"] for item in selected if item.get("incident_id")))
        hits = expected & set(recalled_ids)
        selected_hits = expected & set(selected_ids)
        retrieved_relevant_total += len(hits)
        selected_relevant_total += len(selected_hits)
        selected_total += len(selected_ids)
        if not expected and recalled_ids:
            unmatched_returned += 1
        rows.append({
            "case_id": case["case_id"], "status": "completed",
            "expected_relevant_ids": sorted(expected), "recalled_ids": recalled_ids,
            "selected_ids": selected_ids, "relevant_recalled_ids": sorted(hits),
            "relevant_selected_ids": sorted(selected_hits),
        })

    completed = len(cases) - failures
    return {
        "dataset": "synthetic-checkout-v1",
        "evaluation_mode": "live Hindsight recall; no LLM call",
        "baseline": {
            "mode": "memory-free reference",
            "retrieved_relevant": 0,
            "expected_relevant_in_completed_cases": sum(
                len(row["expected_relevant_ids"]) for row in rows if row["status"] == "completed"
            ),
            "note": "No Hindsight memories are supplied in this reference mode; this measures retrieval coverage only, not recommendation quality.",
        },
        "memory_assisted": {
            "completed_cases": completed,
            "failed_cases": failures,
            "retrieval_recall": retrieved_relevant_total / expected_total if expected_total else None,
            "retrieval_recall_hits": retrieved_relevant_total,
            "retrieval_recall_expected": expected_total,
            "selected_precision": selected_relevant_total / selected_total if selected_total else None,
            "selected_precision_relevant": selected_relevant_total,
            "selected_precision_count": selected_total,
            "unmatched_cases_with_results": unmatched_returned,
            "unmatched_cases": sum(1 for case in cases if not case["relevant_incident_ids"] and any(
                row["case_id"] == case["case_id"] and row["status"] == "completed" for row in rows
            )),
        },
        "metric_definitions": {
            "retrieval_recall": "Labeled relevant incident IDs recalled / labeled relevant IDs across completed cases.",
            "selected_precision": "Labeled relevant IDs among selected-for-reasoning incidents / all selected incident IDs.",
            "unmatched_cases_with_results": "Completed zero-label cases where Hindsight returned at least one incident; not an LLM citation error rate.",
            "scope": "Measures Hindsight retrieval and the six-memory selector only. It does not measure LLM recommendation quality, resolution time, or causal correctness.",
        },
        "cases": rows,
    }

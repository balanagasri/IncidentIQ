import pytest
from app.evaluation import EVALUATION_CASES, run_retrieval_evaluation
from app.seed_data import INCIDENTS


@pytest.mark.asyncio
async def test_evaluation_uses_returned_memory_ids_and_reports_labeled_retrieval_metrics():
    by_id = {item["id"]: item for item in INCIDENTS}
    calls = []

    async def recall(query):
        calls.append(query)
        if "SQLSTATE 55P03" in query or "row lock wait" in query or "Backfill" in query:
            incident = by_id["INC-2026-037"]
        elif "TLS handshake failed" in query:
            incident = by_id["INC-2026-029"]
        elif "consumer heartbeat missed" in query:
            incident = by_id["INC-2026-021"]
        elif "TaxAllocationInvariant" in query:
            return []
        else:
            incident = by_id["INC-2026-041"]
        return [{"metadata": {"incident_id": incident["id"]}, "text": (
            f"Incident {incident['id']} affected checkout-api. Symptoms: "
            + "; ".join(incident["symptoms"])
            + "\nError signatures: " + "; ".join(incident["error_signatures"])
            + "\nAttempted interventions and reported outcomes:\n"
            + "\n".join(f"- {action['action']}: {action['outcome']} — {action['notes']}" for action in incident["actions"])
            + f"\nConfirmed root cause: {incident['confirmed_root_cause']}\nResolution: {incident['resolution']}"
        )}]

    result = await run_retrieval_evaluation(recall)

    assert len(calls) == len(EVALUATION_CASES)
    assert result["memory_assisted"]["failed_cases"] == 0
    assert result["memory_assisted"]["retrieval_recall"] == 1.0
    assert result["memory_assisted"]["selected_precision"] == 1.0
    assert result["memory_assisted"]["unmatched_cases_with_results"] == 0
    assert result["baseline"]["retrieved_relevant"] == 0
    assert "not recommendation quality" in result["baseline"]["note"]


@pytest.mark.asyncio
async def test_evaluation_reports_external_errors_as_partial_not_success():
    calls = 0

    async def recall(_query):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("unavailable")
        return []

    result = await run_retrieval_evaluation(recall)

    assert result["memory_assisted"]["failed_cases"] == 1
    assert result["memory_assisted"]["completed_cases"] == len(EVALUATION_CASES) - 1
    assert result["cases"][0]["status"] == "error"
    assert result["cases"][0]["error_type"] == "ConnectionError"
    assert result["memory_assisted"]["retrieval_recall"] == 0.0

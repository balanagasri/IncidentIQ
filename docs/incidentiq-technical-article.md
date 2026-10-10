# IncidentIQ: Remembering Which Incident Fixes Worked with Hindsight

## Introduction: incident history is more than a timeline

Familiar symptoms do not guarantee a familiar cause. Checkout timeouts can follow a traffic increase, database locks, stale certificates, or queue configuration changes. A useful incident memory therefore records not only what happened, but what engineers tried and whether it helped.

IncidentIQ stores synthetic incident narratives in Hindsight, recalls them for a new incident, and asks a language model for a structured investigation plan. Engineers decide what to do and report the outcome. The MVP does not connect to production systems or execute changes.

[SCREENSHOT 1 — Initial incident before historical memory]
Show the First demo incident selected and analyzed before seeding a fresh Hindsight demo bank. Include the incident facts and empty/no-useful-history evidence state. The empty-history baseline depends on using a bank that has not already been seeded.

## What IncidentIQ does

The example domain is checkout/payment. An incident includes symptoms, error signatures, deployment version, and configuration context. The backend recalls from Hindsight before recommendation generation. Its structured response contains a summary, hypotheses, recommended steps, safety notes, unknowns, and evidence-memory IDs.

The seed data makes the problem concrete. `INC-2026-041` records checkout timeouts and pool saturation during increased traffic: restarting failed, while increasing the database pool after checking headroom succeeded. `INC-2026-037` has similar timeout and pool-wait symptoms, but increasing the pool failed because the confirmed cause was backfill lock contention. Similar symptoms do not guarantee the same intervention.

## Architecture

The React/Vite workspace calls a FastAPI backend. Routes are in `backend/app/main.py` (there is no `backend/app/api.py`). SQLModel uses SQLite for incidents, actions, and analysis snapshots. `hindsight.py` owns the Hindsight adapter; `agent.py` selects evidence and generates recommendations; `schemas.py` defines their data contract.

SQLite holds application workflow state; Hindsight is the external persistent memory used to retain and search incident narratives. The backend reads service settings from environment variables. It uses the Python OpenAI client with Groq’s OpenAI-compatible API and JSON Schema response formatting. Credentials stay on the backend.

## How Hindsight is integrated

The backend calls the Hindsight bank API directly with `httpx.AsyncClient`. Retain sends an incident narrative to `POST /v1/default/banks/{bank_id}/memories`, with timestamp, stable document ID, team/service/type tags, and incident metadata. The narrative separates suspected from confirmed causes and spells out action outcomes.

This is the actual retain call in `backend/app/hindsight.py`:

```python
response = await self._post("/memories", {"items": [item]}, "retain")
```

Recall posts separately to `/memories/recall`. Its payload uses a medium budget, 5,000-token maximum, strict demo-team tag matching, selected memory types, and object-form `include.chunks`. The query includes the current incident’s service, symptoms, errors, and deployment/configuration context.

```python
body = self._recall_payload(query)
response = await self._post("/memories/recall", body, "recall")
```

The adapter retries `httpx.TransportError` up to two times, with 100 ms and 200 ms delays. HTTP error responses are not retried. Retries do not guarantee external availability.

## Retain → Recall → Reason → Outcome → Retain

`POST /api/demo/seed-hindsight` retains four synthetic checkout incidents with document IDs such as `incident:INC-2026-041`. `POST /api/incidents/{id}/analyze` recalls first, then passes the incident and selected evidence to the agent. The UI receives the broad recall results and recalled/selected/cited counts with the recommendation.

The agent sorts by an available Hindsight relevance score, removes duplicate incident identities, and selects at most six memories. Each summary is limited to 1,400 characters, bounding model context while leaving the broader result list available to the UI.

[SCREENSHOT 2 — Hindsight recall showing recalled memories]
Show the evidence panel after seeding and analysis. Include recalled incident IDs, date/service, relevance when returned, and source text describing interventions and outcomes.

## Learning from failed and inconclusive interventions

The UI records an action, outcome (`successful`, `failed`, or `inconclusive`), and notes. The action route stores it in SQLite; the UI then calls retain, which sends the updated incident under its stable Hindsight document ID. On resolution, the engineer supplies cause, resolution, and duration, and the resolve route retains that state too.

The Hindsight narrative explicitly preserves outcomes:

```python
action_lines = [
    f"- {a.get('action')}: {a.get('outcome')} — {a.get('notes', '')}"
    for a in actions
]
```

Failed and inconclusive actions remain alongside successes for later recall. This is operational learning through retained memory, not model fine-tuning. Since action storage and Hindsight retain are separate requests, a retain failure can leave the action in SQLite without updating Hindsight.

[SCREENSHOT 3 — Engineer records an intervention outcome]
Show the action/outcome form with a reported result and the action history. The UI’s confirmation appears after the backend retain call succeeds.

## Recommendation provenance

The LLM receives an allowlist from selected Hindsight results: incident and memory IDs, summaries, and intervention/outcome text. Its JSON response includes `evidence_memory_ids`. Pydantic validates the structure; the backend filters IDs against selected incidents and replaces model-authored evidence descriptions with Hindsight-derived summaries.

If the model returns no citations, `agent.py` applies a deterministic fallback: it compares substantive terms in the summary and steps with selected evidence. It requires two overlapping terms, or a configured specific anchor plus an explicit action outcome, then ranks matches and selects at most two. It only uses selected results with incident IDs. This lexical heuristic is not semantic proof and can miss or misread a relationship.

The evidence panel shows all recalled memories and a separate “USED IN RECOMMENDATION” section with cited IDs and summaries. It shows the selected count but does not mark each selected card. Recommendations are advisory; the engineer decides what to do.

[SCREENSHOT 4 — Evidence-backed recommendation and cited Hindsight memory]
Show the recommendation steps beside the broader recall panel and “USED IN RECOMMENDATION” section, so the incident ID and supporting historical summary are visible together.

## Before and after memory

Before seeding, the First demo incident is analyzed against a fresh bank without IncidentIQ seed history. After seeding, comparable symptoms can bring back contrasting outcomes: pool capacity helped during a traffic surge, while a pool change did not address lock contention. The recommendation can use this evidence to motivate a read-only check of pool utilization or lock waiters without asserting a diagnosis.

After the engineer’s outcome is retained, “Later similar incident” creates a synthetic checkout incident and analysis performs another Hindsight recall. If Hindsight returns the updated memory, it appears in the evidence and may support the recommendation. Retrieval is relevance-dependent; a particular result is not guaranteed.

[SCREENSHOT 5 — Later incident after retention]
Show the later similar incident after the engineer outcome has been retained. Capture its Hindsight panel if the new incident memory is returned; do not imply retrieval if it is absent.

## Engineering decisions

The implementation separates the Hindsight adapter, evidence selection and reasoning, schema validation, and route orchestration. UI recall evidence comes from Hindsight; there is no local recall substitute. Bounded model context addresses request size while preserving the wider evidence list.

## Limitations

The demo uses fictional checkout/payment data. It does not ingest production telemetry, connect to production systems, or execute remediation. It covers one demo team and service domain; engineer-reported outcomes are not independently verified. Retrieval and model output depend on external availability, configuration, and relevance. The fallback is lexical, and structured output does not prove a hypothesis. Authentication, access control, redaction, and production ingestion safeguards are outside this MVP.

## Conclusion

IncidentIQ makes intervention outcomes part of incident memory: Hindsight retains incident context, action history, and resolution; recall brings prior records into a later investigation; the agent produces bounded, structured recommendations with checked provenance; and the engineer supplies the next outcome. The result is a small, inspectable retain–recall loop that keeps humans responsible for operational decisions and makes both failed and successful experience available to future investigations.

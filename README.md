# IncidentIQ

IncidentIQ is a focused incident-response assistant for SRE and software teams. It uses real Hindsight memory retain and recall APIs to find prior synthetic incident outcomes, then asks an LLM to recommend evidence-backed investigation steps. Engineers record what they actually tried so future incidents can learn from both successful and failed interventions.

> **Demo data only.** This MVP uses synthetic checkout/payment incidents. It does not connect to production systems, ingest live telemetry, or execute operational changes.

## What it demonstrates

The project is designed to show the complete learning loop:

1. Analyze an incident before historical incidents are seeded and observe that there is no useful history.
2. Retain the synthetic incident set into a real Hindsight bank.
3. Analyze a comparable incident and see real recall results, including failed and successful actions.
4. Record the engineer's actual action and outcome.
5. Resolve the incident and retain its final outcome to Hindsight.
6. Analyze a later similar incident and inspect whether the new outcome is recalled.

The workspace also includes Hindsight-backed similar-incident comparisons, an application analytics view, a manually triggered retrieval evaluation, and an editable postmortem draft. Postmortems are assembled from recorded data; missing impact or root cause is labeled unknown. These additions do not execute remediation.

## Architecture

```text
React + Vite UI ── IncidentIQ FastAPI ── SQLite application state
                          │
                          ├── Hindsight Memory API (retain / recall)
                          └── Groq OpenAI-compatible API (structured reasoning)
```

- `frontend/` contains the single-page incident workspace and Hindsight evidence panel.
- `backend/app/` contains API routes, structured schemas, SQLite models, LLM reasoning, and the Hindsight HTTP adapter.
- Hindsight stores searchable incident memories. SQLite stores workflow state, engineer actions, analysis snapshots, and provenance. The application does not substitute a local vector store or canned recall response for Hindsight.
- SQLite also records successful retain operations, recommendation feedback, evaluation runs, and postmortem drafts. New tables are created with the existing SQLModel `create_all` startup; no existing table columns are altered.
- LLM keys and Hindsight credentials remain on the backend. The browser receives recommendations and normalized recall evidence only.

## Hindsight integration and memory strategy

The backend calls the Hindsight bank API directly:

- `POST /v1/default/banks/{bank_id}/memories` for retain.
- `POST /v1/default/banks/{bank_id}/memories/recall` for recall.

Each incident is serialized into a compact narrative covering its service, timestamp, symptoms, error signatures, release/configuration context, suspected versus confirmed causes, attempted actions and explicit outcomes, resolution, and resolution time. Retains use a stable `incident:{incident_id}` document ID so final updates replace the same logical document. Team/service/type tags scope recall; incident IDs and source metadata provide provenance. The recall query includes current incident symptoms, error signatures, and release/configuration context. Recall results shown in the UI come from the Hindsight API response.

Only identities returned by Hindsight may appear as recommendation citations. The backend filters generated citation IDs against the selected memories and replaces model-authored evidence descriptions with compact summaries derived from the Hindsight results. Up to six unique memories, each summarized to at most 1,400 characters, enter Groq reasoning; the evidence panel can still display the broader recall result set. The model is instructed to distinguish fact from hypothesis, avoid inventing confirmed causes or outcomes, and suggest safe investigations rather than take action.

If the model returns no citation IDs, a deterministic lexical fallback compares terms in the recommendation and investigation steps with selected Hindsight summaries. It uses only selected incidents, requires meaningful overlap (or a configured specific term plus an explicit action outcome), and can select at most two memories. This is a heuristic rather than semantic proof. The comparison view labels shared symptom/error terms and differences; it does not equate similar symptoms with a shared cause.

The demo uses a fresh, dedicated Hindsight bank. The first no-history phase assumes that bank has not previously been populated with IncidentIQ demo memories. Seed and incident retain operations are idempotent by document ID.

## Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- A reachable Hindsight service/bank and an API key accepted by that service
- A Groq API key for the configured OpenAI-compatible Groq endpoint

## Setup

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Create a Groq API key at [console.groq.com/keys](https://console.groq.com/keys): sign in or create a Groq account, open **API Keys**, create a key, then copy it directly into `LLM_API_KEY` in `backend/.env`. Do not paste the key into the chat or commit the `.env` file. Keep the Hindsight key in `HINDSIGHT_API_KEY` as before.

The app uses Groq's OpenAI-compatible API with the existing Python OpenAI client. The base URL and model below are configured by default; leave them as shown unless intentionally changing providers.

Set the secrets and service settings in `backend/.env`:

| Variable | Purpose |
| --- | --- |
| `APP_DATABASE_URL` | SQLModel database URL; defaults to local SQLite |
| `HINDSIGHT_BASE_URL` | Hindsight service base URL; Cloud default shown in example |
| `HINDSIGHT_API_KEY` | Hindsight API bearer key |
| `HINDSIGHT_BANK_ID` | Dedicated bank for the IncidentIQ demo |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` |
| `LLM_API_KEY` | Groq API key created in Groq Console |
| `LLM_MODEL` | `openai/gpt-oss-120b` |
| `LLM_PROVIDER` | `groq` |
| `APP_CORS_ORIGINS` | Comma-separated frontend origins |

Run the API from `backend/`:

```powershell
uvicorn app.main:app --reload --port 8000
```

Interactive API docs are at `http://localhost:8000/docs`.

### Frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to the local FastAPI service.
If the backend uses a non-default port, set `VITE_API_TARGET` before starting Vite (for example, `http://127.0.0.1:8001`); the default proxy target is `http://localhost:8000`.

## Demo walkthrough

1. Start both services and confirm `/api/health` reports Hindsight and LLM configuration.
2. In the UI, click **First demo incident**, then **Analyze with memory** before seeding. The evidence panel should report no matching memory on a fresh demo bank.
3. Click **Seed historical incidents**. The API will retain four synthetic checkout incidents in Hindsight, including a failed restart, a successful pool increase, and superficially similar symptoms with different confirmed causes.
4. Create another incident with the API `POST /api/incidents` (or use the first incident after seed) and analyze it. The evidence panel displays actual recalled memory text, incident provenance, and intervention outcomes; recommendations cite only returned incident IDs.
5. Record an engineer action/outcome. The updated incident is retained using its stable Hindsight document ID.
6. Resolve the incident with a confirmed cause, resolution, and elapsed minutes. The resolved narrative is retained again.
7. Click **Later similar incident**, analyze it, and inspect recall for the newly retained incident.

The **Memory analytics** view reports measurements from SQLite records and successful retain logs. For a clean portfolio demo, point `APP_DATABASE_URL` to a new SQLite file before starting the backend; the existing ignored local database may contain prior manual or test activity. The evaluation button makes real Hindsight recall calls for a labeled synthetic checkout dataset; when a successfully retained incident with an engineer-reported successful action exists, it adds a follow-up case for that incident. It does not call the LLM. Retrieval recall is labeled relevant incident IDs found in completed scenarios divided by labeled relevant IDs for those scenarios. Selected precision is relevant IDs among selected memories divided by all selected IDs. The zero-memory baseline reports retrieval coverage only; it is not a baseline recommendation-quality comparison. Partial external failures are recorded as partial, and a run does not measure resolution quality or prove that memory improves outcomes.

The **Postmortem** view builds an editable Markdown draft from recorded incident fields, action rows, the latest analysis, and its validated memory evidence. Impact and root cause are marked unknown when absent. Finalizing retains the incident’s recorded knowledge in Hindsight using its stable incident document ID. Re-finalizing an unchanged report does not issue another retain call; editing and finalizing updates the same document ID. The report itself is saved in SQLite; Hindsight retain uses the incident narrative.

Action submissions accept an idempotency token so a client retry with the same token does not create a duplicate action row. Recommendation usefulness feedback stores one latest decision per analysis, so changing a vote updates that record rather than preserving every vote change.

The four-history seed endpoint is `POST /api/demo/seed-hindsight`. It makes real retain requests and reports an API error if Hindsight is unavailable or credentials are missing.

## API overview

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | App status and boolean dependency configuration indicators (no secrets) |
| `GET /api/demo/incidents` | First demo incident and synthetic history count |
| `POST /api/demo/first` | Create the initial no-history incident |
| `POST /api/demo/seed-hindsight` | Retain the synthetic history into Hindsight |
| `POST /api/incidents` / `GET /api/incidents` | Create/list application incidents |
| `GET /api/incidents/{id}` | Read incident workflow state |
| `POST /api/incidents/{id}/analyze` | Hindsight recall, LLM reasoning, and evidence snapshot |
| `POST /api/incidents/{id}/actions` | Record an engineer action outcome |
| `POST /api/incidents/{id}/retain` | Retain the evolving incident state |
| `POST /api/incidents/{id}/resolve` | Resolve and retain final incident outcome |
| `GET /api/analytics` | Application record counts, outcomes, feedback, and latest evaluation |
| `POST /api/evaluations/run` | Run labeled scenarios against live Hindsight recall (no LLM call) |
| `GET /api/evaluations/latest` | Read the latest persisted evaluation |
| `POST /api/analyses/{id}/feedback` | Record/update engineer usefulness feedback for an analysis |
| `POST /api/incidents/{id}/postmortem/generate` | Generate a factual editable postmortem draft |
| `GET` / `PUT /api/incidents/{id}/postmortem` | Read or save the Markdown draft |
| `POST /api/incidents/{id}/postmortem/finalize` | Finalize the draft and retain incident knowledge in Hindsight |

## Tests and verification

Backend tests: `cd backend; pytest`. The suite includes a live Hindsight recall test when credentials are configured and therefore needs network access. In Windows PowerShell, run the frontend production build with `cd frontend; npm.cmd run build` and frontend checks with `cd frontend; npm.cmd test`. A live Hindsight/Groq end-to-end demo requires valid external credentials and a reachable configured bank.

## Limitations

- Synthetic incident data only; no production integration or live telemetry.
- One demo team and checkout/payment service domain.
- Recommendations are advisory. Engineers remain responsible for investigation and changes.
- No authentication, multi-tenancy, role-based access, redaction pipeline, or production log-ingestion controls.
- Recall quality and extracted facts depend on Hindsight configuration and the selected model/provider.
- This MVP records the engineer-reported result; it does not independently verify operational outcomes.
- The evaluation measures live Hindsight retrieval and the local six-memory selector on labeled synthetic cases; it does not score LLM recommendation quality or resolution outcomes. Evaluation requires a reachable Hindsight endpoint.
- Similarity explanations are lexical. They disclose shared terms and returned evidence, not semantic proof of a common cause.
- The health screen reports whether credentials are configured, not whether remote services are reachable.
- Postmortem drafts can only include data represented in application records. Impact is not modeled, and missing facts remain unknown. Editing the Markdown changes the saved report text; the structured source fields remain the generated record.
- Recommendation feedback stores the latest accepted/rejected value per analysis, not a sequence of every change.

## Synthetic-data disclaimer

All included incident IDs, timestamps, release versions, metrics, logs, action outcomes, causes, and resolutions are fictional examples created for the demo. They are not reports of real incidents.

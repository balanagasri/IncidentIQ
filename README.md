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
- LLM keys and Hindsight credentials remain on the backend. The browser receives recommendations and normalized recall evidence only.

## Hindsight integration and memory strategy

The backend calls the Hindsight bank API directly:

- `POST /v1/default/banks/{bank_id}/memories` for retain.
- `POST /v1/default/banks/{bank_id}/memories/recall` for recall.

Each incident is serialized into a compact narrative covering its service, timestamp, symptoms, error signatures, release/configuration context, suspected versus confirmed causes, attempted actions and explicit outcomes, resolution, and resolution time. Retains use a stable `incident:{incident_id}` document ID so final updates replace the same logical document. Team/service/type tags scope recall; incident IDs and source metadata provide provenance. The recall query includes current incident symptoms, error signatures, and release/configuration context. Recall results shown in the UI come from the Hindsight API response.

Only identities returned by Hindsight may appear as recommendation citations. The backend filters generated citation IDs against the selected memories and replaces model-authored evidence descriptions with compact summaries derived from the Hindsight results. Up to six unique memories, each summarized to at most 1,400 characters, enter Groq reasoning; the evidence panel can still display the broader recall result set. The model is instructed to distinguish fact from hypothesis, avoid inventing confirmed causes or outcomes, and suggest safe investigations rather than take action.

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

## Demo walkthrough

1. Start both services and confirm `/api/health` reports Hindsight and LLM configuration.
2. In the UI, click **First demo incident**, then **Analyze with memory** before seeding. The evidence panel should report no matching memory on a fresh demo bank.
3. Click **Seed historical incidents**. The API will retain four synthetic checkout incidents in Hindsight, including a failed restart, a successful pool increase, and superficially similar symptoms with different confirmed causes.
4. Create another incident with the API `POST /api/incidents` (or use the first incident after seed) and analyze it. The evidence panel displays actual recalled memory text, incident provenance, and intervention outcomes; recommendations cite only returned incident IDs.
5. Record an engineer action/outcome. The updated incident is retained using its stable Hindsight document ID.
6. Resolve the incident with a confirmed cause, resolution, and elapsed minutes. The resolved narrative is retained again.
7. Click **Later similar incident**, analyze it, and inspect recall for the newly retained incident.

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

## Tests and verification

Backend tests: `cd backend; pytest`. The suite includes a live Hindsight recall test when credentials are configured and therefore needs network access. In Windows PowerShell, run the frontend production build with `cd frontend; npm.cmd run build` and frontend checks with `cd frontend; npm.cmd test`. A live Hindsight/Groq end-to-end demo requires valid external credentials and a reachable configured bank.

## Limitations

- Synthetic incident data only; no production integration or live telemetry.
- One demo team and checkout/payment service domain.
- Recommendations are advisory. Engineers remain responsible for investigation and changes.
- No authentication, multi-tenancy, role-based access, redaction pipeline, or production log-ingestion controls.
- Recall quality and extracted facts depend on Hindsight configuration and the selected model/provider.
- This MVP records the engineer-reported result; it does not independently verify operational outcomes.

## Synthetic-data disclaimer

All included incident IDs, timestamps, release versions, metrics, logs, action outcomes, causes, and resolutions are fictional examples created for the demo. They are not reports of real incidents.

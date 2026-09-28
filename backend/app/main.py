from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from .config import get_settings
from .database import get_session, init_db
from .models import Incident, Action, Analysis
from .schemas import IncidentCreate, ActionCreate, ResolveRequest
from .hindsight import HindsightService, HindsightError
from .agent import recommend
from .seed_data import INCIDENTS, FIRST_DEMO


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="IncidentIQ API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
hindsight = HindsightService()


def serialize(incident: Incident, session: Session):
    data = incident.model_dump(mode="json")
    data["actions"] = [a.model_dump(mode="json") for a in session.exec(select(Action).where(Action.incident_id == incident.id).order_by(Action.id)).all()]
    return data


@app.get("/api/health")
async def health():
    settings = get_settings()
    return {"status": "ok", "hindsight_configured": bool(settings.hindsight_api_key), "llm_configured": bool(settings.llm_api_key), "synthetic_data_only": True}


@app.get("/api/demo/incidents")
def demo_incidents():
    return {"first_incident": FIRST_DEMO, "historical_count": len(INCIDENTS), "synthetic": True}


@app.post("/api/demo/first", status_code=201)
def create_first(session: Session = Depends(get_session)):
    first = {**FIRST_DEMO, "timestamp": datetime.fromisoformat(FIRST_DEMO["timestamp"].replace("Z", "+00:00"))}
    item = Incident(id="INC-DEMO-FIRST", **first)
    existing = session.get(Incident, item.id)
    if existing:
        return serialize(existing, session)
    session.add(item); session.commit(); session.refresh(item)
    return serialize(item, session)


@app.post("/api/demo/seed-hindsight")
async def seed_hindsight():
    outcomes = []
    for data in INCIDENTS:
        incident = {**data, "is_synthetic": True}
        try:
            result = await hindsight.retain(incident, f"incident:{data['id']}")
            outcomes.append({"incident_id": data["id"], "retained": True, "result": result})
        except HindsightError as exc:
            raise HTTPException(502, detail=str(exc))
    return {"seeded": len(outcomes), "incidents": outcomes, "synthetic": True}


@app.post("/api/incidents", status_code=201)
def create_incident(payload: IncidentCreate, session: Session = Depends(get_session)):
    item = Incident(id=f"INC-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}", **payload.model_dump(exclude_none=True))
    session.add(item); session.commit(); session.refresh(item)
    return serialize(item, session)


@app.get("/api/incidents")
def list_incidents(session: Session = Depends(get_session)):
    return [serialize(x, session) for x in session.exec(select(Incident).order_by(Incident.timestamp.desc())).all()]


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str, session: Session = Depends(get_session)):
    item = session.get(Incident, incident_id)
    if not item: raise HTTPException(404, "Incident not found")
    return serialize(item, session)


@app.post("/api/incidents/{incident_id}/analyze")
async def analyze(incident_id: str, session: Session = Depends(get_session)):
    item = session.get(Incident, incident_id)
    if not item: raise HTTPException(404, "Incident not found")
    current = serialize(item, session)
    query = f"Comparable production incident outcomes for {item.service}. Symptoms: {'; '.join(item.symptoms)}. Errors: {'; '.join(item.error_signatures)}. Deployment/config: {item.deployment}; {item.configuration_context}. Which interventions succeeded or failed, and what root causes were confirmed?"
    try:
        memories = await hindsight.recall(query)
    except HindsightError as exc:
        raise HTTPException(502, detail=str(exc))
    try:
        result, memory_stats = await recommend(current, memories)
    except Exception as exc:
        raise HTTPException(502, detail=f"LLM analysis failed: {exc}")
    evidence = [{"incident_id": _memory_incident_id(m), "date": m.get("timestamp") or m.get("when"), "service": _memory_service(m, item.service),
                 "text": m.get("text") or m.get("content") or str(m), "relevance": m.get("score") or m.get("final_score"),
                 "metadata": m.get("metadata") or {}} for m in memories]
    analysis = Analysis(incident_id=incident_id, recommendation=result.model_dump(), evidence=evidence)
    session.add(analysis); session.commit(); session.refresh(analysis)
    return {"incident": current, "recommendation": result.model_dump(), "evidence": evidence,
            "memory_stats": memory_stats, "analysis_id": analysis.id}


def _memory_incident_id(memory: dict) -> str:
    metadata = memory.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("incident_id"):
        return str(metadata["incident_id"])
    import re
    text = str(memory.get("text") or memory.get("content") or "")
    match = re.search(r"Incident\s+(INC-[A-Za-z0-9_-]+)", text, re.I)
    return match.group(1) if match else ""


def _memory_service(memory: dict, fallback: str) -> str:
    metadata = memory.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("service"):
        return str(metadata["service"])
    for tag in memory.get("tags") or []:
        if str(tag).startswith("service:"):
            return str(tag).split(":", 1)[1]
    import re
    text = str(memory.get("text") or memory.get("content") or "")
    match = re.search(r"affected\s+([\w-]+)", text, re.I)
    return match.group(1) if match else fallback


@app.post("/api/incidents/{incident_id}/actions", status_code=201)
def record_action(incident_id: str, payload: ActionCreate, session: Session = Depends(get_session)):
    if not session.get(Incident, incident_id): raise HTTPException(404, "Incident not found")
    action = Action(incident_id=incident_id, **payload.model_dump())
    session.add(action); session.commit(); session.refresh(action)
    return action.model_dump(mode="json")


async def retain_incident(item: Incident, session: Session):
    data = serialize(item, session)
    try:
        result = await hindsight.retain(data, f"incident:{item.id}")
    except HindsightError as exc:
        raise HTTPException(502, detail=str(exc))
    item.hindsight_document_id = f"incident:{item.id}"
    item.retained_at = datetime.now(timezone.utc)
    session.add(item); session.commit()
    return {"retained": True, "document_id": item.hindsight_document_id, "hindsight": result}


@app.post("/api/incidents/{incident_id}/retain")
async def retain_current(incident_id: str, session: Session = Depends(get_session)):
    item = session.get(Incident, incident_id)
    if not item: raise HTTPException(404, "Incident not found")
    return await retain_incident(item, session)


@app.post("/api/incidents/{incident_id}/resolve")
async def resolve(incident_id: str, payload: ResolveRequest, session: Session = Depends(get_session)):
    item = session.get(Incident, incident_id)
    if not item: raise HTTPException(404, "Incident not found")
    item.confirmed_root_cause = payload.confirmed_root_cause
    item.resolution = payload.resolution
    item.resolution_minutes = payload.resolution_minutes
    item.status = "resolved"
    session.add(item); session.commit(); session.refresh(item)
    learning = await retain_incident(item, session)
    return {"incident": serialize(item, session), "learning": learning}


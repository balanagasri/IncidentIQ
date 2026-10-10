from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from .config import get_settings
from .database import get_session, init_db
from .models import Incident, Action, ActionSubmission, Analysis, MemoryRetention, RecommendationFeedback, EvaluationRun, Postmortem
from .schemas import (IncidentCreate, ActionCreate, ResolveRequest, RecommendationFeedbackCreate,
                      PostmortemDraftUpdate, PostmortemReport, AnalysisResponse,
                      AnalyticsResponse, EvaluationRunResponse, EvaluationLatestResponse,
                      RecommendationFeedbackResponse, PostmortemResponse)
from .hindsight import HindsightService, HindsightError
from .agent import recommend, select_evidence
from .comparison import build_comparisons
from .evaluation import run_retrieval_evaluation
from .postmortems import build_postmortem, render_markdown
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
async def seed_hindsight(session: Session = Depends(get_session)):
    outcomes = []
    for data in INCIDENTS:
        incident = {**data, "is_synthetic": True}
        try:
            result = await hindsight.retain(incident, f"incident:{data['id']}")
            outcomes.append({"incident_id": data["id"], "retained": True, "result": result})
            session.add(MemoryRetention(incident_id=data["id"], document_id=f"incident:{data['id']}",
                                        reason="demo_seed", action_count=len(data.get("actions", [])),
                                        has_resolution=bool(data.get("resolution"))))
            session.commit()
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


@app.post("/api/incidents/{incident_id}/analyze", response_model=AnalysisResponse)
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
    selected = select_evidence(memories)
    return {"incident": current, "recommendation": result.model_dump(), "evidence": evidence,
            "similar_incidents": build_comparisons(current, selected),
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
    if payload.submission_id:
        submission = session.get(ActionSubmission, payload.submission_id)
        if submission:
            action = session.get(Action, submission.action_id)
            if action is None or action.incident_id != incident_id:
                raise HTTPException(409, "Submission ID has already been used for another incident")
            return action.model_dump(mode="json")
    action = Action(incident_id=incident_id, **payload.model_dump(exclude={"submission_id"}))
    session.add(action); session.flush()
    if payload.submission_id:
        session.add(ActionSubmission(submission_id=payload.submission_id, action_id=action.id))
    session.commit(); session.refresh(action)
    return action.model_dump(mode="json")


async def retain_incident(item: Incident, session: Session, reason: str):
    data = serialize(item, session)
    try:
        result = await hindsight.retain(data, f"incident:{item.id}")
    except HindsightError as exc:
        raise HTTPException(502, detail=str(exc))
    item.hindsight_document_id = f"incident:{item.id}"
    item.retained_at = datetime.now(timezone.utc)
    session.add(item); session.commit()
    session.add(MemoryRetention(incident_id=item.id, document_id=item.hindsight_document_id, reason=reason,
                                action_count=len(data.get("actions", [])), has_resolution=bool(item.resolution)))
    session.commit()
    return {"retained": True, "document_id": item.hindsight_document_id, "hindsight": result}


@app.post("/api/incidents/{incident_id}/retain")
async def retain_current(incident_id: str, session: Session = Depends(get_session)):
    item = session.get(Incident, incident_id)
    if not item: raise HTTPException(404, "Incident not found")
    return await retain_incident(item, session, "incident_update")


@app.post("/api/incidents/{incident_id}/resolve")
async def resolve(incident_id: str, payload: ResolveRequest, session: Session = Depends(get_session)):
    item = session.get(Incident, incident_id)
    if not item: raise HTTPException(404, "Incident not found")
    item.confirmed_root_cause = payload.confirmed_root_cause
    item.resolution = payload.resolution
    item.resolution_minutes = payload.resolution_minutes
    item.status = "resolved"
    session.add(item); session.commit(); session.refresh(item)
    learning = await retain_incident(item, session, "resolution")
    return {"incident": serialize(item, session), "learning": learning}


@app.get("/api/analytics", response_model=AnalyticsResponse)
def analytics(session: Session = Depends(get_session)):
    incidents = session.exec(select(Incident)).all()
    analyses = session.exec(select(Analysis)).all()
    actions = session.exec(select(Action)).all()
    retentions = session.exec(select(MemoryRetention)).all()
    feedback = session.exec(select(RecommendationFeedback)).all()
    outcome_distribution = {outcome: sum(1 for action in actions if action.outcome == outcome)
                            for outcome in ("successful", "failed", "inconclusive")}
    citation_count = valid_citation_count = analyses_with_recall = 0
    analyses_with_citations = 0
    for analysis in analyses:
        evidence = analysis.evidence if isinstance(analysis.evidence, list) else []
        if evidence:
            analyses_with_recall += 1
        recalled_ids = {str(item.get("incident_id")) for item in evidence if isinstance(item, dict) and item.get("incident_id")}
        recommendation = analysis.recommendation if isinstance(analysis.recommendation, dict) else {}
        citations = recommendation.get("evidence_memory_ids") or []
        if citations:
            analyses_with_citations += 1
        citation_count += len(citations)
        valid_citation_count += sum(1 for citation in citations if citation in recalled_ids)
    latest_evaluation = session.exec(select(EvaluationRun).order_by(EvaluationRun.created_at.desc())).first()
    retained_outcome_incidents = len({event.incident_id for event in retentions if event.action_count > 0 or event.has_resolution})
    return {
        "measured_from": "SQLite application records and completed live Hindsight retain logs",
        "incident_count": len(incidents),
        "investigation_count": len(analyses),
        "investigations_with_recalled_results": analyses_with_recall,
        "recommendations_with_citations": analyses_with_citations,
        "citation_validity": valid_citation_count / citation_count if citation_count else None,
        "valid_citations": valid_citation_count,
        "citation_count": citation_count,
        "successful_hindsight_retains": len(retentions),
        "distinct_incidents_with_retained_outcomes": retained_outcome_incidents,
        "action_outcomes": outcome_distribution,
        "recommendation_feedback": {
            "accepted": sum(1 for item in feedback if item.accepted),
            "rejected": sum(1 for item in feedback if not item.accepted),
            "recorded": len(feedback),
        },
        "latest_evaluation": {"id": latest_evaluation.id, "status": latest_evaluation.status,
                              "created_at": latest_evaluation.created_at.isoformat(), "result": latest_evaluation.result}
        if latest_evaluation else None,
    }


@app.post("/api/evaluations/run", status_code=201, response_model=EvaluationRunResponse)
async def run_evaluation(session: Session = Depends(get_session)):
    retained_case = None
    events = session.exec(select(MemoryRetention)).all()
    for event in sorted(events, key=lambda item: item.created_at, reverse=True):
        if event.reason == "demo_seed":
            continue
        incident = session.get(Incident, event.incident_id)
        if incident is None:
            continue
        actions = session.exec(select(Action).where(Action.incident_id == incident.id)).all()
        if not any(action.outcome == "successful" for action in actions):
            continue
        retained_case = {
            "case_id": "retained-followup-" + incident.id,
            "current_incident": {
                "id": "EVAL-FOLLOWUP", "service": incident.service,
                "symptoms": [*incident.symptoms, "similar incident after a previously retained intervention"],
                "error_signatures": incident.error_signatures,
                "deployment": incident.deployment,
                "configuration_context": "Follow-up scenario generated from an incident with a retained successful action.",
            },
            "relevant_incident_ids": [incident.id],
        }
        break
    result = await run_retrieval_evaluation(hindsight.recall, retained_case=retained_case)
    failures = result["memory_assisted"]["failed_cases"]
    run = EvaluationRun(status="partial" if failures else "completed", result=result)
    session.add(run); session.commit(); session.refresh(run)
    return {"id": run.id, "status": run.status, "created_at": run.created_at.isoformat(), "result": run.result}


@app.get("/api/evaluations/latest", response_model=EvaluationLatestResponse)
def latest_evaluation(session: Session = Depends(get_session)):
    run = session.exec(select(EvaluationRun).order_by(EvaluationRun.created_at.desc())).first()
    if not run:
        return {"evaluation": None}
    return {"id": run.id, "status": run.status, "created_at": run.created_at.isoformat(), "result": run.result}


@app.post("/api/analyses/{analysis_id}/feedback", response_model=RecommendationFeedbackResponse)
def record_recommendation_feedback(analysis_id: int, payload: RecommendationFeedbackCreate,
                                   session: Session = Depends(get_session)):
    if not session.get(Analysis, analysis_id):
        raise HTTPException(404, "Analysis not found")
    feedback = session.exec(select(RecommendationFeedback).where(RecommendationFeedback.analysis_id == analysis_id)).first()
    if feedback is None:
        feedback = RecommendationFeedback(analysis_id=analysis_id, accepted=payload.accepted, note=payload.note)
    else:
        feedback.accepted = payload.accepted
        feedback.note = payload.note
        feedback.updated_at = datetime.now(timezone.utc)
    session.add(feedback); session.commit(); session.refresh(feedback)
    return {"analysis_id": analysis_id, "accepted": feedback.accepted, "note": feedback.note,
            "created_at": feedback.created_at.isoformat(), "updated_at": feedback.updated_at.isoformat()}


def _postmortem_response(postmortem: Postmortem):
    return {"id": postmortem.id, "incident_id": postmortem.incident_id, "report": postmortem.report,
            "markdown": postmortem.markdown, "finalized": postmortem.finalized,
            "retained_at": postmortem.retained_at.isoformat() if postmortem.retained_at else None,
            "updated_at": postmortem.updated_at.isoformat()}


@app.post("/api/incidents/{incident_id}/postmortem/generate", response_model=PostmortemResponse)
def generate_postmortem(incident_id: str, session: Session = Depends(get_session)):
    incident = session.get(Incident, incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    actions = session.exec(select(Action).where(Action.incident_id == incident_id).order_by(Action.created_at)).all()
    analyses = session.exec(select(Analysis).where(Analysis.incident_id == incident_id).order_by(Analysis.created_at)).all()
    report = build_postmortem(incident, actions, analyses)
    draft = session.exec(select(Postmortem).where(Postmortem.incident_id == incident_id)).first()
    if draft is None:
        draft = Postmortem(incident_id=incident_id, report=report.model_dump(mode="json"), markdown=render_markdown(report))
    else:
        draft.report = report.model_dump(mode="json")
        if not draft.finalized:
            draft.markdown = render_markdown(report)
        draft.updated_at = datetime.now(timezone.utc)
    session.add(draft); session.commit(); session.refresh(draft)
    return _postmortem_response(draft)


@app.get("/api/incidents/{incident_id}/postmortem", response_model=PostmortemResponse)
def get_postmortem(incident_id: str, session: Session = Depends(get_session)):
    if not session.get(Incident, incident_id):
        raise HTTPException(404, "Incident not found")
    draft = session.exec(select(Postmortem).where(Postmortem.incident_id == incident_id)).first()
    if not draft:
        raise HTTPException(404, "Postmortem draft not found")
    return _postmortem_response(draft)


@app.put("/api/incidents/{incident_id}/postmortem", response_model=PostmortemResponse)
def update_postmortem(incident_id: str, payload: PostmortemDraftUpdate, session: Session = Depends(get_session)):
    draft = session.exec(select(Postmortem).where(Postmortem.incident_id == incident_id)).first()
    if not draft:
        raise HTTPException(404, "Generate a postmortem draft before editing it")
    draft.markdown = payload.markdown
    draft.finalized = False
    draft.retained_at = None
    draft.updated_at = datetime.now(timezone.utc)
    session.add(draft); session.commit(); session.refresh(draft)
    return _postmortem_response(draft)


@app.post("/api/incidents/{incident_id}/postmortem/finalize", response_model=PostmortemResponse)
async def finalize_postmortem(incident_id: str, payload: PostmortemDraftUpdate,
                             session: Session = Depends(get_session)):
    incident = session.get(Incident, incident_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    draft = session.exec(select(Postmortem).where(Postmortem.incident_id == incident_id)).first()
    if not draft:
        raise HTTPException(404, "Generate a postmortem draft before finalizing it")
    if draft.finalized and draft.retained_at and draft.markdown == payload.markdown:
        return _postmortem_response(draft)
    draft.markdown = payload.markdown
    draft.updated_at = datetime.now(timezone.utc)
    session.add(draft); session.commit()
    try:
        await retain_incident(incident, session, "postmortem_finalized")
    except HTTPException:
        raise
    draft.finalized = True
    draft.retained_at = datetime.now(timezone.utc)
    session.add(draft); session.commit(); session.refresh(draft)
    return _postmortem_response(draft)


from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class IncidentCreate(BaseModel):
    title: str
    timestamp: Optional[datetime] = None
    service: str = "checkout-api"
    severity: str = "SEV-2"
    symptoms: list[str] = Field(default_factory=list)
    error_signatures: list[str] = Field(default_factory=list)
    deployment: str = "unknown"
    configuration_context: str = ""


class ActionCreate(BaseModel):
    action: str = Field(min_length=2)
    outcome: Literal["successful", "failed", "inconclusive"]
    notes: str = ""
    submission_id: Optional[str] = Field(default=None, max_length=100)


class ResolveRequest(BaseModel):
    confirmed_root_cause: str = Field(min_length=3)
    resolution: str = Field(min_length=3)
    resolution_minutes: int = Field(ge=0)


class Hypothesis(BaseModel):
    cause: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    classification: Literal["FACT", "HYPOTHESIS"]


class RecommendedStep(BaseModel):
    step: str
    priority: Literal["high", "medium", "low"]
    expected_observation: str
    safety_note: str
    evidence_ids: list[str] = Field(default_factory=list)


class MemoryEvidence(BaseModel):
    incident_id: str
    reason: str
    outcome_summary: str


class Recommendation(BaseModel):
    summary: str
    hypotheses: list[Hypothesis]
    recommended_steps: list[RecommendedStep]
    safety_notes: list[str]
    evidence_memory_ids: list[str]
    memory_evidence: list[MemoryEvidence]
    unknowns: list[str]


class RecommendationFeedbackCreate(BaseModel):
    accepted: bool
    note: str = ""


class TimelineEntry(BaseModel):
    timestamp: Optional[datetime] = None
    event: str
    source: Literal["incident", "engineer", "system"]


class PostmortemFactor(BaseModel):
    statement: str
    classification: Literal["FACT", "HYPOTHESIS"]
    evidence_ids: list[str] = Field(default_factory=list)


class PostmortemReport(BaseModel):
    summary: str
    impact: str
    timeline: list[TimelineEntry]
    confirmed_root_cause: str
    contributing_factors: list[PostmortemFactor]
    actions: list[ActionCreate]
    resolution_status: str
    resolution: str
    lessons_learned: list[str]
    follow_up_recommendations: list[str]
    memories_informed: list[MemoryEvidence]


class PostmortemDraftUpdate(BaseModel):
    markdown: str = Field(min_length=20, max_length=50000)


class SimilarIncidentComparison(BaseModel):
    incident_id: str
    memory_id: Optional[str] = None
    date: Optional[str] = None
    service: str
    deployment_context: str
    symptoms: str
    error_signals: str
    actions_and_outcomes: str
    confirmed_root_cause: str
    resolution: str
    similarity_terms: list[str]
    differences: list[str]
    why_relevant: str
    relevance: Optional[float] = None


class AnalysisResponse(BaseModel):
    incident: dict
    recommendation: Recommendation
    evidence: list[dict]
    similar_incidents: list[SimilarIncidentComparison]
    memory_stats: dict[str, int]
    analysis_id: int


class RecommendationFeedbackResponse(BaseModel):
    analysis_id: int
    accepted: bool
    note: str
    created_at: datetime
    updated_at: datetime


class EvaluationRunResponse(BaseModel):
    id: int
    status: str
    created_at: datetime
    result: dict


class EvaluationLatestResponse(BaseModel):
    id: Optional[int] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    result: Optional[dict] = None
    evaluation: Optional[dict] = None


class AnalyticsResponse(BaseModel):
    measured_from: str
    incident_count: int
    investigation_count: int
    investigations_with_recalled_results: int
    recommendations_with_citations: int
    citation_validity: Optional[float]
    valid_citations: int
    citation_count: int
    successful_hindsight_retains: int
    distinct_incidents_with_retained_outcomes: int
    action_outcomes: dict[str, int]
    recommendation_feedback: dict[str, int]
    latest_evaluation: Optional[dict] = None


class PostmortemResponse(BaseModel):
    id: int
    incident_id: str
    report: PostmortemReport
    markdown: str
    finalized: bool
    retained_at: Optional[datetime] = None
    updated_at: datetime


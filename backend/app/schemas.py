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


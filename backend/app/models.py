from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON


def utcnow():
    return datetime.now(timezone.utc)


class Incident(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    timestamp: datetime = Field(default_factory=utcnow)
    service: str = "checkout-api"
    severity: str = "SEV-2"
    symptoms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    error_signatures: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    deployment: str = "unknown"
    configuration_context: str = ""
    suspected_causes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    confirmed_root_cause: Optional[str] = None
    resolution: Optional[str] = None
    resolution_minutes: Optional[int] = None
    status: str = "investigating"
    is_synthetic: bool = True
    hindsight_document_id: Optional[str] = None
    retained_at: Optional[datetime] = None


class Action(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(index=True, foreign_key="incident.id")
    action: str
    outcome: str
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ActionSubmission(SQLModel, table=True):
    submission_id: str = Field(primary_key=True)
    action_id: int = Field(foreign_key="action.id", unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class Analysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(index=True, foreign_key="incident.id")
    recommendation: dict = Field(default_factory=dict, sa_column=Column(JSON))
    evidence: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class MemoryRetention(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(index=True)
    document_id: str
    reason: str
    action_count: int = 0
    has_resolution: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class RecommendationFeedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    analysis_id: int = Field(foreign_key="analysis.id", unique=True, index=True)
    accepted: bool
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EvaluationRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    status: str
    result: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Postmortem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(foreign_key="incident.id", unique=True, index=True)
    report: dict = Field(default_factory=dict, sa_column=Column(JSON))
    markdown: str = ""
    finalized: bool = False
    retained_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


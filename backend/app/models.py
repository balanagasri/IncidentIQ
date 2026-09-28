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


class Analysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(index=True, foreign_key="incident.id")
    recommendation: dict = Field(default_factory=dict, sa_column=Column(JSON))
    evidence: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


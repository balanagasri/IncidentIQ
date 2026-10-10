from datetime import datetime, timezone
from app.models import Action, Analysis, Incident
from app.postmortems import build_postmortem, render_markdown


def test_postmortem_marks_missing_impact_and_root_cause_unknown_and_uses_recorded_events():
    incident = Incident(id="INC-TEST-PM", title="Checkout timeout", service="checkout-api",
                        symptoms=["checkout requests timeout"], timestamp=datetime(2026, 9, 1, tzinfo=timezone.utc))
    action = Action(incident_id=incident.id, action="Restart pod", outcome="failed", notes="Timeout returned",
                    created_at=datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc))
    analysis = Analysis(incident_id=incident.id, recommendation={
        "hypotheses": [{"cause": "Pool saturation", "rationale": "Possible from current symptoms", "classification": "HYPOTHESIS"}],
        "recommended_steps": [{"step": "Inspect pool wait", "expected_observation": "Waits may be elevated"}],
        "evidence_memory_ids": ["INC-HIST"],
        "memory_evidence": [{"incident_id": "INC-HIST", "reason": "Cited", "outcome_summary": "Pool increase succeeded"}],
    }, created_at=datetime(2026, 9, 1, 0, 1, tzinfo=timezone.utc))

    report = build_postmortem(incident, [action], [analysis])
    markdown = render_markdown(report)

    assert report.impact.startswith("Unknown:")
    assert report.confirmed_root_cause.startswith("Unknown:")
    assert report.actions[0].outcome == "failed"
    assert report.contributing_factors[0].classification == "HYPOTHESIS"
    assert report.memories_informed[0].incident_id == "INC-HIST"
    assert "Pool increase succeeded" in markdown
    assert "Impact" in markdown and "Unknown:" in markdown

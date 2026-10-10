"""Factual postmortem drafts assembled from persisted incident records."""
from typing import Any
from .models import Action, Analysis, Incident
from .schemas import PostmortemFactor, PostmortemReport, TimelineEntry


def build_postmortem(incident: Incident, actions: list[Action], analyses: list[Analysis]) -> PostmortemReport:
    latest = max(analyses, key=lambda item: item.created_at) if analyses else None
    recommendation = latest.recommendation if latest and isinstance(latest.recommendation, dict) else {}
    memories = recommendation.get("memory_evidence") or []
    evidence_ids = {str(item.get("incident_id")) for item in memories if isinstance(item, dict) and item.get("incident_id")}

    factors: list[PostmortemFactor] = []
    if incident.confirmed_root_cause:
        factors.append(PostmortemFactor(statement=incident.confirmed_root_cause, classification="FACT"))
    for hypothesis in recommendation.get("hypotheses", []):
        if not isinstance(hypothesis, dict) or not hypothesis.get("cause"):
            continue
        classification = "FACT" if hypothesis.get("classification") == "FACT" else "HYPOTHESIS"
        factors.append(PostmortemFactor(
            statement=f"{hypothesis['cause']}: {hypothesis.get('rationale', '')}".rstrip(": "),
            classification=classification,
            evidence_ids=sorted(evidence_ids) if classification == "HYPOTHESIS" else [],
        ))

    timeline = [TimelineEntry(timestamp=incident.timestamp, event=f"Incident opened: {incident.title}", source="incident")]
    timeline.extend(TimelineEntry(timestamp=action.created_at, event=f"Action: {action.action} — {action.outcome}. {action.notes}".strip(), source="engineer") for action in actions)
    timeline.extend(TimelineEntry(timestamp=analysis.created_at, event="Incident analysis generated", source="system") for analysis in analyses)
    if incident.status == "resolved":
        timeline.append(TimelineEntry(
            event=f"Incident marked resolved; reported resolution time: {incident.resolution_minutes if incident.resolution_minutes is not None else 'unknown'} minutes.",
            source="engineer",
        ))
    timeline.sort(key=lambda item: (item.timestamp is None, item.timestamp.isoformat() if item.timestamp else ""))

    lessons = [
        f"Engineer reported {action.outcome} for '{action.action}'." + (f" Notes: {action.notes}" if action.notes else "")
        for action in actions
    ] or ["No engineer-reported intervention outcomes are recorded."]
    followups = [
        f"{item.get('step', '')} — expected observation: {item.get('expected_observation', 'not specified')}"
        for item in recommendation.get("recommended_steps", []) if isinstance(item, dict) and item.get("step")
    ]
    if not followups:
        followups = ["No follow-up recommendations are recorded in an analysis."]

    report = PostmortemReport(
        summary=(f"{incident.title}. Service: {incident.service}; severity: {incident.severity}. "
                 f"Reported symptoms: {'; '.join(incident.symptoms) or 'none recorded'}."),
        impact="Unknown: affected users, transactions, and business impact are not captured in this MVP.",
        timeline=timeline,
        confirmed_root_cause=incident.confirmed_root_cause or "Unknown: no confirmed root cause is recorded.",
        contributing_factors=factors,
        actions=[{"action": action.action, "outcome": action.outcome, "notes": action.notes} for action in actions],
        resolution_status=incident.status,
        resolution=incident.resolution or "Unknown: no resolution is recorded.",
        lessons_learned=lessons,
        follow_up_recommendations=followups,
        memories_informed=memories,
    )
    return report


def render_markdown(report: PostmortemReport | dict[str, Any]) -> str:
    data = report.model_dump(mode="json") if isinstance(report, PostmortemReport) else report
    lines = [
        "# Incident Postmortem", "", "## Summary", data["summary"], "",
        "## Impact", data["impact"], "", "## Timeline",
    ]
    for entry in data["timeline"]:
        timestamp = entry.get("timestamp") or "Time not recorded"
        lines.append(f"- **{timestamp}** — {entry['event']} ({entry['source']})")
    lines.extend(["", "## Confirmed Root Cause", data["confirmed_root_cause"], "", "## Contributing Factors"])
    lines.extend([f"- **{factor['classification']}** — {factor['statement']}" + (f" (evidence: {', '.join(factor['evidence_ids'])})" if factor.get("evidence_ids") else "") for factor in data["contributing_factors"]] or ["- None recorded."])
    lines.extend(["", "## Actions and Outcomes"])
    lines.extend([f"- **{item['outcome']}** — {item['action']}" + (f": {item['notes']}" if item.get("notes") else "") for item in data["actions"]] or ["- No actions recorded."])
    lines.extend(["", "## Resolution", f"Status: {data['resolution_status']}", data["resolution"], "", "## Lessons Learned"])
    lines.extend([f"- {item}" for item in data["lessons_learned"]])
    lines.extend(["", "## Follow-up Recommendations"])
    lines.extend([f"- {item}" for item in data["follow_up_recommendations"]])
    lines.extend(["", "## Hindsight Memories Informing This Report"])
    lines.extend([f"- **{item['incident_id']}** — {item['outcome_summary']}" for item in data["memories_informed"]] or ["- No cited Hindsight memories are recorded."])
    return "\n".join(lines).strip() + "\n"

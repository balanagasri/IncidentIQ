"""Thin HTTP adapter to the real Hindsight Memory API."""
from typing import Any
import httpx
from .config import get_settings


class HindsightError(RuntimeError):
    pass


class HindsightService:
    def __init__(self):
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.hindsight_api_key:
            raise HindsightError("HINDSIGHT_API_KEY is required to use Hindsight")
        return {"Authorization": f"Bearer {self.settings.hindsight_api_key}", "Content-Type": "application/json"}

    @property
    def bank_url(self) -> str:
        return f"{self.settings.hindsight_base_url.rstrip('/')}/v1/default/banks/{self.settings.hindsight_bank_id}"

    async def retain(self, incident: dict[str, Any], document_id: str) -> dict[str, Any]:
        content = self._narrative(incident)
        item = {
            "content": content,
            "context": "synthetic software incident outcome; distinguish attempted, successful, failed, and unresolved actions",
            "timestamp": incident.get("timestamp"),
            "document_id": document_id,
            "tags": ["team:demo-sre", f"service:{incident.get('service', 'unknown')}", "type:incident"],
            "metadata": {"incident_id": str(incident["id"]), "service": str(incident.get("service", "unknown")), "source": "incidentiq", "synthetic": str(incident.get("is_synthetic", True)).lower()},
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f"{self.bank_url}/memories", headers=self._headers(), json={"items": [item]})
        if response.is_error:
            raise HindsightError(f"Hindsight retain failed ({response.status_code}): {response.text[:400]}")
        return response.json()

    async def recall(self, query: str) -> list[dict[str, Any]]:
        body = self._recall_payload(query)
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(f"{self.bank_url}/memories/recall", headers=self._headers(), json=body)
        if response.is_error:
            raise HindsightError(f"Hindsight recall failed ({response.status_code}): {response.text[:400]}")
        data = response.json()
        return data.get("results", [])

    @staticmethod
    def _recall_payload(query: str) -> dict[str, Any]:
        return {"query": query, "budget": "mid", "max_tokens": 5000,
                "tags": ["team:demo-sre"], "tags_match": "all_strict",
                "types": ["experience", "world", "observation"],
                "include": {"chunks": {}}}

    @staticmethod
    def _narrative(i: dict[str, Any]) -> str:
        actions = i.get("actions", [])
        action_lines = [f"- {a.get('action')}: {a.get('outcome')} — {a.get('notes', '')}" for a in actions]
        if not action_lines:
            action_lines = ["- No interventions recorded yet; do not infer outcomes."]
        return "\n".join([
            f"Incident {i['id']} ({i.get('timestamp')}) affected {i.get('service')} at severity {i.get('severity')}.",
            f"Symptoms: {'; '.join(i.get('symptoms', []))}",
            f"Error signatures: {'; '.join(i.get('error_signatures', []))}",
            f"Deployment/version: {i.get('deployment')}. Configuration context: {i.get('configuration_context')}",
            f"Suspected causes (unconfirmed): {'; '.join(i.get('suspected_causes', [])) or 'none recorded'}",
            "Attempted interventions and reported outcomes:\n" + "\n".join(action_lines),
            f"Confirmed root cause: {i.get('confirmed_root_cause') or 'not confirmed'}",
            f"Resolution: {i.get('resolution') or 'not resolved'}; resolution time: {i.get('resolution_minutes') if i.get('resolution_minutes') is not None else 'unknown'} minutes.",
        ])


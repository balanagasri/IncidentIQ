"""Thin HTTP adapter to the real Hindsight Memory API."""
import asyncio
from typing import Any
import httpx
from .config import get_settings


class HindsightError(RuntimeError):
    def __init__(self, message: str, *, operation: str | None = None, attempts: int | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.operation = operation
        self.attempts = attempts
        self.cause_type = type(cause).__name__ if cause else None


class HindsightService:
    MAX_TRANSPORT_RETRIES = 2
    RETRY_DELAYS_SECONDS = (0.1, 0.2)

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
        response = await self._post("/memories", {"items": [item]}, "retain")
        if response.is_error:
            raise HindsightError(f"Hindsight retain failed ({response.status_code}): {response.text[:400]}")
        return response.json()

    async def recall(self, query: str) -> list[dict[str, Any]]:
        body = self._recall_payload(query)
        response = await self._post("/memories/recall", body, "recall")
        if response.is_error:
            raise HindsightError(f"Hindsight recall failed ({response.status_code}): {response.text[:400]}")
        data = response.json()
        return data.get("results", [])

    async def _post(self, path: str, payload: dict[str, Any], operation: str) -> httpx.Response:
        """Retry only transient HTTP transport failures; HTTP responses are handled normally."""
        headers = self._headers()
        async with httpx.AsyncClient(timeout=45) as client:
            for attempt in range(self.MAX_TRANSPORT_RETRIES + 1):
                try:
                    return await client.post(f"{self.bank_url}{path}", headers=headers, json=payload)
                except httpx.TransportError as exc:
                    if attempt >= self.MAX_TRANSPORT_RETRIES:
                        total_attempts = attempt + 1
                        raise HindsightError(
                            f"Hindsight {operation} failed after {total_attempts} attempts due to "
                            f"{type(exc).__name__}: {exc}",
                            operation=operation,
                            attempts=total_attempts,
                            cause=exc,
                        ) from exc
                    await asyncio.sleep(self.RETRY_DELAYS_SECONDS[attempt])
        raise AssertionError("unreachable")

    @staticmethod
    def _recall_payload(query: str) -> dict[str, Any]:
        return {"query": query, "budget": "mid", "max_tokens": 5000,
                "tags": ["team:demo-sre"], "tags_match": "all_strict",
                "types": ["experience", "world", "observation"],
                "include": {"chunks": {}}}

    @staticmethod
    def _narrative(i: dict[str, Any]) -> str:
        actions = i.get("actions", [])
        action_lines = [
            f"- The engineer reported that the intervention '{a.get('action')}' was {a.get('outcome')}. "
            f"Engineer notes: {a.get('notes') or 'No notes recorded.'}"
            for a in actions
        ]
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


from app.hindsight import HindsightService
from app.agent import _incident_id
from app.main import _memory_service
from app import hindsight as hindsight_module
from app.hindsight import HindsightError
import httpx
import pytest


def test_narrative_preserves_failed_and_successful_actions():
    text = HindsightService._narrative({
        "id": "INC-10", "service": "checkout-api", "actions": [
            {"action": "Restart", "outcome": "failed", "notes": "It returned."},
            {"action": "Raise pool", "outcome": "successful", "notes": "Latency recovered."},
        ]
    })
    assert "Restart: failed" in text
    assert "Raise pool: successful" in text
    assert "confirmed" in text.lower()


def test_recall_payload_requests_raw_chunks_as_object():
    payload = HindsightService._recall_payload("checkout timeouts")
    chunks = payload["include"]["chunks"]

    assert type(chunks) is dict
    assert chunks == {}


def test_memory_id_comes_from_returned_hindsight_result():
    assert _incident_id({"metadata": {"incident_id": "INC-22"}}) == "INC-22"
    assert _incident_id({"text": "Incident INC-23 (2026-08-01) had checkout timeouts"}) == "INC-23"
    assert _incident_id({"text": "No incident identity here"}) == ""


def test_recalled_service_uses_hindsight_provenance():
    assert _memory_service({"metadata": {"service": "payments-worker"}}, "checkout-api") == "payments-worker"
    assert _memory_service({"tags": ["service:payments-gateway"]}, "checkout-api") == "payments-gateway"


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.is_error = status_code >= 400
        self.text = "request rejected"
        self._payload = payload or {"results": [{"text": "memory"}]}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_recall_retries_remote_protocol_error_then_succeeds(monkeypatch):
    client = _Client([httpx.RemoteProtocolError("disconnected"), _Response()])
    monkeypatch.setattr(hindsight_module.httpx, "AsyncClient", lambda **kwargs: client)
    async def no_wait(_delay):
        return None
    monkeypatch.setattr(hindsight_module.asyncio, "sleep", no_wait)

    results = await HindsightService().recall("checkout timeouts")

    assert results == [{"text": "memory"}]
    assert client.calls == 2


@pytest.mark.asyncio
async def test_recall_persistent_transport_failure_returns_structured_error(monkeypatch):
    error = httpx.RemoteProtocolError("server disconnected")
    client = _Client([error, error, error])
    monkeypatch.setattr(hindsight_module.httpx, "AsyncClient", lambda **kwargs: client)
    async def no_wait(_delay):
        return None
    monkeypatch.setattr(hindsight_module.asyncio, "sleep", no_wait)

    with pytest.raises(HindsightError, match="recall failed after 3 attempts") as caught:
        await HindsightService().recall("checkout timeouts")

    assert client.calls == 3
    assert caught.value.operation == "recall"
    assert caught.value.attempts == 3
    assert caught.value.cause_type == "RemoteProtocolError"


@pytest.mark.asyncio
async def test_recall_does_not_retry_ordinary_4xx(monkeypatch):
    client = _Client([_Response(status_code=422), _Response()])
    monkeypatch.setattr(hindsight_module.httpx, "AsyncClient", lambda **kwargs: client)

    with pytest.raises(HindsightError, match=r"Hindsight recall failed \(422\)"):
        await HindsightService().recall("checkout timeouts")

    assert client.calls == 1


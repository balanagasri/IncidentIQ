import pytest
from app.config import get_settings
from app.hindsight import HindsightService


@pytest.mark.asyncio
async def test_live_hindsight_recall_when_configured():
    settings = get_settings()
    if not settings.hindsight_api_key:
        pytest.skip("Live Hindsight credentials are not configured in this environment")
    results = await HindsightService().recall("checkout connection pool timeout incident intervention outcome")
    assert isinstance(results, list)

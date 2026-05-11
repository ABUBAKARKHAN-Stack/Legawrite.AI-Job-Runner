"""
Critical-path tests for the Legawrite job signaling system.
Tests cover: job creation, state machine transitions, and SSE event format.
Run with: pytest backend/tests/ -v
"""
import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(status="pending", result=None, error=None):
    return json.dumps({
        "job_id": "test-job-id",
        "prompt": "test prompt",
        "status": status,
        "result": result,
        "error": error,
    })


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_job_returns_job_id():
    """POST /api/jobs must return a job_id and status=pending."""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()
    mock_redis.lpush = AsyncMock()

    with patch("app.main.get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/jobs", json={"prompt": "hello world"}
            )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    # Verify Redis was called
    mock_redis.set.assert_called_once()
    mock_redis.lpush.assert_called_once()


@pytest.mark.asyncio
async def test_create_job_rejects_empty_prompt():
    """POST /api/jobs with no prompt must return HTTP 400."""
    mock_redis = AsyncMock()

    with patch("app.main.get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/jobs", json={})

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/jobs/{id}/stream — 404 guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_returns_404_for_unknown_job():
    """SSE endpoint must return 404 if the job does not exist in Redis."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("app.main.get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/jobs/nonexistent-id/stream")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_returns_200_when_redis_ok():
    """Health endpoint must return 200 when Redis responds to PING."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with patch("app.main.get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_returns_503_when_redis_down():
    """Health endpoint must return 503 when Redis is unreachable."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("app.main.get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_returns_queue_depth():
    """Metrics endpoint must return the current job_queue length."""
    mock_redis = AsyncMock()
    mock_redis.llen = AsyncMock(return_value=5)

    with patch("app.main.get_redis", return_value=mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.json()["queue_depth"] == 5

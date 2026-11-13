"""
test_ai_health.py — Integration test for the Python AI service /health endpoint.

Tests live server on localhost:8000 if running, or falls back to TestClient.
"""

from __future__ import annotations

import pytest
import httpx


AI_BASE_URL = "http://localhost:8000"


@pytest.mark.integration
def test_health_endpoint_returns_ok():
    """
    The /health endpoint must return HTTP 200 with status=ok.
    """
    try:
        response = httpx.get(f"{AI_BASE_URL}/health", timeout=1.0)
    except Exception:
        from starlette.testclient import TestClient
        from services.ai.main import app
        client = TestClient(app)
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ai"
    assert "timestamp" in body
    assert "llm_provider" in body

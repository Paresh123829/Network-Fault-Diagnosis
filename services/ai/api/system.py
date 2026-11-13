"""
system.py — Health and system status router for AI service.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from services.ai.config import get_settings
except ImportError:
    from config import get_settings

from services.ai.agents.oversight.kill_switch import KillSwitchManager
from services.ai.api.kill_switch import shared_kill_switch_mgr
from network.containerlab.runtime.mock_provider import mock_clab_provider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])
settings = get_settings()

# Default shared kill switch manager
_kill_switch_mgr = shared_kill_switch_mgr


class SystemStatusResponse(BaseModel):
    service: str = "ai_engine"
    status: str = "healthy"
    version: str = "0.8.0"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    environment: str
    llm_provider: str
    llm_model: str
    network_provider_mode: str
    mock_provider: bool
    provider_name: str
    qdrant_connected: bool
    mongodb_connected: bool
    kill_switch_active: bool
    active_incidents_count: int
    uptime_seconds: float = 0.0


_START_TIME = datetime.now(timezone.utc)


@router.get("/health", tags=["system"])
async def health_check() -> Dict[str, Any]:
    """Lightweight operational health check."""
    return {
        "service": "ai",
        "status": "ok",
        "version": "0.8.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "network_provider": "ContainerlabMockProvider",
        "mock_mode": True,
    }


@router.get("/system/status", response_model=SystemStatusResponse, tags=["system"])
async def system_status() -> SystemStatusResponse:
    """Comprehensive system and provider status endpoint."""
    uptime = (datetime.now(timezone.utc) - _START_TIME).total_seconds()
    
    # Check Qdrant status
    qdrant_ok = False
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=0.5)
        # Attempt minimal check
        client.get_collections()
        qdrant_ok = True
    except Exception:
        qdrant_ok = False

    # Check MongoDB status
    mongo_ok = False
    try:
        import pymongo
        mc = pymongo.MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=500)
        mc.server_info()
        mongo_ok = True
    except Exception:
        mongo_ok = False

    # Check active incidents count
    active_incidents = 0
    try:
        from services.ai.api.incidents import get_active_incident_count
        active_incidents = get_active_incident_count()
    except Exception:
        active_incidents = 0

    return SystemStatusResponse(
        service="ai_engine",
        status="healthy",
        version="0.8.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment=settings.python_env,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        network_provider_mode="containerlab_mock",
        mock_provider=True,
        provider_name="ContainerlabMockProvider",
        qdrant_connected=qdrant_ok,
        mongodb_connected=mongo_ok,
        kill_switch_active=_kill_switch_mgr.is_global_active(),
        active_incidents_count=active_incidents,
        uptime_seconds=uptime,
    )

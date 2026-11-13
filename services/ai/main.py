"""
main.py — FastAPI entry point for the Python AI service.

Phase 0: Only the /health endpoint is implemented.
Agents will be registered as routers in later phases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from services.ai.config import get_settings
except ImportError:
    from config import get_settings

# ─── Logging setup ───────────────────────────────────────────────────────────
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("ai_service")

# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="CNT Fault Diagnosis — AI Service",
    description="Multi-agent AI service for network fault diagnosis and safe remediation.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"])
async def health() -> dict:
    """
    Simple health check.
    Returns service status, version, and current UTC timestamp.
    """
    logger.info("Health check requested")
    return {
        "service": "ai",
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "environment": settings.python_env,
    }


# ─── API v1 Routers ────────────────────────────────────────────────────────
try:
    from services.ai.api.system import router as system_router
    from services.ai.api.incidents import router as incidents_router
    from services.ai.api.diagnosis import router as diagnosis_router
    from services.ai.api.topology import router as topology_router
    from services.ai.api.knowledge import router as knowledge_router
    from services.ai.api.remediation import router as remediation_router
    from services.ai.api.kill_switch import router as kill_switch_router
    from services.ai.api.audit import router as audit_router
    from services.ai.api.events import router as events_router

    app.include_router(system_router, prefix="/api/v1")
    app.include_router(incidents_router, prefix="/api/v1")
    app.include_router(diagnosis_router, prefix="/api/v1")
    app.include_router(topology_router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(remediation_router, prefix="/api/v1")
    app.include_router(kill_switch_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    logger.info("Successfully registered all API v1 routers")
except Exception as _api_exc:
    logger.error("Failed to register API v1 routers: %s", _api_exc, exc_info=True)


# ─── RAG router ─────────────────────────────────────────────────────────────
try:
    from services.rag.src.router import router as rag_router
    app.include_router(rag_router)
except Exception as _rag_imp_exc:
    logger.warning("Could not register RAG router: %s", _rag_imp_exc)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.ai_service_host,
        port=settings.ai_service_port,
        reload=(settings.python_env == "development"),
        log_level=settings.log_level.lower(),
    )

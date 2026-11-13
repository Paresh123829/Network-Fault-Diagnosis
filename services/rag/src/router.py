"""
router.py — FastAPI Router for RAG Operations.

Endpoints:
  - GET  /rag/health
  - GET  /rag/stats
  - POST /rag/search
  - POST /rag/ingest
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .service import RAGService
from .config import RAW_DATA_DIR, MANIFESTS_DIR

router = APIRouter(prefix="/rag", tags=["rag"])
_service_instance: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    global _service_instance
    if _service_instance is None:
        _service_instance = RAGService()
    return _service_instance


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query string")
    top_k: int = Field(default=5, ge=1, le=20)
    protocol: Optional[str] = None
    fault_category: Optional[str] = None
    vendor: Optional[str] = None
    min_relevance: Optional[float] = None
    search_mode: str = Field(default="hybrid", description="dense, lexical, or hybrid")


class IngestRequest(BaseModel):
    raw_dir: Optional[str] = None


@router.get("/health")
def rag_health():
    """Health status of Qdrant and RAG service."""
    svc = get_rag_service()
    q_health = svc.vector_store.health_check()
    emb_ok = svc.embedding_service.is_available
    return {
        "status": "ok" if q_health.get("status") == "healthy" and emb_ok else "degraded",
        "qdrant": q_health,
        "embedding_model": svc.config.embedding_model_name,
        "embedding_available": emb_ok,
    }


@router.get("/stats")
def rag_stats():
    """Returns vector collection statistics and vocabulary counts."""
    svc = get_rag_service()
    stats = svc.vector_store.get_collection_stats()
    stats["bm25_vocab_size"] = len(svc.hybrid_searcher.bm25_index.doc_freqs)
    stats["indexed_docs_in_memory"] = len(svc.indexed_docs)
    stats["indexed_chunks_in_memory"] = len(svc.indexed_chunks)
    return stats


@router.post("/search")
def rag_search(req: SearchRequest):
    """Executes dense, lexical, or hybrid knowledge search."""
    svc = get_rag_service()
    try:
        evidence = svc.query(
            query_text=req.query,
            top_k=req.top_k,
            protocol=req.protocol,
            fault_category=req.fault_category,
            vendor=req.vendor,
            min_relevance=req.min_relevance,
            search_mode=req.search_mode,
        )
        return evidence.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ingest")
def rag_ingest(req: IngestRequest):
    """Triggers corpus ingestion and re-indexing."""
    svc = get_rag_service()
    raw_path = Path(req.raw_dir) if req.raw_dir else RAW_DATA_DIR
    if not raw_path.exists():
        raise HTTPException(status_code=400, detail=f"Directory not found: {raw_path}")

    summary = svc.ingest_corpus(raw_dir=raw_path, manifest_output_dir=MANIFESTS_DIR)
    return summary


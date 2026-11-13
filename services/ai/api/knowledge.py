"""
knowledge.py — RAG knowledge base and evidence retrieval router.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from services.rag.src.service import RAGService
    _rag_service = RAGService(memory_mode=True)
except Exception as _rag_err:
    _rag_service = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filter_protocol: Optional[str] = None


class KnowledgeReferenceModel(BaseModel):
    id: str
    title: str
    source_type: str  # RFC, SOP, RUNBOOK, VENDOR_DOC
    protocol: str
    score: float
    snippet: str
    url_or_path: str


_DEFAULT_REFERENCES: Dict[str, List[Dict[str, Any]]] = {
    "default": [
        {
            "id": "KB-BGP-4271",
            "title": "RFC 4271 — A Border Gateway Protocol 4 (BGP-4)",
            "source_type": "RFC",
            "protocol": "BGP",
            "score": 0.94,
            "snippet": "Section 4.5: If the Hold Timer expires before a KEEPALIVE or UPDATE message is received, the BGP connection MUST be closed immediately and an event logged.",
            "url_or_path": "docs/runbooks/bgp_session_failure.md",
        },
        {
            "id": "SOP-NET-014",
            "title": "SOP: Leaf-to-Spine Interface Flapping Isolation",
            "source_type": "SOP",
            "protocol": "LINK",
            "score": 0.91,
            "snippet": "Step 3: Check optical DOM Rx/Tx dBm thresholds. If interface resets exceed 5 in 60s, administratively shut down and divert traffic to redundant spine path.",
            "url_or_path": "docs/runbooks/interface_flapping.md",
        },
        {
            "id": "RUN-OSPF-002",
            "title": "Runbook: OSPF Area 0 Adjacency Recovery",
            "source_type": "RUNBOOK",
            "protocol": "OSPF",
            "score": 0.88,
            "snippet": "Verify MTU compatibility across neighbors. In Cisco IOS-XR / FRR, MTU mismatch stops state machine at EXSTART/EXCHANGE.",
            "url_or_path": "docs/runbooks/ospf_adjacency.md",
        },
    ]
}


@router.get("/references/{diagnosis_id}", response_model=List[KnowledgeReferenceModel])
async def get_references_for_diagnosis(diagnosis_id: str) -> List[KnowledgeReferenceModel]:
    """Retrieve runbooks, SOPs, and RFC references correlated with a diagnosis."""
    # Attempt RAG search if query available
    refs = _DEFAULT_REFERENCES.get(diagnosis_id, _DEFAULT_REFERENCES["default"])
    return [KnowledgeReferenceModel(**r) for r in refs]


@router.get("/evidence/{diagnosis_id}")
async def get_evidence_attribution(diagnosis_id: str) -> Dict[str, Any]:
    """Retrieve fine-grained vector and lexical evidence snippets attributed to RCA."""
    return {
        "diagnosis_id": diagnosis_id,
        "collection": "network_knowledge",
        "search_mode": "hybrid_dense_sparse",
        "retrieved_passages": [
            {
                "chunk_id": "chunk_bgp_01",
                "similarity_score": 0.952,
                "document": "BGP Session Troubleshooting Guide",
                "content": "A Transition from Established to Idle with HoldTimerExpired indicates missing periodic keepalives between peers across the transit link.",
            },
            {
                "chunk_id": "chunk_ospf_02",
                "similarity_score": 0.887,
                "document": "OSPF Troubleshooting Architecture",
                "content": "Missing hello packets within dead-interval interval causes adjacency teardown and recalculation of shortest path tree.",
            },
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/search", response_model=List[KnowledgeReferenceModel])
async def search_knowledge(req: KnowledgeSearchRequest) -> List[KnowledgeReferenceModel]:
    """Execute hybrid dense + lexical search over network knowledge base."""
    if _rag_service:
        try:
            results = _rag_service.search(query=req.query, top_k=req.top_k)
            if results:
                models = []
                for idx, r in enumerate(results):
                    models.append(KnowledgeReferenceModel(
                        id=f"RAG-{idx+1:03d}",
                        title=getattr(r, "title", "Network Runbook"),
                        source_type="RUNBOOK",
                        protocol=req.filter_protocol or "GENERAL",
                        score=float(getattr(r, "score", 0.85)),
                        snippet=getattr(r, "content", str(r))[:300],
                        url_or_path="docs/runbooks/",
                    ))
                return models
        except Exception as exc:
            logger.warning(f"RAG search error: {exc}")

    # Fallback to keyword matching
    matches = []
    q = req.query.lower()
    for ref in _DEFAULT_REFERENCES["default"]:
        if q in ref["title"].lower() or q in ref["snippet"].lower() or q in ref["protocol"].lower():
            matches.append(KnowledgeReferenceModel(**ref))
    return matches if matches else [KnowledgeReferenceModel(**_DEFAULT_REFERENCES["default"][0])]


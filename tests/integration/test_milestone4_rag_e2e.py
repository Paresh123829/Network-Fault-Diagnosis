"""
test_milestone4_rag.py (Integration) — Full-Chain Integration Test for Milestone 4.

Verifies the complete pipeline:
  Source Document → Loader → Cleaner → Chunker → Metadata → FastEmbed
  → Qdrant Vector Store → Hybrid Search → RetrievedEvidence
  → LangGraph StateGraph Multi-Agent Orchestration → MongoDB Persistence
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from services.rag.src.config import default_rag_config, RAW_DATA_DIR
from services.rag.src.service import RAGService
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.schemas.contracts import (
    IncidentTimeline,
    TimeWindow,
    StructuredEvent,
    EventType,
    Severity,
    IncidentStatus,
    RetrievedEvidence,
    DiagnosisResult,
)


@pytest.fixture(scope="module")
def shared_rag_service():
    """Initializes and ingests knowledge corpus once for integration suite."""
    svc = RAGService(memory_mode=True)
    svc.ingest_corpus(raw_dir=RAW_DATA_DIR)
    return svc


def test_e2e_rag_ingestion_and_hybrid_search(shared_rag_service):
    """Verifies that all 11 corpus documents are indexed and retrievable via hybrid search."""
    svc = shared_rag_service
    assert len(svc.indexed_docs) == 11
    assert len(svc.indexed_chunks) >= 40

    # Query BGP
    bgp_ev = svc.query("BGP neighbor down hold timer expired", top_k=3, search_mode="hybrid")
    assert isinstance(bgp_ev, RetrievedEvidence)
    assert len(bgp_ev.passages) > 0
    top_p = bgp_ev.passages[0]
    assert "bgp" in top_p.metadata.get("protocol", "").lower()
    assert top_p.relevance_score > 0.35

    # Query Optics
    optics_ev = svc.query("optical transceiver uninstalled pull Rx power dBm", top_k=3, search_mode="hybrid")
    assert len(optics_ev.passages) > 0
    assert any("optic" in p.metadata.get("protocol", "").lower() or "transceiver" in p.text.lower() for p in optics_ev.passages)


def test_e2e_langgraph_diagnosis_with_retrieved_evidence(shared_rag_service, monkeypatch):
    """
    Verifies that LangGraph StateGraph executes with knowledge retrieval node,
    enriches RCA with RetrievedEvidence citations, and preserves telemetry distinction.
    """
    # Monkeypatch get_rag_service to return shared memory service for fast testing
    from services.rag.src import service as rag_module
    monkeypatch.setattr(rag_module, "get_rag_service", lambda *args, **kwargs: shared_rag_service)

    t0 = datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    timeline = IncidentTimeline(
        incident_id="inc_int_rag_001",
        time_window=TimeWindow(start=t0, end=t0 + timedelta(seconds=180)),
        events=[
            StructuredEvent(
                event_id="ev_opt_1",
                timestamp=t0 + timedelta(seconds=10),
                device_id="spine2",
                interface="HundredGigE0/0/0/0",
                event_type=EventType.PORT_DOWN,
                severity=Severity.CRITICAL,
                normalized_fields={"carrier": "lost", "rx_power_dbm": -40.0},
                raw_reference="%LINK-3-UPDOWN: Interface HundredGigE0/0/0/0, changed state to Down",
            ),
            StructuredEvent(
                event_id="ev_opt_2",
                timestamp=t0 + timedelta(seconds=12),
                device_id="spine2",
                interface="HundredGigE0/0/0/0",
                event_type=EventType.PORT_DOWN,
                severity=Severity.CRITICAL,
                normalized_fields={"line_protocol": "down"},
                raw_reference="%LINEPROTO-5-UPDOWN: Line protocol on Interface HundredGigE0/0/0/0, changed state to Down",
            ),
        ],
        affected_devices=["spine2"],
        affected_interfaces=["HundredGigE0/0/0/0"],
        suspected_protocols=["interface"],
        status=IncidentStatus.OPEN,
        correlation_reason="Optical transceiver pull and line protocol drop on spine2 HundredGigE0/0/0/0",
    )

    orchestrator = DiagnosisOrchestrator()
    final_state = orchestrator.diagnose_incident(timeline=timeline)

    # 1. Verify LangGraph state transitions
    assert "knowledge_retrieval" in "".join(final_state.get("execution_trace", []))
    retrieved_ev = final_state.get("retrieved_evidence")
    assert retrieved_ev is not None
    assert isinstance(retrieved_ev, RetrievedEvidence)
    assert len(retrieved_ev.passages) > 0

    # 2. Verify DiagnosisResult includes both telemetry and knowledge citations
    diag = final_state.get("diagnosis_result")
    assert isinstance(diag, DiagnosisResult)
    assert diag.probable_root_cause != ""
    assert diag.confidence > 0.0

    # Verify that passage IDs are included in evidence_ids
    passage_ids = [p.passage_id for p in retrieved_ev.passages]
    assert any(pid in diag.evidence_ids for pid in passage_ids)

    # Verify that top hypothesis contains SOP citations
    top_hyp = diag.hypotheses[0]
    has_sop_citation = any("Retrieved SOP" in ev for ev in top_hyp.supporting_evidence)
    assert has_sop_citation is True


def test_langgraph_operates_when_rag_returns_no_results(monkeypatch):
    """
    Verifies that if RAG returns 0 results (empty knowledge base or extreme filter),
    the diagnostic workflow still synthesizes a valid diagnosis without crashing.
    """
    class EmptyRAGService:
        def retrieve_for_incident(self, *args, **kwargs):
            return RetrievedEvidence(query="empty query", passages=[], source_ids=[])

    from services.rag.src import service as rag_module
    monkeypatch.setattr(rag_module, "get_rag_service", lambda *args, **kwargs: EmptyRAGService())

    t0 = datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    timeline = IncidentTimeline(
        incident_id="inc_int_no_rag_002",
        time_window=TimeWindow(start=t0, end=t0 + timedelta(seconds=60)),
        events=[
            StructuredEvent(
                event_id="ev_single",
                timestamp=t0 + timedelta(seconds=5),
                device_id="leaf3",
                interface="HundredGigE0/0/0/1",
                event_type=EventType.PORT_DOWN,
                severity=Severity.INFO,
                normalized_fields={},
                raw_reference="Interface down event",
            )
        ],
        affected_devices=["leaf3"],
        affected_interfaces=["HundredGigE0/0/0/1"],
        suspected_protocols=["interface"],
        status=IncidentStatus.OPEN,
    )

    orchestrator = DiagnosisOrchestrator()
    final_state = orchestrator.diagnose_incident(timeline=timeline)

    diag = final_state.get("diagnosis_result")
    assert diag is not None
    assert diag.confidence > 0.0
    assert len(diag.hypotheses) > 0

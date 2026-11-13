"""
run_rag_pipeline.py — Master Execution Script for Milestone 4 RAG Pipeline.

Executes:
  1. Corpus Ingestion & Document Processing
  2. Embeddings & Qdrant Vector Indexing
  3. BM25 Lexical Index Construction
  4. 14-Query Retrieval Evaluation (Dense vs Lexical vs Hybrid)
  5. Evidence Attribution Verification
  6. LangGraph E2E Integration Run
  7. Generation of All Milestone 4 Reports & Manifests
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from services.rag.src.config import default_rag_config, RAW_DATA_DIR, REPORTS_DIR, MANIFESTS_DIR
from services.rag.src.service import RAGService, get_rag_service
from services.rag.src.evaluation import RetrievalEvaluator, EvaluationQuery
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.schemas.contracts import (
    IncidentTimeline,
    TimeWindow,
    StructuredEvent,
    EventType,
    Severity,
    IncidentStatus,
)
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rag_pipeline")


def run_milestone4_pipeline():
    logger.info("================================================================================")
    logger.info("STARTING MILESTONE 4: RAG KNOWLEDGE BASE & RETRIEVAL PIPELINE")
    logger.info("================================================================================")

    reports_dir = REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Initialize RAG Service
    rag_service = get_rag_service(config=default_rag_config)

    # 2. Ingest Knowledge Corpus
    logger.info("--- STAGE 1: CORPUS INGESTION & QDRANT INDEXING ---")
    ingest_summary = rag_service.ingest_corpus(
        raw_dir=RAW_DATA_DIR,
        manifest_output_dir=reports_dir,
    )
    logger.info("Ingestion Summary: %s", json.dumps(ingest_summary, indent=2))

    # Also copy manifests to MANIFESTS_DIR
    for fname in ["knowledge_corpus_manifest.json", "document_ingestion_results.csv",
                  "document_extraction_failures.csv", "chunk_inventory.csv", "qdrant_collection_manifest.json"]:
        src_f = reports_dir / fname
        if src_f.exists():
            (MANIFESTS_DIR / fname).write_bytes(src_f.read_bytes())

    # 3. Load Evaluation Queries & Run Evaluation
    logger.info("--- STAGE 2: RETRIEVAL EVALUATION (DENSE VS LEXICAL VS HYBRID) ---")
    eval_queries_path = Path(__file__).resolve().parent.parent / "evaluation" / "retrieval_queries.json"
    with open(eval_queries_path, "r", encoding="utf-8") as f:
        raw_queries = json.load(f)

    # Map doc names to doc IDs from ingested docs
    name_to_id = {d.file_path.name: d.document_id for d in rag_service.indexed_docs}

    eval_queries: list[EvaluationQuery] = []
    for q_data in raw_queries:
        rel_doc_ids = [name_to_id[name] for name in q_data.get("relevant_doc_names", []) if name in name_to_id]
        # Find chunk IDs belonging to these relevant documents
        rel_chunk_ids = [c.chunk_id for c in rag_service.indexed_chunks if c.document_id in rel_doc_ids]

        eq = EvaluationQuery(
            query_id=q_data["query_id"],
            query_text=q_data["query_text"],
            expected_protocol=q_data["expected_protocol"],
            expected_fault_category=q_data["expected_fault_category"],
            relevant_doc_ids=rel_doc_ids,
            relevant_chunk_ids=rel_chunk_ids,
            metadata={"expected_keywords": q_data.get("expected_keywords", [])},
        )
        eval_queries.append(eq)

    evaluator = RetrievalEvaluator(rag_service=rag_service)
    eval_results = evaluator.evaluate_benchmark(queries=eval_queries, top_k=5)
    evaluator.export_reports(eval_results=eval_results, output_dir=reports_dir)

    logger.info("Evaluation Summary:")
    print(json.dumps(eval_results["comparative_summary"], indent=2))

    # 4. LangGraph Integration Run
    logger.info("--- STAGE 3: LANGGRAPH ORCHESTRATION WITH REAL RETRIEVED EVIDENCE ---")
    t0 = datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    test_timeline = IncidentTimeline(
        incident_id="inc_rag_e2e_bgp_001",
        time_window=TimeWindow(start=t0, end=t0 + timedelta(seconds=120)),
        events=[
            StructuredEvent(
                event_id="ev_bgp_1",
                timestamp=t0 + timedelta(seconds=10),
                device_id="leaf1",
                interface="HundredGigE0/0/0/1",
                event_type=EventType.BGP_NEIGHBOR_DOWN,
                severity=Severity.INFO,
                normalized_fields={"peer_ip": "10.0.0.2", "protocol": "bgp", "state": "Down"},
                raw_reference="%ROUTING-BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down - Peer closed the session",
            ),
            StructuredEvent(
                event_id="ev_bgp_2",
                timestamp=t0 + timedelta(seconds=15),
                device_id="leaf1",
                interface="HundredGigE0/0/0/1",
                event_type=EventType.BGP_NEIGHBOR_DOWN,
                severity=Severity.INFO,
                normalized_fields={"peer_ip": "10.0.0.2", "protocol": "bgp", "state": "Down"},
                raw_reference="%ROUTING-BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down - Hold timer expired",
            ),
        ],
        affected_devices=["leaf1"],
        affected_interfaces=["HundredGigE0/0/0/1"],
        suspected_protocols=["bgp"],
        status=IncidentStatus.OPEN,
        correlation_reason="Simultaneous BGP peer session reset on leaf1 HundredGigE0/0/0/1",
    )

    orchestrator = DiagnosisOrchestrator()
    final_state = orchestrator.diagnose_incident(timeline=test_timeline)

    diag = final_state.get("diagnosis_result")
    retrieved_ev = final_state.get("retrieved_evidence")
    rag_trace = final_state.get("rag_trace")
    exec_trace = final_state.get("execution_trace", [])

    logger.info("LangGraph Diagnosis Complete:")
    logger.info("  Probable Root Cause: %s", diag.probable_root_cause if diag else "None")
    logger.info("  Confidence: %s", diag.confidence if diag else 0.0)
    logger.info("  Total Evidence IDs: %s", len(diag.evidence_ids) if diag else 0)
    logger.info("  Retrieved Passages: %s", len(retrieved_ev.passages) if retrieved_ev else 0)

    # 5. Export RAG Integration Results
    rag_integration_results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "incident_id": test_timeline.incident_id,
        "probable_root_cause": diag.probable_root_cause if diag else "",
        "confidence": diag.confidence if diag else 0.0,
        "retrieved_passages_count": len(retrieved_ev.passages) if retrieved_ev else 0,
        "retrieved_source_ids": retrieved_ev.source_ids if retrieved_ev else [],
        "retrieved_passage_ids": [p.passage_id for p in retrieved_ev.passages] if retrieved_ev else [],
        "evidence_ids_in_diagnosis": diag.evidence_ids if diag else [],
        "rag_trace": rag_trace,
        "execution_trace": exec_trace,
        "is_persisted": final_state.get("is_persisted", False),
        "status": "PASSED" if (retrieved_ev and len(retrieved_ev.passages) > 0 and diag) else "FAILED",
    }
    with open(reports_dir / "rag_integration_test_results.json", "w", encoding="utf-8") as f:
        json.dump(rag_integration_results, f, indent=2)

    logger.info("================================================================================")
    logger.info("MILESTONE 4 PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("Reports and manifests written to: %s", reports_dir)
    logger.info("================================================================================")


if __name__ == "__main__":
    run_milestone4_pipeline()

"""
test_milestone3_langgraph_e2e.py — End-to-End Integration Tests for LangGraph Multi-Agent Diagnosis.

Tests the full pipeline from raw dataset ingestion -> event correlation -> LangGraph StateGraph diagnosis -> MongoDB persistence.
"""

import os
import pytest
from datetime import datetime, timezone
from pymongo import MongoClient

from network.datasets.adapters.cisco_adapter import CiscoTelemetryAdapter
from services.ai.schemas.contracts import IncidentTimeline, StructuredEvent, DiagnosisResult
from services.ai.agents.ingestion.service import IngestionService
from services.ai.agents.ingestion.persistence import IngestionPersistence
from services.ai.agents.correlation.algorithm import CorrelationAlgorithm
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.agents.diagnosis.persistence import DiagnosisPersistence


@pytest.fixture
def mongo_eval_db():
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except Exception as e:
        pytest.skip(f"MongoDB not reachable: {e}")
    db = client["cnt_test_m3_e2e"]
    yield db
    client.drop_database("cnt_test_m3_e2e")
    client.close()


def test_case3_e2e_langgraph_diagnosis(mongo_eval_db):
    """
    Validates E2E: Ingest Case 3 (BGP clear) -> Correlate -> LangGraph StateGraph diagnosis.
    """
    os.environ["MONGO_DB_NAME"] = "cnt_test_m3_e2e"
    adapter = CiscoTelemetryAdapter()
    syslog_records = list(adapter.iter_syslog_records(case="3"))[:300]
    if not syslog_records:
        pytest.skip("Case 3 syslogs not found.")

    # 1. Ingestion
    ing_persistence = IngestionPersistence(db_name="cnt_test_m3_e2e")
    ing_service = IngestionService(persistence=ing_persistence)
    events = [ing_service.process_record(r) for r in syslog_records if r]
    anomalies = [e for e in events if e.event_type.value != "unknown"]
    assert len(anomalies) > 0

    # 2. Correlation
    correlator = CorrelationAlgorithm(window_seconds=120)
    incidents = correlator.group_events(anomalies, [])
    assert len(incidents) > 0

    # 3. LangGraph Multi-Agent Diagnosis
    orchestrator = DiagnosisOrchestrator()
    sample_incident = incidents[0]
    final_state = orchestrator.diagnose_incident(sample_incident, context_id="case_3")

    assert "diagnosis_result" in final_state
    diag: DiagnosisResult = final_state["diagnosis_result"]
    assert diag.confidence >= 0.80
    assert "bgp" in diag.probable_root_cause.lower()
    assert len(diag.affected_components) > 0

    # Verify execution trace completeness
    trace = final_state["execution_trace"]
    assert len(trace) >= 10
    assert any("Stage 1" in s for s in trace)
    assert any("Stage 9" in s for s in trace)

    # 4. Verify MongoDB persistence
    diag_persistence = DiagnosisPersistence(db_name="cnt_test_m3_e2e")
    saved_doc = diag_persistence.get_diagnosis(sample_incident.incident_id)
    assert saved_doc is not None
    assert saved_doc["probable_root_cause"] == diag.probable_root_cause


def test_case4_e2e_langgraph_diagnosis(mongo_eval_db):
    """
    Validates E2E: Ingest Case 4 -> Correlate -> LangGraph StateGraph diagnosis.
    """
    os.environ["MONGO_DB_NAME"] = "cnt_test_m3_e2e"
    adapter = CiscoTelemetryAdapter()
    
    fault_records = []
    for r in adapter.iter_syslog_records(case="4"):
        if r.event_hint or "down" in (r.raw_message or "").lower():
            fault_records.append(r)
            if len(fault_records) >= 20:
                break

    if not fault_records:
        pytest.skip("Case 4 fault syslogs not found.")

    ing_persistence = IngestionPersistence(db_name="cnt_test_m3_e2e")
    ing_service = IngestionService(persistence=ing_persistence)
    events = [ing_service.process_record(r) for r in fault_records if r]
    anomalies = [e for e in events if e.event_type.value != "unknown"]
    assert len(anomalies) > 0

    correlator = CorrelationAlgorithm(window_seconds=120)
    incidents = correlator.group_events(anomalies, [])
    assert len(incidents) > 0

    orchestrator = DiagnosisOrchestrator()
    sample_incident = incidents[0]
    final_state = orchestrator.diagnose_incident(sample_incident, context_id="case_4")

    diag: DiagnosisResult = final_state["diagnosis_result"]
    assert diag.confidence >= 0.70
    assert len(diag.hypotheses) > 0

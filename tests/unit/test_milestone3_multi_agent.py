"""
test_milestone3_multi_agent.py — Unit Tests for Milestone 3 Multi-Agent AI Framework.

Tests:
  - Topology loading from Containerlab & Cisco testbed
  - Graph neighbor resolution, interface mapping, blast radius
  - Symptom extraction, causal sequencing, missing evidence detection
  - RCA hypothesis generation across fault families
  - Evidence attribution and contradiction penalization
  - LangGraph StateGraph execution, conditional routing, and checkpointing
  - MongoDB diagnosis persistence
"""

import os
import pytest
from datetime import datetime, timezone
from pymongo import MongoClient

from services.ai.schemas.contracts import (
    IncidentTimeline,
    StructuredEvent,
    EventType,
    Severity,
    TimeWindow,
    DiagnosisResult,
    TopologyContext,
)
from services.ai.agents.topology.loader import (
    load_containerlab_topology,
    load_cisco_spine_leaf_topology,
    load_topology,
)
from services.ai.agents.topology.graph import TopologyGraph
from services.ai.agents.topology.agent import TopologyAgent
from services.ai.agents.symptom.analyzer import SymptomAnalyzer
from services.ai.agents.symptom.models import SymptomCategory, SymptomPrimacy
from services.ai.agents.symptom.agent import SymptomAgent
from services.ai.agents.rca.hypotheses import RCAHypothesisEngine
from services.ai.agents.rca.agent import RCAgent
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.orchestrator.graph import build_diagnosis_graph
from services.ai.agents.diagnosis.persistence import DiagnosisPersistence


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_timeline():
    t0 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 15, 10, 0, 2, tzinfo=timezone.utc)

    e1 = StructuredEvent(
        event_id="evt_shut_1",
        raw_reference="case4/syslog:10",
        timestamp=t0,
        device_id="spine2",
        interface="HundredGigE0/0/0/8",
        event_type=EventType.PORT_ADMIN_SHUTDOWN,
        severity=Severity.HIGH,
        normalized_fields={"raw_message": "interface HundredGigE0/0/0/8 administratively down"}
    )
    e2 = StructuredEvent(
        event_id="evt_down_1",
        raw_reference="case4/syslog:11",
        timestamp=t1,
        device_id="spine2",
        interface="HundredGigE0/0/0/8",
        event_type=EventType.PORT_DOWN,
        severity=Severity.HIGH,
        normalized_fields={"raw_message": "line protocol changed to down"}
    )

    return IncidentTimeline(
        incident_id="inc_unit_test_01",
        time_window=TimeWindow(start=t0, end=t1),
        events=[e1, e2],
        affected_devices=["spine2"],
        affected_interfaces=["HundredGigE0/0/0/8"],
        suspected_protocols=["interface"]
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. TOPOLOGY MODEL & GRAPH TESTS (Task A & C)
# ─────────────────────────────────────────────────────────────────────────────

class TestTopologyModelAndGraph:
    def test_load_containerlab_topology(self):
        topo = load_containerlab_topology()
        assert topo.topology_id == "containerlab_frr_linear"
        assert len(topo.devices) == 3
        assert "r1" in topo.devices
        assert "r2" in topo.devices
        assert "r3" in topo.devices
        assert len(topo.physical_links) == 2
        assert len(topo.bgp_peers) >= 2
        assert len(topo.ospf_adjacencies) >= 2

    def test_load_cisco_spine_leaf_topology(self):
        topo = load_cisco_spine_leaf_topology()
        assert topo.topology_id == "cisco_spine_leaf_fabric"
        assert len(topo.devices) == 15  # 4 spines + 8 leaves + 3 DCI
        assert "spine1" in topo.devices
        assert "leaf1" in topo.devices
        assert "dr01" in topo.devices
        assert len(topo.physical_links) == 32  # 8 leaves * 4 spines

    def test_graph_neighbor_resolution(self):
        topo = load_containerlab_topology()
        graph = TopologyGraph(topo)
        r2_neighbors = graph.get_directly_connected("r2")
        assert sorted(r2_neighbors) == ["r1", "r3"]

    def test_graph_interface_mapping(self):
        topo = load_containerlab_topology()
        graph = TopologyGraph(topo)
        mapping = graph.get_neighboring_interfaces("r1", "eth1")
        assert mapping is not None
        remote_dev, remote_intf = mapping
        assert remote_dev == "r2"
        assert remote_intf == "eth1"

    def test_blast_radius_calculation(self):
        topo = load_cisco_spine_leaf_topology()
        graph = TopologyGraph(topo)
        blast = graph.estimate_blast_radius(["spine1"])
        assert blast["blast_radius_device_count"] == 9  # spine1 + 8 connected leaves
        assert blast["blast_radius_score"] > 0.5
        assert len(blast["directly_impacted_neighbors"]) == 8

    def test_topology_agent_contextualize(self, sample_timeline):
        agent = TopologyAgent()
        context = agent.contextualize_incident(sample_timeline)
        assert isinstance(context, TopologyContext)
        assert len(context.nodes) > 0
        node_ids = [n.node_id for n in context.nodes]
        assert "spine2" in node_ids


# ─────────────────────────────────────────────────────────────────────────────
# 2. SYMPTOM CONTEXTUALIZATION TESTS (Task B)
# ─────────────────────────────────────────────────────────────────────────────

class TestSymptomAgent:
    def test_symptom_extraction_and_primacy(self, sample_timeline):
        agent = SymptomAgent()
        report = agent.process(sample_timeline)
        assert len(report.symptoms) == 2
        assert report.primary_symptom is not None
        # The admin shutdown at t0 is primary; physical link down at t1 is downstream
        assert report.primary_symptom.category == SymptomCategory.ADMIN_SHUTDOWN
        assert report.primary_symptom.primacy == SymptomPrimacy.PRIMARY
        assert len(report.downstream_symptoms) == 1
        assert report.downstream_symptoms[0].category == SymptomCategory.PHYSICAL_LINK_FAILURE

    def test_chronological_sequencing(self, sample_timeline):
        agent = SymptomAgent()
        report = agent.process(sample_timeline)
        assert report.symptoms[0].sequence_order == 1
        assert report.symptoms[1].sequence_order == 2
        assert len(report.temporal_cascade) == 2

    def test_missing_evidence_detection(self):
        t0 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        e = StructuredEvent(
            event_id="e_bgp",
            raw_reference="case3/syslog:1",
            timestamp=t0,
            device_id="leaf1",
            event_type=EventType.BGP_NEIGHBOR_DOWN,
            severity=Severity.HIGH,
            normalized_fields={"raw_message": "BGP-5-ADJCHANGE: neighbor 10.0.0.1 Down"}
        )
        tl = IncidentTimeline(
            incident_id="inc_bgp_only",
            time_window=TimeWindow(start=t0, end=t0),
            events=[e],
            affected_devices=["leaf1"],
            suspected_protocols=["bgp"]
        )
        agent = SymptomAgent()
        report = agent.process(tl)
        # Should flag that physical link telemetry was absent
        assert any("physical link" in m.lower() for m in report.missing_evidence)


# ─────────────────────────────────────────────────────────────────────────────
# 3. RCA AGENT TESTS (Task D)
# ─────────────────────────────────────────────────────────────────────────────

class TestRCAgent:
    def test_hypothesis_generation_and_confidence(self, sample_timeline):
        symptom_agent = SymptomAgent()
        report = symptom_agent.process(sample_timeline)

        rca_agent = RCAgent()
        diag = rca_agent.diagnose(sample_timeline, report)
        assert isinstance(diag, DiagnosisResult)
        assert diag.confidence >= 0.85
        assert "shutdown" in diag.probable_root_cause.lower()
        assert len(diag.hypotheses) > 0
        assert diag.hypotheses[0].root_cause_category == "port_admin_shutdown"

    def test_contradictory_evidence_handling(self):
        t0 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        # Optics removed, but also port admin shutdown
        e1 = StructuredEvent(
            event_id="e_optics",
            raw_reference="case4:optics",
            timestamp=t0,
            device_id="spine2",
            event_type=EventType.PORT_DOWN,
            severity=Severity.HIGH,
            normalized_fields={"raw_message": "%L2-OPTICS-2-TRANSCEIVER_REMOVED"}
        )
        e2 = StructuredEvent(
            event_id="e_admin",
            raw_reference="case4:admin",
            timestamp=t0,
            device_id="spine2",
            event_type=EventType.PORT_ADMIN_SHUTDOWN,
            severity=Severity.HIGH,
            normalized_fields={"raw_message": "administratively down"}
        )
        tl = IncidentTimeline(
            incident_id="inc_conflict",
            time_window=TimeWindow(start=t0, end=t0),
            events=[e1, e2],
            affected_devices=["spine2"],
            suspected_protocols=["interface"]
        )
        s_agent = SymptomAgent()
        report = s_agent.process(tl)
        rca_agent = RCAgent()
        diag = rca_agent.diagnose(tl, report)

        # Contradictory evidence must be present in hypotheses
        for h in diag.hypotheses:
            if h.hypothesis_id == "hyp_port_admin_shutdown":
                assert len(h.contradictory_evidence) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. LANGGRAPH ORCHESTRATION TESTS (Task E)
# ─────────────────────────────────────────────────────────────────────────────

class TestLangGraphOrchestrator:
    def test_state_graph_compilation(self):
        graph = build_diagnosis_graph()
        assert graph is not None

    def test_full_diagnosis_workflow_execution(self, sample_timeline):
        orchestrator = DiagnosisOrchestrator()
        result_state = orchestrator.diagnose_incident(sample_timeline)

        assert "diagnosis_result" in result_state
        diag: DiagnosisResult = result_state["diagnosis_result"]
        assert diag.confidence > 0.80
        assert "HundredGigE0/0/0/8" in diag.affected_components
        assert "spine2" in diag.affected_components

        # Verify all 9 stages in trace
        trace = result_state["execution_trace"]
        assert any("Stage 1" in s for s in trace)
        assert any("Stage 2" in s for s in trace)
        assert any("Stage 3" in s for s in trace)
        assert any("Stage 4" in s for s in trace)
        assert any("Stage 5" in s for s in trace)
        assert any("Stage 6" in s for s in trace)
        assert any("Stage 7" in s for s in trace)
        assert any("Stage 8" in s for s in trace)
        assert any("Stage 9" in s for s in trace)

    def test_conditional_routing_on_invalid_evidence(self):
        # Empty events triggers abort routing
        t0 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        tl_empty = IncidentTimeline(
            incident_id="inc_empty",
            time_window=TimeWindow(start=t0, end=t0),
            events=[],
            affected_devices=[],
            suspected_protocols=[]
        )
        orchestrator = DiagnosisOrchestrator()
        result_state = orchestrator.diagnose_incident(tl_empty)
        assert result_state["validation_status"] == "empty"
        trace = result_state["execution_trace"]
        assert any("abort" in s.lower() for s in trace)
        diag = result_state["diagnosis_result"]
        assert diag.confidence == 0.0

    def test_checkpointing_state_preservation(self, sample_timeline):
        orchestrator = DiagnosisOrchestrator()
        thread_id = "test_thread_checkpoint_001"
        res1 = orchestrator.diagnose_incident(sample_timeline, thread_id=thread_id)
        # Check that checkpointer saved state
        state_tuple = orchestrator.app.get_state({"configurable": {"thread_id": thread_id}})
        assert state_tuple is not None
        assert state_tuple.values["incident_id"] == sample_timeline.incident_id


# ─────────────────────────────────────────────────────────────────────────────
# 5. MONGO PERSISTENCE TESTS (Task F)
# ─────────────────────────────────────────────────────────────────────────────

class TestDiagnosisPersistence:
    def test_save_and_retrieve_diagnosis(self, sample_timeline):
        persistence = DiagnosisPersistence()
        if not persistence.check_connection():
            pytest.skip("MongoDB unavailable")

        orchestrator = DiagnosisOrchestrator()
        res = orchestrator.diagnose_incident(sample_timeline)
        diag: DiagnosisResult = res["diagnosis_result"]

        # Retrieve doc from mongo
        doc = persistence.get_diagnosis(sample_timeline.incident_id)
        assert doc is not None
        assert doc["incident_id"] == sample_timeline.incident_id
        assert doc["probable_root_cause"] == diag.probable_root_cause
        assert "provenance" in doc


"""
test_milestone5_topology_e2e.py — End-to-End Integration Tests for Milestone 5 Topology Subsystem.

Tests:
  - Multi-agent LangGraph workflow execution with topology reasoning & blast radius injection
  - Cisco 15-node spine-leaf fabric multi-device incident diagnosis
  - Containerlab linear FRR multi-node incident diagnosis
  - Verification of blast_radius_report in IncidentState
"""

import pytest
from datetime import datetime, timezone

from services.ai.schemas.contracts import (
    IncidentTimeline,
    StructuredEvent,
    EventType,
    Severity,
    TimeWindow,
    DiagnosisResult,
)
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.agents.topology import (
    TopologyAgent,
    load_cisco_spine_leaf_topology,
    load_containerlab_topology,
)


@pytest.fixture
def multi_device_cisco_timeline():
    t0 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 15, 10, 0, 2, tzinfo=timezone.utc)

    e1 = StructuredEvent(
        event_id="evt_spine2_down",
        raw_reference="cisco_testbed:1",
        timestamp=t0,
        device_id="spine2",
        interface="HundredGigE0/0/0/8",
        event_type=EventType.PORT_ADMIN_SHUTDOWN,
        severity=Severity.HIGH,
        normalized_fields={"raw_message": "interface HundredGigE0/0/0/8 administratively down"}
    )
    e2 = StructuredEvent(
        event_id="evt_leaf8_bgp",
        raw_reference="cisco_testbed:2",
        timestamp=t1,
        device_id="leaf8",
        interface="HundredGigE0/0/0/2",
        event_type=EventType.BGP_NEIGHBOR_DOWN,
        severity=Severity.HIGH,
        normalized_fields={"bgp_peer": "10.0.0.102", "protocol_hint": "bgp"}
    )

    return IncidentTimeline(
        incident_id="inc_e2e_cisco_clos_01",
        time_window=TimeWindow(start=t0, end=t1),
        events=[e1, e2],
        affected_devices=["spine2", "leaf8"],
        affected_interfaces=["HundredGigE0/0/0/8", "HundredGigE0/0/0/2"],
        suspected_protocols=["interface", "bgp"]
    )


@pytest.fixture
def containerlab_timeline():
    t0 = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    e1 = StructuredEvent(
        event_id="evt_clab_r1",
        raw_reference="clab:1",
        timestamp=t0,
        device_id="r1",
        interface="eth1",
        event_type=EventType.PORT_DOWN,
        severity=Severity.HIGH,
        normalized_fields={"protocol_hint": "interface"}
    )

    return IncidentTimeline(
        incident_id="inc_e2e_clab_01",
        time_window=TimeWindow(start=t0, end=t0),
        events=[e1],
        affected_devices=["r1"],
        affected_interfaces=["eth1"],
        suspected_protocols=["interface"]
    )


class TestMilestone5TopologyE2E:
    def test_full_langgraph_pipeline_with_topology_reasoning(self, multi_device_cisco_timeline):
        orchestrator = DiagnosisOrchestrator()
        result_state = orchestrator.diagnose_incident(multi_device_cisco_timeline)

        # 1. State assertions
        assert "topology_analysis" in result_state
        assert "blast_radius_report" in result_state
        assert "diagnosis_result" in result_state

        topo_analysis = result_state["topology_analysis"]
        assert topo_analysis["topology_id"] == "cisco_spine_leaf_fabric"
        assert topo_analysis["cross_device_valid"] is True
        assert len(topo_analysis["path_redundancy"]) >= 1

        # 2. Blast radius assertions
        blast = result_state["blast_radius_report"]
        assert "spine2" in blast["originating_devices"] or "leaf8" in blast["originating_devices"]
        assert blast["total_nodes_in_topology"] == 15
        assert blast["blast_radius_score"] > 0.0

        # 3. Execution trace assertions
        trace = result_state["execution_trace"]
        assert any("Stage 3 [topology_retrieval]" in step for step in trace)
        assert any("Stage 5 [topology_reasoning]" in step for step in trace)

        # 4. Diagnosis output
        diag: DiagnosisResult = result_state["diagnosis_result"]
        assert diag.confidence > 0.70

    def test_containerlab_topology_reasoning(self, containerlab_timeline):
        agent = TopologyAgent(context_id="containerlab_frr")
        analysis = agent.analyze_topology(containerlab_timeline)

        assert analysis["topology_id"] == "containerlab_frr_linear"
        assert "r1" in analysis["resolved_devices"]
        assert "blast_radius" in analysis
        assert analysis["blast_radius"]["blast_radius_score"] > 0.0


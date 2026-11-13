"""
test_milestone7_telemetry.py — Unit tests for Milestone 7 Telemetry Collector and Evidence Normalizer.
"""

import pytest

from network.containerlab.telemetry.collector import ClabTelemetryCollector
from network.containerlab.telemetry.normalizer import ClabEvidenceNormalizer
from network.containerlab.fault_injection.injector import FaultInjector
from network.containerlab.scenarios.registry import get_scenario
from services.ai.schemas.contracts import EventType, IncidentStatus


@pytest.fixture
def collector():
    return ClabTelemetryCollector(force_mock=True)


@pytest.fixture
def normalizer():
    return ClabEvidenceNormalizer()


@pytest.fixture
def injector():
    return FaultInjector(force_mock=True)


def test_telemetry_collection_structure(collector):
    obs = collector.collect_topology_state()
    assert obs.timestamp is not None
    assert "R1" in obs.bgp_state
    assert "R2" in obs.ospf_state
    assert "R1" in obs.bfd_state
    assert "br-vlan" in obs.bridge_vlans
    assert "client1_to_gw" in obs.ping_results


def test_evidence_normalizer_bgp_down(collector, normalizer, injector):
    sc = get_scenario("CLAB_SCENARIO_1_BGP")
    injector.inject_fault(sc)
    obs = collector.collect_topology_state()
    timeline = normalizer.normalize_observation(obs, sc.scenario_id, "inc_test_bgp")

    assert timeline.incident_id == "inc_test_bgp"
    assert timeline.status == IncidentStatus.OPEN
    assert "R1" in timeline.affected_devices
    assert "bgp" in timeline.suspected_protocols
    assert any(e.event_type == EventType.BGP_NEIGHBOR_DOWN for e in timeline.events)


def test_evidence_normalizer_ospf_adjacency(collector, normalizer, injector):
    sc = get_scenario("CLAB_SCENARIO_2_OSPF")
    injector.inject_fault(sc)
    obs = collector.collect_topology_state()
    timeline = normalizer.normalize_observation(obs, sc.scenario_id, "inc_test_ospf")

    assert timeline.status == IncidentStatus.OPEN
    assert "R2" in timeline.affected_devices
    assert "ospf" in timeline.suspected_protocols
    assert any(e.event_type == EventType.OSPF_ADJACENCY_FAILURE for e in timeline.events)


def test_evidence_normalizer_vlan_mismatch(collector, normalizer, injector):
    sc = get_scenario("CLAB_SCENARIO_3_VLAN")
    injector.inject_fault(sc)
    obs = collector.collect_topology_state()
    timeline = normalizer.normalize_observation(obs, sc.scenario_id, "inc_test_vlan")

    assert timeline.status == IncidentStatus.OPEN
    assert "br-vlan" in timeline.affected_devices
    assert "vlan" in timeline.suspected_protocols
    assert any(e.event_type == EventType.VLAN_FAULT for e in timeline.events)

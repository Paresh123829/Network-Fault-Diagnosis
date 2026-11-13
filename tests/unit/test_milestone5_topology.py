"""
test_milestone5_topology.py — Unit Tests for Milestone 5 Advanced Topology Reasoning & Blast Radius.

Validates:
  - Model integrity & TopologyValidator (structural invariants, dangling refs, duplicates)
  - Multi-layer graph queries (physical multigraph, L2, L3, BGP, OSPF, ECMP, dependency)
  - PathAnalyzer (shortest paths, node-disjoint/edge-disjoint paths, redundancy levels, failure impact)
  - ECMPAnalyzer (resilience, capacity ratios, SPOF detection, observability status)
  - FailureDomainAnalyzer (articulation points, bridges, shared racks/power zones, Clos resilience)
  - TopologyFailureSimulator (non-destructive in-memory simulations of device/link/interface failure)
  - BlastRadiusEngine (quantitative BRR, severity tiers, risk factor breakdown)
  - TopologyAgent & backward compatibility
"""

import pytest
from services.ai.agents.topology import (
    DeviceType,
    InterfaceState,
    InterfaceType,
    NetworkDevice,
    NetworkInterface,
    PhysicalLink,
    BGPPeerRelationship,
    OSPFAdjacency,
    ECMPGroup,
    CrossDeviceDependency,
    TopologyGraphModel,
    TopologyProvenance,
    ValidationState,
    load_cisco_spine_leaf_topology,
    load_containerlab_topology,
    TopologyGraph,
    LAYER_PHYSICAL,
    LAYER_L2,
    LAYER_L3,
    LAYER_BGP,
    LAYER_OSPF,
    LAYER_ECMP,
    LAYER_DEPENDENCY,
    TopologyAgent,
    TopologyValidator,
    ValidationSeverity,
    PathAnalyzer,
    ECMPAnalyzer,
    FailureDomainAnalyzer,
    BlastRadiusEngine,
    TopologyFailureSimulator,
)
from services.ai.schemas.contracts import IncidentTimeline, StructuredEvent, EventType, Severity, TimeWindow
from datetime import datetime, timezone


@pytest.fixture
def cisco_topo():
    return load_cisco_spine_leaf_topology()


@pytest.fixture
def containerlab_topo():
    return load_containerlab_topology()


# ─────────────────────────────────────────────────────────────────────────────
# 1. TopologyValidator Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestTopologyValidator:
    def test_cisco_topology_validation_passes(self, cisco_topo):
        validator = TopologyValidator(cisco_topo)
        report = validator.validate()
        assert report.is_valid is True
        assert report.error_count == 0
        assert report.statistics["device_count"] == 15
        assert report.statistics["physical_link_count"] == 32
        assert report.statistics["ecmp_group_count"] == 8

    def test_containerlab_topology_validation_passes(self, containerlab_topo):
        validator = TopologyValidator(containerlab_topo)
        report = validator.validate()
        assert report.is_valid is True
        assert report.error_count == 0

    def test_detects_dangling_link_reference(self, cisco_topo):
        bad_link = PhysicalLink(
            link_id="bad_link_99",
            source_device="non_existent_dev",
            source_interface="eth1",
            target_device="spine1",
            target_interface="HundredGigE0/0/0/1"
        )
        cisco_topo.physical_links.append(bad_link)
        validator = TopologyValidator(cisco_topo)
        report = validator.validate()
        assert report.is_valid is False
        assert report.error_count >= 1
        dangling_issues = [i for i in report.issues if i.rule == "dangling_device_reference"]
        assert len(dangling_issues) >= 1

    def test_detects_duplicate_device_id(self):
        m = TopologyGraphModel(
            topology_id="dup_test",
            devices={
                "r1": NetworkDevice(device_id="r1", canonical_name="R1"),
                "R1": NetworkDevice(device_id="R1", canonical_name="R1-Dup"),
            }
        )
        validator = TopologyValidator(m)
        report = validator.validate()
        assert report.is_valid is False
        assert any(i.rule == "unique_device_id" for i in report.issues)

    def test_detects_self_loop(self):
        m = TopologyGraphModel(
            topology_id="loop_test",
            devices={"r1": NetworkDevice(device_id="r1", canonical_name="R1")},
            physical_links=[PhysicalLink(
                link_id="loop_link",
                source_device="r1",
                source_interface="eth1",
                target_device="r1",
                target_interface="eth2"
            )]
        )
        validator = TopologyValidator(m)
        report = validator.validate()
        assert any(i.rule == "no_self_loops" for i in report.issues)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multi-Layer Graph Architecture Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestMultiLayerGraph:
    def test_layer_instantiation(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        phys = graph.get_layer(LAYER_PHYSICAL)
        l2 = graph.get_layer(LAYER_L2)
        l3 = graph.get_layer(LAYER_L3)
        bgp = graph.get_layer(LAYER_BGP)
        ecmp = graph.get_layer(LAYER_ECMP)
        dep = graph.get_layer(LAYER_DEPENDENCY)

        assert phys.number_of_nodes() == 15
        assert l3.number_of_nodes() == 15
        assert bgp.number_of_nodes() == 15
        assert ecmp.number_of_nodes() == 15
        assert dep.number_of_nodes() == 15

    def test_parallel_links_preserved_in_multigraph(self):
        m = TopologyGraphModel(
            topology_id="multi_link_test",
            devices={
                "r1": NetworkDevice(device_id="r1", canonical_name="R1"),
                "r2": NetworkDevice(device_id="r2", canonical_name="R2"),
            },
            physical_links=[
                PhysicalLink(link_id="link1", source_device="r1", source_interface="eth1", target_device="r2", target_interface="eth1"),
                PhysicalLink(link_id="link2", source_device="r1", source_interface="eth2", target_device="r2", target_interface="eth2"),
            ]
        )
        graph = TopologyGraph(m)
        phys = graph.get_layer(LAYER_PHYSICAL)
        assert phys.number_of_edges("r1", "r2") == 2
        # Base graph maintains compatibility
        assert graph.g.has_edge("r1", "r2")

    def test_backward_compatible_methods(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        nbrs = graph.get_directly_connected("leaf1")
        assert len(nbrs) == 4
        assert sorted(nbrs) == ["spine1", "spine2", "spine3", "spine4"]

        peers = graph.get_bgp_peers("leaf1")
        assert len(peers) == 4

        blast = graph.estimate_blast_radius(["spine1"])
        assert blast["blast_radius_device_count"] == 9
        assert blast["blast_radius_score"] > 0.5


# ─────────────────────────────────────────────────────────────────────────────
# 3. PathAnalyzer Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestPathAnalyzer:
    def test_shortest_paths_between_leaves(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        analyzer = PathAnalyzer(graph)
        paths = analyzer.find_shortest_paths("leaf1", "leaf2")
        # In 4-spine Clos fabric, shortest path is 2 hops (leaf1 -> spineX -> leaf2) across all 4 spines
        assert len(paths) == 4
        for p in paths:
            assert len(p) == 3
            assert p[0] == "leaf1"
            assert p[2] == "leaf2"
            assert p[1] in ["spine1", "spine2", "spine3", "spine4"]

    def test_node_disjoint_paths(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        analyzer = PathAnalyzer(graph)
        disjoint = analyzer.find_node_disjoint_paths("leaf1", "leaf2")
        assert len(disjoint) == 4  # 4 completely independent paths through 4 spines

    def test_path_redundancy_analysis(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        analyzer = PathAnalyzer(graph)
        rep = analyzer.analyze_path_redundancy("leaf1", "leaf2")
        assert rep.is_reachable is True
        assert rep.shortest_path_hops == 2
        assert rep.node_disjoint_paths_count == 4
        assert rep.redundancy_level == "HIGH"
        assert len(rep.single_points_of_failure) == 0

    def test_in_memory_failure_impact_evaluation(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        analyzer = PathAnalyzer(graph)
        # Simulate loss of spine1 and spine2
        res = analyzer.evaluate_path_failure_impact("leaf1", "leaf2", failed_devices=["spine1", "spine2"])
        assert res["is_reachable"] is True
        assert res["surviving_paths_count"] >= 2  # spine3 and spine4 paths survive
        assert res["post_failure_hops"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. ECMPAnalyzer Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestECMPAnalyzer:
    def test_audit_all_cisco_ecmp_groups(self, cisco_topo):
        analyzer = ECMPAnalyzer(cisco_topo)
        reports = analyzer.analyze_all_ecmp_groups()
        assert len(reports) == 8  # 8 leaves
        for r in reports:
            assert r.health_status == "OPTIMAL"
            assert r.total_next_hops == 4
            assert r.active_next_hops == 4
            assert r.capacity_ratio == 1.0
            assert r.is_spof is False
            assert r.observability_status == "UNKNOWN — INSUFFICIENT TRAFFIC OBSERVABILITY"

    def test_ecmp_single_failure_degradation(self, cisco_topo):
        analyzer = ECMPAnalyzer(cisco_topo)
        sim = analyzer.simulate_ecmp_failure(failed_devices=["spine1"])
        for r in sim:
            assert r.health_status == "DEGRADED"
            assert r.active_next_hops == 3
            assert r.capacity_ratio == 0.75
            assert r.is_spof is False

    def test_ecmp_spof_detection(self, cisco_topo):
        analyzer = ECMPAnalyzer(cisco_topo)
        # Fail 3 out of 4 spines
        sim = analyzer.simulate_ecmp_failure(failed_devices=["spine1", "spine2", "spine3"])
        for r in sim:
            assert r.health_status == "CRITICAL_SPOF"
            assert r.active_next_hops == 1
            assert r.is_spof is True
            assert r.capacity_ratio == 0.25

    def test_ecmp_blackhole_detection(self, cisco_topo):
        analyzer = ECMPAnalyzer(cisco_topo)
        # Fail all 4 spines
        sim = analyzer.simulate_ecmp_failure(failed_devices=["spine1", "spine2", "spine3", "spine4"])
        for r in sim:
            assert r.health_status == "BLACKHOLED"
            assert r.is_blackholed is True
            assert r.capacity_ratio == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. FailureDomainAnalyzer Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestFailureDomainAnalyzer:
    def test_cisco_clos_resilience(self, cisco_topo):
        analyzer = FailureDomainAnalyzer(cisco_topo)
        report = analyzer.analyze()
        assert len(report.spine_tier_devices) == 4
        assert len(report.leaf_tier_devices) == 8
        assert len(report.border_tier_devices) == 3
        # Clos topology has no cut-nodes (articulation points) or bridge links
        assert len(report.articulation_points) == 0
        assert len(report.bridge_links) == 0
        assert report.vulnerability_summary["clos_spine_leaf_resilient"] is True
        assert report.vulnerability_summary["risk_level"] == "LOW"

    def test_linear_topology_articulation_points(self, containerlab_topo):
        analyzer = FailureDomainAnalyzer(containerlab_topo)
        report = analyzer.analyze()
        # In a linear R1-R2-R3 topology, R2 is an articulation point
        assert "r2" in report.articulation_points
        assert report.vulnerability_summary["has_single_point_of_failure_nodes"] is True
        assert report.vulnerability_summary["risk_level"] == "HIGH"


# ─────────────────────────────────────────────────────────────────────────────
# 6. TopologyFailureSimulator Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestTopologyFailureSimulator:
    def test_simulate_device_failure_non_destructive(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        orig_nodes = len(graph.g.nodes())
        orig_edges = len(graph.g.edges())

        sim = TopologyFailureSimulator(cisco_topo, graph)
        res = sim.simulate_device_failure(["spine1"])

        assert res.scenario_type == "device_failure"
        assert res.original_node_count == orig_nodes
        assert res.surviving_node_count == orig_nodes - 1
        assert len(res.affected_bgp_sessions) == 16  # 8 leaves peering bidirectional with spine1
        # Spine-leaf fabric stays connected through spine2, spine3, spine4
        assert res.severed_node_pairs_count == 0

        # Base graph MUST remain unmutated
        assert len(graph.g.nodes()) == orig_nodes
        assert len(graph.g.edges()) == orig_edges

    def test_simulate_link_failure(self, cisco_topo):
        graph = TopologyGraph(cisco_topo)
        sim = TopologyFailureSimulator(cisco_topo, graph)
        res = sim.simulate_link_failure("link_leaf1_spine1")
        assert res.scenario_type == "link_failure"
        assert res.post_failure_components == 4  # 3 isolated DCI + 1 connected Clos fabric


# ─────────────────────────────────────────────────────────────────────────────
# 7. BlastRadiusEngine Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestBlastRadiusEngine:
    def test_spine_failure_blast_radius(self, cisco_topo):
        engine = BlastRadiusEngine(cisco_topo)
        rep = engine.calculate(["spine1"])
        assert rep.originating_devices == ["spine1"]
        assert len(rep.directly_impacted_neighbors) == 8  # all 8 leaves
        assert rep.blast_radius_device_count == 9  # spine1 + 8 leaves
        assert rep.blast_radius_score > 0.5
        assert rep.severity_assessment == "CRITICAL"
        assert len(rep.risk_factors) >= 1
        assert rep.degraded_ecmp_groups_count == 8

        # Verify backward compatibility of to_dict()
        d = rep.to_dict()
        assert "originating_devices" in d
        assert "affected_interfaces" in d
        assert "directly_impacted_neighbors" in d
        assert "bgp_peers_at_risk" in d
        assert "total_nodes_in_topology" in d
        assert "blast_radius_device_count" in d
        assert "blast_radius_score" in d
        assert "severity_assessment" in d

    def test_leaf_failure_blast_radius(self, cisco_topo):
        engine = BlastRadiusEngine(cisco_topo)
        rep = engine.calculate(["leaf1"])
        assert rep.originating_devices == ["leaf1"]
        assert len(rep.directly_impacted_neighbors) == 4  # 4 spines
        assert rep.blast_radius_device_count == 5

    def test_single_uplink_failure_leaf_retains_3_of_4_spines(self, cisco_topo):
        """
        TASK A Verification: A single uplink failure leaves the leaf connected to 3 of 4 spines.
        Exposure ratio > 0, but Unreachability ratio MUST be 0.0.
        Verifies that exposure and unreachability metrics do not incorrectly become identical.
        """
        engine = BlastRadiusEngine(cisco_topo)
        rep = engine.calculate(
            affected_devices=["leaf1"],
            affected_interfaces=["leaf1:HundredGigE0/0/0/1"],
            reference_ingress_devices=["spine2", "spine3", "spine4"]
        )
        # Impact exposure is non-zero (leaf1 and spine1 are exposed)
        assert rep.impact_exposure_ratio > 0.0
        # Network unreachability is exactly 0.0 (all baseline-reachable nodes remain reachable)
        assert rep.network_unreachability_ratio == 0.0
        # Metrics MUST NOT be identical
        assert rep.impact_exposure_ratio != rep.network_unreachability_ratio
        # No nodes are newly unreachable
        assert len(rep.newly_unreachable_devices) == 0
        # Exactly 1 path lost, at least 3 surviving alternate paths through surviving spines
        assert rep.lost_paths_count == 1
        assert rep.surviving_alternate_paths_count >= 3
        assert "leaf1" in rep.failed_topology_reachable_devices

    def test_spine_failure_exposure_vs_unreachability_differentiation(self, cisco_topo):
        """
        TASK A Verification: When spine1 fails, all 8 leaves lose 1 of 4 uplinks (adjacent exposure),
        but 0 leaves lose reachability because all leaves retain 3 surviving spine uplinks.
        """
        engine = BlastRadiusEngine(cisco_topo)
        rep = engine.calculate(["spine1"], reference_ingress_devices=["spine2", "spine3", "spine4"])
        # Exposure is high: spine1 + 8 adjacent leaves = 9 devices exposed
        assert rep.impact_exposure_ratio >= 0.60
        # Unreachability is 0.0: all 8 leaves remain 100% reachable to each other and surviving spines
        assert rep.network_unreachability_ratio == 0.0
        assert rep.impact_exposure_ratio != rep.network_unreachability_ratio
        assert len(rep.newly_unreachable_devices) == 0

    def test_linear_topology_unreachability_on_articulation_failure(self, containerlab_topo):
        """
        TASK A Verification: When an articulation point fails in a linear topology (r2 in r1-r2-r3),
        unreachability ratio MUST be > 0.0 as r3 becomes unreachable from r1.
        """
        engine = BlastRadiusEngine(containerlab_topo)
        rep = engine.calculate(["r2"], reference_ingress_devices=["r1"])
        assert rep.network_unreachability_ratio > 0.0
        assert "r3" in rep.newly_unreachable_devices

    def test_bgp_accounting_reconciliation(self, cisco_topo):
        """
        TASK B Verification: Reconcile 32 unique administrative BGP peer agreements with
        64 directed DiGraph session edges.
        """
        graph = TopologyGraph(cisco_topo)
        assert graph.get_unique_bgp_peer_count() == 32
        assert graph.get_directed_bgp_session_count() == 64

        validator = TopologyValidator(cisco_topo)
        v_rep = validator.validate()
        assert v_rep.statistics["unique_bgp_peer_relationships"] == 32
        assert v_rep.statistics["directed_bgp_session_edges"] == 64
        rec = v_rep.statistics["bgp_accounting_reconciliation"]
        assert rec["unique_peering_relationships"] == 32
        assert rec["directed_session_edges"] == 64


# ─────────────────────────────────────────────────────────────────────────────
# 8. TopologyAgent Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestTopologyAgentEnrichment:
    def test_agent_analyze_topology_comprehensive(self):
        agent = TopologyAgent()
        ev = StructuredEvent(
            event_id="ev_test",
            timestamp=datetime.now(timezone.utc),
            device_id="leaf1",
            interface="HundredGigE0/0/0/1",
            event_type=EventType.PORT_DOWN,
            severity=Severity.HIGH,
            normalized_fields={"protocol_hint": "bgp"},
            raw_reference="test:1"
        )
        timeline = IncidentTimeline(
            incident_id="inc_leaf1",
            time_window=TimeWindow(start=ev.timestamp, end=ev.timestamp),
            events=[ev],
            affected_devices=["leaf1", "leaf2"],
            affected_interfaces=["HundredGigE0/0/0/1"],
            suspected_protocols=["bgp"]
        )

        analysis = agent.analyze_topology(timeline)
        assert analysis["topology_id"] == "cisco_spine_leaf_fabric"
        assert "blast_radius" in analysis
        assert "path_redundancy" in analysis
        assert len(analysis["path_redundancy"]) >= 1
        assert "ecmp_degradations" in analysis
        assert "failure_domain_summary" in analysis

    def test_agent_validate_topology(self):
        agent = TopologyAgent()
        val_rep = agent.validate_topology()
        assert val_rep["is_valid"] is True
        assert val_rep["error_count"] == 0

"""
blast_radius.py — Quantitative Blast Radius and Failure Impact Engine.

Calculates multi-dimensional blast radius for network fault incidents:
  - Impact Exposure Ratio (IER): Unique directly and indirectly exposed devices / total eligible devices
  - Network Unreachability Ratio (NUR): Newly unreachable baseline-reachable devices / baseline-reachable devices
  - Disaggregated impact categories: Direct, Adjacent Exposure, Multi-hop Impact, Newly Unreachable
  - Path tracking: Lost paths vs Surviving alternate paths
  - Baseline vs Failed-topology reachability comparisons from explicit reference vantage points
  - Protocol peering impact (BGP sessions, OSPF adjacencies)
  - Degraded ECMP forwarding paths and SPOF triggering
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
from pydantic import BaseModel, Field

from .model import TopologyGraphModel
from .graph import TopologyGraph
from .ecmp_analyzer import ECMPAnalyzer
from .failure_simulator import TopologyFailureSimulator


class BlastRadiusReport(BaseModel):
    # Backward-compatible fields
    originating_devices: List[str]
    affected_interfaces: List[str] = Field(default_factory=list)
    directly_impacted_neighbors: List[str] = Field(default_factory=list)
    bgp_peers_at_risk: List[str] = Field(default_factory=list)
    total_nodes_in_topology: int
    blast_radius_device_count: int
    blast_radius_score: float
    severity_assessment: str  # LOW, MEDIUM, HIGH, CRITICAL

    # Separate Exposure & Unreachability Metrics (Milestone 5.1)
    impact_exposure_ratio: float = 0.0
    network_unreachability_ratio: float = 0.0

    # Disaggregated Impact Categories
    direct_impact_devices: List[str] = Field(default_factory=list)
    adjacent_exposure_devices: List[str] = Field(default_factory=list)
    multihop_impact_devices: List[str] = Field(default_factory=list)
    newly_unreachable_devices: List[str] = Field(default_factory=list)

    # Reachability & Path Tracking
    baseline_reachable_devices: List[str] = Field(default_factory=list)
    failed_topology_reachable_devices: List[str] = Field(default_factory=list)
    lost_paths_count: int = 0
    surviving_alternate_paths_count: int = 0

    # Quantitative Milestone 5 Fields
    indirectly_impacted_devices: List[str] = Field(default_factory=list)
    newly_isolated_devices: List[str] = Field(default_factory=list)
    degraded_ecmp_groups_count: int = 0
    spofs_triggered: List[str] = Field(default_factory=list)
    blast_radius_ratio: float = 0.0  # Legacy alias to impact_exposure_ratio
    risk_factors: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class BlastRadiusEngine:
    """
    Quantitative blast radius calculation engine distinguishing Exposure from Unreachability.
    """

    def __init__(self, model: TopologyGraphModel, graph: Optional[TopologyGraph] = None):
        self.model = model
        self.graph = graph or TopologyGraph(model)
        self.ecmp_analyzer = ECMPAnalyzer(model, self.graph)
        self.simulator = TopologyFailureSimulator(model, self.graph)

    def calculate(
        self,
        affected_devices: List[str],
        affected_interfaces: Optional[List[str]] = None,
        reference_ingress_devices: Optional[List[str]] = None
    ) -> BlastRadiusReport:
        """
        Computes exhaustive blast radius report for a set of affected devices and interfaces.
        Strictly differentiates Impact Exposure (IER) from Network Unreachability (NUR).
        """
        clean_devs = sorted(list(set(d.lower() for d in affected_devices if self.graph.g.has_node(d.lower()))))
        intfs = affected_interfaces or []
        base_g = self.graph.g
        sim_g = base_g.copy()

        # 1. Direct Impact
        direct_devs = list(clean_devs)

        # 2. Adjacent Exposure & Link Cuts
        adjacent_exposure: Set[str] = set()
        bgp_peers_impacted: Set[str] = set()
        affected_link_endpoints: List[Tuple[str, str]] = []

        if intfs:
            # Interface-level failure: device is up, but specific link(s) are cut
            for intf_spec in intfs:
                if ":" in intf_spec:
                    dev, intf_name = intf_spec.split(":", 1)
                else:
                    dev = clean_devs[0] if clean_devs else ""
                    intf_name = intf_spec
                if dev:
                    mapping = self.graph.get_neighboring_interfaces(dev, intf_name)
                    if mapping:
                        remote_dev, _ = mapping
                        affected_link_endpoints.append((dev.lower(), remote_dev.lower()))
                        adjacent_exposure.add(remote_dev.lower())
                        if sim_g.has_edge(dev.lower(), remote_dev.lower()):
                            sim_g.remove_edge(dev.lower(), remote_dev.lower())
                        # Protocol peers across this specific link
                        for p in self.graph.get_bgp_peers(dev):
                            if p.remote_device.lower() == remote_dev.lower():
                                bgp_peers_impacted.add(p.remote_device)
        else:
            # Full device-level failure: remove node from simulated topology
            for d in clean_devs:
                for nbr in base_g.neighbors(d):
                    if nbr not in clean_devs:
                        adjacent_exposure.add(nbr)
                for peer in self.graph.get_bgp_peers(d):
                    rem = peer.remote_device.lower()
                    if rem not in clean_devs:
                        bgp_peers_impacted.add(peer.remote_device)
                if sim_g.has_node(d):
                    sim_g.remove_node(d)

        # 3. Multi-Hop Impact (2-hop fault propagation paths)
        multihop_impact: Set[str] = set()
        for d in clean_devs:
            paths = self.graph.get_fault_propagation_paths(d, max_depth=2)
            for p in paths:
                if len(p) > 2:
                    end_node = p[-1]
                    if end_node not in clean_devs and end_node not in adjacent_exposure:
                        multihop_impact.add(end_node)

        # 4. Ingress / Reference Device Resolution
        # If device failed completely, surviving nodes exclude clean_devs; if interface failed, clean_devs survive
        if intfs:
            surviving_nodes = sorted(list(sim_g.nodes()))
        else:
            surviving_nodes = sorted([n for n in base_g.nodes() if n not in clean_devs])

        # Define reference vantage points (spines if available, or first non-failed leaf)
        if reference_ingress_devices:
            ref_vantage = [r.lower() for r in reference_ingress_devices if r.lower() in surviving_nodes]
        else:
            spines_surviving = [n for n in surviving_nodes if "spine" in n]
            if spines_surviving:
                ref_vantage = spines_surviving
            else:
                leaves_surviving = [n for n in surviving_nodes if "leaf" in n]
                ref_vantage = leaves_surviving[:2] if leaves_surviving else surviving_nodes[:1]

        # 5. Baseline vs Failed Topology Reachability Analysis
        # Exclude devices already unreachable before the failure (isolated nodes)
        baseline_reachable: List[str] = []
        failed_reachable: List[str] = []
        newly_unreachable: List[str] = []

        for node in surviving_nodes:
            is_base_reachable = False
            for ref in ref_vantage:
                if node == ref or (base_g.has_node(ref) and base_g.has_node(node) and nx.has_path(base_g, ref, node)):
                    is_base_reachable = True
                    break
            if is_base_reachable:
                baseline_reachable.append(node)

                # Check post-failure reachability
                is_failed_reachable = False
                for ref in ref_vantage:
                    if node == ref or (sim_g.has_node(ref) and sim_g.has_node(node) and nx.has_path(sim_g, ref, node)):
                        is_failed_reachable = True
                        break
                if is_failed_reachable:
                    failed_reachable.append(node)
                else:
                    newly_unreachable.append(node)

        # 6. Path Tracking: Lost Shortest Paths vs Surviving Alternate Paths
        lost_paths = 0
        surviving_paths = 0

        # Determine reference source & target for path tracking
        if intfs and clean_devs:
            s_node = clean_devs[0]
            # Pick a target leaf that is not s_node
            t_candidates = [n for n in surviving_nodes if "leaf" in n and n != s_node]
            t_node = t_candidates[0] if t_candidates else (surviving_nodes[-1] if surviving_nodes else "")
        else:
            leaves_surviving = [n for n in surviving_nodes if "leaf" in n]
            if len(leaves_surviving) >= 2:
                s_node, t_node = leaves_surviving[0], leaves_surviving[1]
            else:
                s_node = surviving_nodes[0] if surviving_nodes else ""
                t_node = surviving_nodes[-1] if len(surviving_nodes) > 1 else ""

        if s_node and t_node and base_g.has_node(s_node) and base_g.has_node(t_node):
            try:
                base_shortest_count = len(list(nx.all_shortest_paths(base_g, s_node, t_node)))
            except Exception:
                base_shortest_count = 0

            try:
                if sim_g.has_node(s_node) and sim_g.has_node(t_node) and nx.has_path(sim_g, s_node, t_node):
                    surviving_paths = len(list(nx.all_shortest_paths(sim_g, s_node, t_node)))
                else:
                    surviving_paths = 0
            except Exception:
                surviving_paths = 0

            lost_paths = max(0, base_shortest_count - surviving_paths)

        # 7. Disaggregated Metric Ratios
        total_eligible = max(1, len(base_g.nodes()))
        unique_exposed = set(direct_devs) | set(adjacent_exposure) | set(multihop_impact)
        impact_exposure_ratio = round(len(unique_exposed) / total_eligible, 3)

        base_reachable_count = max(1, len(baseline_reachable))
        network_unreachability_ratio = round(len(newly_unreachable) / base_reachable_count, 3)

        # Legacy backward-compatible score
        impacted_nodes_count = len(clean_devs) + len(adjacent_exposure)
        blast_score = round(min(1.0, impacted_nodes_count / total_eligible), 3)

        # 8. ECMP Degradation and SPOF Analysis
        ecmp_sim = self.ecmp_analyzer.simulate_ecmp_failure(clean_devs, intfs)
        degraded_ecmp = [g for g in ecmp_sim if g.health_status in ("DEGRADED", "CRITICAL_SPOF", "BLACKHOLED")]
        spofs_triggered = [g.group_id for g in ecmp_sim if g.is_spof]

        # 9. Risk Factors and Severity Classification
        risk_factors: List[str] = []
        if impact_exposure_ratio > 0.5:
            risk_factors.append(f"Major topology exposure ({impact_exposure_ratio * 100:.1f}% devices exposed to fault domain)")
        if network_unreachability_ratio > 0.0:
            risk_factors.append(f"Network partition active: {len(newly_unreachable)} baseline devices newly unreachable ({network_unreachability_ratio * 100:.1f}%)")
        if len(spofs_triggered) > 0:
            risk_factors.append(f"{len(spofs_triggered)} ECMP groups degraded to Single-Point-of-Failure (SPOF)")
        if any("spine" in d for d in clean_devs) and not intfs:
            risk_factors.append("Spine tier degradation: fabric-wide cross-pod throughput reduced")

        # Severity
        if network_unreachability_ratio > 0.25 or blast_score > 0.50 or len(spofs_triggered) > 2:
            severity = "CRITICAL"
        elif network_unreachability_ratio > 0.0 or blast_score > 0.25 or len(spofs_triggered) > 0 or len(degraded_ecmp) > 0:
            severity = "HIGH"
        else:
            severity = "MEDIUM"

        return BlastRadiusReport(
            originating_devices=clean_devs,
            affected_interfaces=intfs,
            directly_impacted_neighbors=sorted(list(adjacent_exposure)),
            bgp_peers_at_risk=sorted(list(bgp_peers_impacted)),
            total_nodes_in_topology=total_eligible,
            blast_radius_device_count=impacted_nodes_count,
            blast_radius_score=blast_score,
            severity_assessment=severity,
            impact_exposure_ratio=impact_exposure_ratio,
            network_unreachability_ratio=network_unreachability_ratio,
            direct_impact_devices=sorted(list(set(direct_devs))),
            adjacent_exposure_devices=sorted(list(adjacent_exposure)),
            multihop_impact_devices=sorted(list(multihop_impact)),
            newly_unreachable_devices=sorted(list(newly_unreachable)),
            baseline_reachable_devices=sorted(list(baseline_reachable)),
            failed_topology_reachable_devices=sorted(list(failed_reachable)),
            lost_paths_count=lost_paths,
            surviving_alternate_paths_count=surviving_paths,
            indirectly_impacted_devices=sorted(list(multihop_impact)),
            newly_isolated_devices=sorted(list(newly_unreachable)),
            degraded_ecmp_groups_count=len(degraded_ecmp),
            spofs_triggered=spofs_triggered,
            blast_radius_ratio=impact_exposure_ratio,
            risk_factors=risk_factors,
            details={
                "baseline_reachable_count": len(baseline_reachable),
                "failed_reachable_count": len(failed_reachable),
                "reference_vantage": ref_vantage,
            }
        )

"""
failure_domain.py — Failure Domain and Structural Vulnerability Analyzer.

Identifies shared physical and logical failure domains:
  - Racks, fabrics, datacenters, power zones, and SRLGs
  - Graph articulation points (cut-vertices) whose loss partitions the network
  - True physical bridges (cut-edges), correctly accounting for parallel multi-links
  - Spine-Leaf Clos tier redundancy and single points of failure (SPOF)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
from pydantic import BaseModel, Field

from .model import TopologyGraphModel, DeviceType
from .graph import TopologyGraph, LAYER_PHYSICAL


class FailureDomainCluster(BaseModel):
    domain_type: str  # rack, power_zone, fabric, srlg
    domain_id: str
    member_devices: List[str] = Field(default_factory=list)
    member_interfaces: List[str] = Field(default_factory=list)


class FailureDomainAnalysisReport(BaseModel):
    topology_id: str
    articulation_points: List[str] = Field(default_factory=list, description="Critical devices whose failure partitions network")
    bridge_links: List[Dict[str, str]] = Field(default_factory=list, description="Critical physical links whose failure partitions network")
    shared_racks: Dict[str, List[str]] = Field(default_factory=dict)
    shared_power_zones: Dict[str, List[str]] = Field(default_factory=dict)
    shared_fabrics: Dict[str, List[str]] = Field(default_factory=dict)
    spine_tier_devices: List[str] = Field(default_factory=list)
    leaf_tier_devices: List[str] = Field(default_factory=list)
    border_tier_devices: List[str] = Field(default_factory=list)
    isolated_devices: List[str] = Field(default_factory=list)
    vulnerability_summary: Dict[str, Any] = Field(default_factory=dict)


class FailureDomainAnalyzer:
    """
    Evaluates failure domains and graph structural vulnerabilities.
    """

    def __init__(self, model: TopologyGraphModel, graph: Optional[TopologyGraph] = None):
        self.model = model
        self.graph = graph or TopologyGraph(model)

    def analyze(self) -> FailureDomainAnalysisReport:
        """Runs full structural and failure domain audit."""
        # 1. Structural Cut-Vertices (Articulation Points)
        simple_g = self.graph.g
        articulation_points: List[str] = []
        if len(simple_g.nodes()) > 2 and nx.is_connected(simple_g):
            articulation_points = sorted(list(nx.articulation_points(simple_g)))
        elif len(simple_g.nodes()) > 2:
            # For partitioned graphs, compute articulation points per component
            for c in nx.connected_components(simple_g):
                sub = simple_g.subgraph(c)
                if len(sub) > 2:
                    articulation_points.extend(list(nx.articulation_points(sub)))
            articulation_points = sorted(list(set(articulation_points)))

        # 2. Structural Cut-Edges (Bridges)
        # Note: Must ensure edge has no parallel physical links in physical_multigraph!
        bridge_links: List[Dict[str, str]] = []
        raw_bridges: List[Tuple[str, str]] = []

        if len(simple_g.nodes()) > 1 and nx.is_connected(simple_g):
            raw_bridges = list(nx.bridges(simple_g))
        elif len(simple_g.nodes()) > 1:
            for c in nx.connected_components(simple_g):
                sub = simple_g.subgraph(c)
                if len(sub) > 1:
                    raw_bridges.extend(list(nx.bridges(sub)))

        for u, v in raw_bridges:
            # Check parallel multi-links in physical_multigraph
            edge_count = self.graph.physical_multigraph.number_of_edges(u, v)
            if edge_count <= 1:
                # True bridge: single physical link with no parallel backup
                bridge_links.append({"source": u, "target": v})

        # 3. Categorize Shared Domains
        racks: Dict[str, List[str]] = {}
        power_zones: Dict[str, List[str]] = {}
        fabrics: Dict[str, List[str]] = {}
        spines: List[str] = []
        leaves: List[str] = []
        borders: List[str] = []
        isolated: List[str] = []

        for dev_id, dev in self.model.devices.items():
            d_id = dev_id.lower()

            if dev.rack_id:
                racks.setdefault(dev.rack_id, []).append(d_id)
            if dev.power_zone:
                power_zones.setdefault(dev.power_zone, []).append(d_id)
            if dev.fabric_id:
                fabrics.setdefault(dev.fabric_id, []).append(d_id)

            # Tiers
            if dev.device_type == DeviceType.SPINE:
                spines.append(d_id)
            elif dev.device_type == DeviceType.LEAF:
                leaves.append(d_id)
            elif dev.device_type in (DeviceType.DCI, DeviceType.BORDER_ROUTER) or dev.is_border:
                borders.append(d_id)

            if len(self.graph.get_directly_connected(d_id)) == 0:
                isolated.append(d_id)

        # 4. Vulnerability Assessment
        has_critical_ap = len(articulation_points) > 0
        has_critical_bridges = len(bridge_links) > 0

        vulnerability = {
            "has_single_point_of_failure_nodes": has_critical_ap,
            "articulation_point_count": len(articulation_points),
            "bridge_link_count": len(bridge_links),
            "clos_spine_leaf_resilient": (len(spines) >= 2 and len(articulation_points) == 0 and len(bridge_links) == 0),
            "risk_level": "HIGH" if has_critical_ap else ("MEDIUM" if has_critical_bridges else "LOW")
        }

        return FailureDomainAnalysisReport(
            topology_id=self.model.topology_id,
            articulation_points=articulation_points,
            bridge_links=bridge_links,
            shared_racks={k: sorted(v) for k, v in racks.items()},
            shared_power_zones={k: sorted(v) for k, v in power_zones.items()},
            shared_fabrics={k: sorted(v) for k, v in fabrics.items()},
            spine_tier_devices=sorted(spines),
            leaf_tier_devices=sorted(leaves),
            border_tier_devices=sorted(borders),
            isolated_devices=sorted(isolated),
            vulnerability_summary=vulnerability
        )


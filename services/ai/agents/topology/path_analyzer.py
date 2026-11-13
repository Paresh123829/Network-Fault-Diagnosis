"""
path_analyzer.py — Deterministic Path Diversity and Redundancy Analyzer.

Analyzes topological routing diversity, path redundancy, node-disjoint and edge-disjoint paths,
and evaluates failure-induced path stretch and reachability disruption.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import networkx as nx
from pydantic import BaseModel, Field

from .graph import TopologyGraph, LAYER_PHYSICAL, LAYER_L3


class PathRedundancyReport(BaseModel):
    source: str
    target: str
    is_reachable: bool
    shortest_path_hops: int
    shortest_path: List[str] = Field(default_factory=list)
    total_simple_paths_count: int
    node_disjoint_paths_count: int
    node_disjoint_paths: List[List[str]] = Field(default_factory=list)
    edge_disjoint_paths_count: int
    redundancy_level: str  # NONE, SINGLE_PATH, MODERATE, HIGH
    single_points_of_failure: List[str] = Field(default_factory=list, description="Intermediate nodes present on all paths")
    shared_transit_nodes: List[str] = Field(default_factory=list)
    path_stretch_on_primary_failure: Optional[int] = None


class PathAnalyzer:
    """
    Path routing and redundancy analyzer backed by TopologyGraph.
    """

    def __init__(self, graph: TopologyGraph):
        self.graph = graph

    def find_shortest_paths(self, source: str, target: str, layer: str = LAYER_PHYSICAL) -> List[List[str]]:
        """Finds all shortest paths between source and target on specified layer."""
        s, t = source.lower(), target.lower()
        g = self.graph.get_layer(layer)
        if not g.has_node(s) or not g.has_node(t):
            return []
        try:
            return list(nx.all_shortest_paths(g, s, t))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def find_all_paths(self, source: str, target: str, cutoff: int = 4, layer: str = LAYER_PHYSICAL) -> List[List[str]]:
        """Finds all simple paths between source and target up to cutoff hops."""
        s, t = source.lower(), target.lower()
        # Use simple graph for path searches to avoid exponential multigraph explosion
        g = self.graph.g
        if not g.has_node(s) or not g.has_node(t):
            return []
        try:
            return list(nx.all_simple_paths(g, s, t, cutoff=cutoff))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def find_node_disjoint_paths(self, source: str, target: str) -> List[List[str]]:
        """Finds maximum set of internally node-disjoint paths between source and target."""
        s, t = source.lower(), target.lower()
        g = self.graph.g
        if not g.has_node(s) or not g.has_node(t):
            return []
        try:
            return list(nx.node_disjoint_paths(g, s, t))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def find_edge_disjoint_paths(self, source: str, target: str) -> List[List[str]]:
        """Finds maximum set of edge-disjoint paths between source and target."""
        s, t = source.lower(), target.lower()
        g = self.graph.g
        if not g.has_node(s) or not g.has_node(t):
            return []
        try:
            return list(nx.edge_disjoint_paths(g, s, t))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def analyze_path_redundancy(self, source: str, target: str, cutoff: int = 4) -> PathRedundancyReport:
        """
        Computes exhaustive path redundancy and diversity metrics between two endpoints.
        """
        s, t = source.lower(), target.lower()
        g = self.graph.g

        if not g.has_node(s) or not g.has_node(t) or not nx.has_path(g, s, t):
            return PathRedundancyReport(
                source=s,
                target=t,
                is_reachable=False,
                shortest_path_hops=0,
                shortest_path=[],
                total_simple_paths_count=0,
                node_disjoint_paths_count=0,
                node_disjoint_paths=[],
                edge_disjoint_paths_count=0,
                redundancy_level="NONE",
                single_points_of_failure=[],
                shared_transit_nodes=[],
                path_stretch_on_primary_failure=None
            )

        shortest = nx.shortest_path(g, s, t)
        shortest_hops = len(shortest) - 1

        all_paths = list(nx.all_simple_paths(g, s, t, cutoff=cutoff))
        try:
            node_disjoint = list(nx.node_disjoint_paths(g, s, t))
        except Exception:
            node_disjoint = [shortest]

        try:
            edge_disjoint = list(nx.edge_disjoint_paths(g, s, t))
        except Exception:
            edge_disjoint = [shortest]

        # Identify intermediate nodes
        intermediate_nodes_per_path = [set(p[1:-1]) for p in all_paths if len(p) > 2]
        spofs: List[str] = []
        shared_transit: Set[str] = set()

        if intermediate_nodes_per_path:
            common = set.intersection(*intermediate_nodes_per_path)
            spofs = sorted(list(common))
            for p_nodes in intermediate_nodes_per_path:
                shared_transit.update(p_nodes)

        # Redundancy classification
        nd_count = len(node_disjoint)
        if nd_count >= 4:
            redundancy = "HIGH"
        elif nd_count >= 2:
            redundancy = "MODERATE"
        elif nd_count == 1:
            redundancy = "SINGLE_PATH"
        else:
            redundancy = "NONE"

        # Path stretch on primary path intermediate node failure
        path_stretch = None
        if len(shortest) > 2 and len(all_paths) > 1:
            test_sub = g.copy()
            # remove first intermediate hop of primary path
            failed_node = shortest[1]
            test_sub.remove_node(failed_node)
            if nx.has_path(test_sub, s, t):
                new_len = nx.shortest_path_length(test_sub, s, t)
                path_stretch = new_len - shortest_hops

        return PathRedundancyReport(
            source=s,
            target=t,
            is_reachable=True,
            shortest_path_hops=shortest_hops,
            shortest_path=shortest,
            total_simple_paths_count=len(all_paths),
            node_disjoint_paths_count=nd_count,
            node_disjoint_paths=node_disjoint,
            edge_disjoint_paths_count=len(edge_disjoint),
            redundancy_level=redundancy,
            single_points_of_failure=spofs,
            shared_transit_nodes=sorted(list(shared_transit)),
            path_stretch_on_primary_failure=path_stretch
        )

    def evaluate_path_failure_impact(
        self,
        source: str,
        target: str,
        failed_devices: List[str],
        failed_links: Optional[List[Tuple[str, str]]] = None,
        cutoff: int = 4
    ) -> Dict[str, Any]:
        """
        Simulates in-memory failure of specified devices and links without mutating base graph.
        Evaluates surviving paths, path stretch, and reachability.
        """
        s, t = source.lower(), target.lower()
        sim_g = self.graph.g.copy()

        for d in failed_devices:
            d_clean = d.lower()
            if sim_g.has_node(d_clean):
                sim_g.remove_node(d_clean)

        if failed_links:
            for u, v in failed_links:
                u_c, v_c = u.lower(), v.lower()
                if sim_g.has_edge(u_c, v_c):
                    sim_g.remove_edge(u_c, v_c)

        if not sim_g.has_node(s) or not sim_g.has_node(t):
            return {
                "source": s,
                "target": t,
                "is_reachable": False,
                "reason": "Source or target device failed",
                "surviving_paths_count": 0,
                "path_stretch": None
            }

        if not nx.has_path(sim_g, s, t):
            return {
                "source": s,
                "target": t,
                "is_reachable": False,
                "reason": "All paths severed",
                "surviving_paths_count": 0,
                "path_stretch": None
            }

        surviving_paths = list(nx.all_simple_paths(sim_g, s, t, cutoff=cutoff))
        orig_shortest_len = nx.shortest_path_length(self.graph.g, s, t)
        new_shortest_len = nx.shortest_path_length(sim_g, s, t)

        return {
            "source": s,
            "target": t,
            "is_reachable": True,
            "original_hops": orig_shortest_len,
            "post_failure_hops": new_shortest_len,
            "path_stretch": new_shortest_len - orig_shortest_len,
            "surviving_paths_count": len(surviving_paths),
            "surviving_shortest_path": nx.shortest_path(sim_g, s, t)
        }


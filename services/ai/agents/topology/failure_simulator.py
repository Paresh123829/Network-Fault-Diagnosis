"""
failure_simulator.py — In-Memory Network Failure Simulator.

Injects isolated, hypothetical failure scenarios (device failure, link cut, interface flap,
protocol session drop) and evaluates post-failure structural impact without mutating
production or base topology state.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple, Union
import networkx as nx
from pydantic import BaseModel, Field

from .model import TopologyGraphModel
from .graph import TopologyGraph


class SimulationResult(BaseModel):
    scenario_id: str
    scenario_type: str  # device_failure, link_failure, interface_failure, bgp_session_failure
    injected_entities: List[str] = Field(default_factory=list)
    original_node_count: int
    surviving_node_count: int
    original_components: int
    post_failure_components: int
    newly_isolated_devices: List[str] = Field(default_factory=list)
    severed_node_pairs_count: int
    affected_bgp_sessions: List[Dict[str, str]] = Field(default_factory=list)
    affected_ospf_adjacencies: List[Dict[str, str]] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class TopologyFailureSimulator:
    """
    Simulates topological failures non-destructively in-memory.
    """

    def __init__(self, model: TopologyGraphModel, graph: Optional[TopologyGraph] = None):
        self.model = model
        self.graph = graph or TopologyGraph(model)

    def simulate_device_failure(self, device_ids: Union[str, List[str]]) -> SimulationResult:
        """Simulates simultaneous complete failure of one or more devices."""
        devs = [device_ids.lower()] if isinstance(device_ids, str) else [d.lower() for d in device_ids]
        base_g = self.graph.g
        sim_g = base_g.copy()

        orig_nodes = len(base_g.nodes())
        orig_comp = nx.number_connected_components(base_g) if orig_nodes > 0 else 0

        # Remove failed devices
        for d in devs:
            if sim_g.has_node(d):
                sim_g.remove_node(d)

        surviving_nodes = len(sim_g.nodes())
        post_comp = nx.number_connected_components(sim_g) if surviving_nodes > 0 else 0

        # Newly isolated devices (degree 0 in surviving graph)
        newly_isolated: List[str] = []
        for n in sim_g.nodes():
            if sim_g.degree(n) == 0 and base_g.degree(n) > 0:
                newly_isolated.append(n)

        # Severed pairs between surviving nodes
        severed_pairs = 0
        surviving_node_list = list(sim_g.nodes())
        for i in range(len(surviving_node_list)):
            for j in range(i + 1, len(surviving_node_list)):
                u, v = surviving_node_list[i], surviving_node_list[j]
                had_path = nx.has_path(base_g, u, v)
                has_path = nx.has_path(sim_g, u, v)
                if had_path and not has_path:
                    severed_pairs += 1

        # Impacted BGP sessions
        affected_bgp: List[Dict[str, str]] = []
        for peer in self.model.bgp_peers:
            if peer.local_device.lower() in devs or peer.remote_device.lower() in devs:
                affected_bgp.append({
                    "local": peer.local_device,
                    "remote": peer.remote_device,
                    "type": peer.peer_type
                })

        # Impacted OSPF adjacencies
        affected_ospf: List[Dict[str, str]] = []
        for ospf in self.model.ospf_adjacencies:
            if ospf.local_device.lower() in devs or ospf.remote_device.lower() in devs:
                affected_ospf.append({
                    "local": ospf.local_device,
                    "remote": ospf.remote_device,
                    "area": ospf.area
                })

        return SimulationResult(
            scenario_id=f"device_failure_{'_'.join(devs)}",
            scenario_type="device_failure",
            injected_entities=devs,
            original_node_count=orig_nodes,
            surviving_node_count=surviving_nodes,
            original_components=orig_comp,
            post_failure_components=post_comp,
            newly_isolated_devices=sorted(newly_isolated),
            severed_node_pairs_count=severed_pairs,
            affected_bgp_sessions=affected_bgp,
            affected_ospf_adjacencies=affected_ospf,
            details={"failed_devices": devs}
        )

    def simulate_link_failure(self, link_id_or_endpoints: Union[str, Tuple[str, str]]) -> SimulationResult:
        """Simulates physical link cut."""
        base_g = self.graph.g
        sim_g = base_g.copy()

        src: Optional[str] = None
        tgt: Optional[str] = None

        if isinstance(link_id_or_endpoints, tuple):
            src, tgt = link_id_or_endpoints[0].lower(), link_id_or_endpoints[1].lower()
        else:
            # Look up link ID in model
            for l in self.model.physical_links:
                if l.link_id.lower() == link_id_or_endpoints.lower():
                    src, tgt = l.source_device.lower(), l.target_device.lower()
                    break

        if src and tgt and sim_g.has_edge(src, tgt):
            sim_g.remove_edge(src, tgt)

        orig_nodes = len(base_g.nodes())
        orig_comp = nx.number_connected_components(base_g)
        post_comp = nx.number_connected_components(sim_g)

        newly_isolated: List[str] = []
        for n in [src, tgt]:
            if n and sim_g.has_node(n) and sim_g.degree(n) == 0:
                newly_isolated.append(n)

        # Severed pairs
        severed_pairs = 0
        node_list = list(sim_g.nodes())
        for i in range(len(node_list)):
            for j in range(i + 1, len(node_list)):
                u, v = node_list[i], node_list[j]
                if nx.has_path(base_g, u, v) and not nx.has_path(sim_g, u, v):
                    severed_pairs += 1

        return SimulationResult(
            scenario_id=f"link_failure_{src}_{tgt}",
            scenario_type="link_failure",
            injected_entities=[str(link_id_or_endpoints)],
            original_node_count=orig_nodes,
            surviving_node_count=orig_nodes,
            original_components=orig_comp,
            post_failure_components=post_comp,
            newly_isolated_devices=sorted(newly_isolated),
            severed_node_pairs_count=severed_pairs,
            affected_bgp_sessions=[],
            affected_ospf_adjacencies=[],
            details={"endpoints": [src, tgt]}
        )

    def simulate_interface_failure(self, device_id: str, interface_name: str) -> SimulationResult:
        """Simulates administrative down or transceiver failure of an interface."""
        mapping = self.graph.get_neighboring_interfaces(device_id, interface_name)
        if mapping:
            remote_dev, _ = mapping
            return self.simulate_link_failure((device_id, remote_dev))

        return SimulationResult(
            scenario_id=f"interface_failure_{device_id}_{interface_name}",
            scenario_type="interface_failure",
            injected_entities=[f"{device_id}:{interface_name}"],
            original_node_count=len(self.graph.g.nodes()),
            surviving_node_count=len(self.graph.g.nodes()),
            original_components=nx.number_connected_components(self.graph.g),
            post_failure_components=nx.number_connected_components(self.graph.g),
            newly_isolated_devices=[],
            severed_node_pairs_count=0,
            details={"note": "Interface had no active remote neighbor link"}
        )


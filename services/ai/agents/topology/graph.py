"""
graph.py — Multi-Layer Network Topology Graph Engine using NetworkX.

Maintains multi-layer graph views:
  - LAYER_PHYSICAL: MultiGraph preserving parallel links between device pairs
  - LAYER_L2: Layer-2 switching and VLAN domains
  - LAYER_L3: Layer-3 routed IP connectivity
  - LAYER_BGP: DiGraph of BGP peering sessions
  - LAYER_OSPF: Graph of OSPF adjacencies and areas
  - LAYER_ECMP: DiGraph of multi-path next-hop forwarding groups
  - LAYER_DEPENDENCY: DiGraph of cross-device structural dependencies

Provides deterministic queries:
  - Direct neighbors, interface mappings, protocol relationships
  - Multi-hop fault propagation paths
  - Blast-radius estimation
  - Conversion to canonical TopologyContext contracts
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple, Union
import networkx as nx

from services.ai.schemas.contracts import (
    TopologyContext,
    TopologyNode,
    TopologyLink,
)
from .model import (
    TopologyGraphModel,
    BGPPeerRelationship,
    OSPFAdjacency,
    PhysicalLink,
    ECMPGroup,
    CrossDeviceDependency,
)

LAYER_PHYSICAL = "physical"
LAYER_L2 = "l2"
LAYER_L3 = "l3"
LAYER_BGP = "bgp"
LAYER_OSPF = "ospf"
LAYER_ECMP = "ecmp"
LAYER_DEPENDENCY = "dependency"


class TopologyGraph:
    """
    Multi-layer in-memory graph engine backed by NetworkX.
    """

    def __init__(self, model: TopologyGraphModel):
        self.model = model
        # Base simple graph for backward-compatible operations
        self.g = nx.Graph()
        # Base BGP digraph for backward-compatible operations
        self.bgp_digraph = nx.DiGraph()

        # Multi-layer graph collection
        self.physical_multigraph = nx.MultiGraph()
        self.l2_graph = nx.Graph()
        self.l3_graph = nx.Graph()
        self.ospf_graph = nx.Graph()
        self.ecmp_digraph = nx.DiGraph()
        self.dependency_digraph = nx.DiGraph()

        self._build_graphs()

    def _build_graphs(self):
        # 1. Add Device Nodes to all relevant layers
        for dev_id, dev in self.model.devices.items():
            node_attrs = {
                "canonical_name": dev.canonical_name,
                "device_type": dev.device_type.value,
                "asn": dev.asn,
                "loopback": dev.loopback_ip,
                "protocols": dev.routing_protocols,
                "rack_id": dev.rack_id,
                "fabric_id": dev.fabric_id,
                "power_zone": dev.power_zone,
                "srlg_ids": dev.srlg_ids,
                "is_border": dev.is_border,
            }
            # Simple base graph
            self.g.add_node(dev_id, **node_attrs)
            # Physical multigraph
            self.physical_multigraph.add_node(dev_id, **node_attrs)
            # L2 and L3 layers
            self.l2_graph.add_node(dev_id, **node_attrs)
            self.l3_graph.add_node(dev_id, **node_attrs)
            # Protocol and dependency layers
            self.bgp_digraph.add_node(dev_id, asn=dev.asn, loopback=dev.loopback_ip)
            self.ospf_graph.add_node(dev_id, **node_attrs)
            self.ecmp_digraph.add_node(dev_id, **node_attrs)
            self.dependency_digraph.add_node(dev_id, **node_attrs)

        # 2. Add Physical Links
        for link in self.model.physical_links:
            src = link.source_device.lower()
            tgt = link.target_device.lower()
            link_data = {
                "link_id": link.link_id,
                "source_interface": link.source_interface,
                "target_interface": link.target_interface,
                "speed": link.speed_mbps,
                "link_type": link.link_type,
                "source_ip": link.source_ip,
                "target_ip": link.target_ip,
                "subnet": link.subnet,
                "is_lag_member": link.is_lag_member,
                "lag_bundle_id": link.lag_bundle_id,
                "srlg": link.srlg,
                "latency_ms": link.latency_ms,
            }

            # Backward-compatible simple graph (keeps latest or single edge)
            self.g.add_edge(src, tgt, **link_data)

            # MultiGraph preserving distinct parallel physical links
            self.physical_multigraph.add_edge(src, tgt, key=link.link_id, **link_data)

            # L3 Layer link if IP/routed
            self.l3_graph.add_edge(src, tgt, **link_data)

            # L2 Layer link
            self.l2_graph.add_edge(src, tgt, **link_data)

        # 3. Add BGP Sessions to DiGraph
        for peer in self.model.bgp_peers:
            loc = peer.local_device.lower()
            rem = peer.remote_device.lower()
            if self.g.has_node(loc) and self.g.has_node(rem):
                self.bgp_digraph.add_edge(
                    loc,
                    rem,
                    peer_type=peer.peer_type,
                    remote_ip=peer.remote_ip,
                    local_as=peer.local_as,
                    remote_as=peer.remote_as,
                    status=peer.status,
                    session_state=peer.session_state,
                )

        # 4. Add OSPF Adjacencies
        for ospf in self.model.ospf_adjacencies:
            loc = ospf.local_device.lower()
            rem = ospf.remote_device.lower()
            if self.ospf_graph.has_node(loc) and self.ospf_graph.has_node(rem):
                self.ospf_graph.add_edge(
                    loc,
                    rem,
                    area=ospf.area,
                    cost=ospf.cost,
                    state=ospf.state,
                    network_type=ospf.network_type,
                )

        # 5. Add ECMP Groups
        for grp in self.model.ecmp_groups:
            dev = grp.device_id.lower()
            for nh in grp.next_hops:
                nh_clean = nh.lower()
                if self.ecmp_digraph.has_node(dev) and self.ecmp_digraph.has_node(nh_clean):
                    self.ecmp_digraph.add_edge(
                        dev,
                        nh_clean,
                        group_id=grp.group_id,
                        destination_prefix=grp.destination_prefix,
                        status=grp.status,
                        is_active=(nh in grp.active_next_hops or nh_clean in grp.active_next_hops),
                    )

        # 6. Add Cross-Device Dependencies
        for dep in self.model.dependencies:
            dep_dev = dep.dependent_device.lower()
            sup_dev = dep.supporting_device.lower()
            if self.dependency_digraph.has_node(dep_dev) and self.dependency_digraph.has_node(sup_dev):
                self.dependency_digraph.add_edge(
                    dep_dev,
                    sup_dev,
                    dependency_id=dep.dependency_id,
                    dependency_type=dep.dependency_type,
                    is_redundant=dep.is_redundant,
                    criticality=dep.criticality,
                )

    def get_layer(self, layer_name: str) -> Union[nx.Graph, nx.DiGraph, nx.MultiGraph]:
        """Returns the NetworkX graph corresponding to the requested topology layer."""
        lname = layer_name.lower()
        if lname == LAYER_PHYSICAL:
            return self.physical_multigraph
        elif lname == LAYER_L2:
            return self.l2_graph
        elif lname == LAYER_L3:
            return self.l3_graph
        elif lname == LAYER_BGP:
            return self.bgp_digraph
        elif lname == LAYER_OSPF:
            return self.ospf_graph
        elif lname == LAYER_ECMP:
            return self.ecmp_digraph
        elif lname == LAYER_DEPENDENCY:
            return self.dependency_digraph
        return self.g

    def get_directly_connected(self, device_id: str) -> List[str]:
        """Returns list of directly connected neighbor device IDs."""
        d = device_id.lower()
        if not self.g.has_node(d):
            return []
        return sorted(list(self.g.neighbors(d)))

    def get_neighboring_interfaces(self, device_id: str, interface_name: str) -> Optional[Tuple[str, str]]:
        """
        Returns (remote_device, remote_interface) connected to device_id:interface_name.
        """
        d = device_id.lower()
        if not self.g.has_node(d):
            return None

        # Check multi-graph first for exact interface matching across parallel edges
        if self.physical_multigraph.has_node(d):
            for nbr in self.physical_multigraph.neighbors(d):
                edge_dict = self.physical_multigraph.get_edge_data(d, nbr)
                if edge_dict:
                    for key, edge_data in edge_dict.items():
                        if edge_data.get("source_device") == d and edge_data.get("source_interface") == interface_name:
                            return (edge_data.get("target_device"), edge_data.get("target_interface"))
                        elif edge_data.get("target_device") == d and edge_data.get("target_interface") == interface_name:
                            return (edge_data.get("source_device"), edge_data.get("source_interface"))
                        elif edge_data.get("source_interface") == interface_name:
                            return (nbr, edge_data.get("target_interface"))
                        elif edge_data.get("target_interface") == interface_name:
                            return (nbr, edge_data.get("source_interface"))

        # Fallback to simple graph
        for n in self.g.neighbors(d):
            edge_data = self.g.get_edge_data(d, n)
            if edge_data:
                if edge_data.get("source_device") == d and edge_data.get("source_interface") == interface_name:
                    return (edge_data.get("target_device"), edge_data.get("target_interface"))
                elif edge_data.get("target_device") == d and edge_data.get("target_interface") == interface_name:
                    return (edge_data.get("source_device"), edge_data.get("source_interface"))
                elif edge_data.get("source_interface") == interface_name:
                    return (n, edge_data.get("target_interface"))
                elif edge_data.get("target_interface") == interface_name:
                    return (n, edge_data.get("source_interface"))
        return None

    def get_bgp_peers(self, device_id: str) -> List[BGPPeerRelationship]:
        """Returns all configured BGP peer relationships for a device."""
        d = device_id.lower()
        return [p for p in self.model.bgp_peers if p.local_device.lower() == d]

    def get_unique_bgp_peer_count(self) -> int:
        """Returns the number of unique bidirectional BGP administrative peering pairs."""
        pairs = {tuple(sorted([p.local_device.lower(), p.remote_device.lower()])) for p in self.model.bgp_peers}
        return len(pairs)

    def has_node(self, device_id: str) -> bool:
        """Checks if a device exists in the topology model or base graph."""
        d = device_id.lower()
        return d in self.model.devices or self.g.has_node(d)

    def get_node(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Returns node attributes for device_id."""
        d = device_id.lower()
        if d in self.model.devices:
            dev = self.model.devices[d]
            return {
                "device_id": dev.device_id,
                "canonical_name": dev.canonical_name,
                "device_type": dev.device_type.value if hasattr(dev.device_type, "value") else str(dev.device_type),
                "interfaces": list(dev.interfaces.keys()),
                "asn": dev.asn,
            }
        if self.g.has_node(d):
            return dict(self.g.nodes[d])
        return None

    def get_directed_bgp_session_count(self) -> int:
        """Returns the number of directed BGP session endpoints / DiGraph edges."""
        return len(self.model.bgp_peers)

    def get_ospf_adjacencies(self, device_id: str) -> List[OSPFAdjacency]:
        """Returns all configured OSPF adjacencies for a device."""
        d = device_id.lower()
        return [o for o in self.model.ospf_adjacencies if o.local_device.lower() == d]

    def get_ecmp_groups_for_device(self, device_id: str) -> List[ECMPGroup]:
        """Returns all configured ECMP groups for a device."""
        d = device_id.lower()
        return [g for g in self.model.ecmp_groups if g.device_id.lower() == d]

    def get_dependencies_for_device(self, device_id: str) -> List[CrossDeviceDependency]:
        """Returns all dependencies where device_id is the dependent device."""
        d = device_id.lower()
        return [dep for dep in self.model.dependencies if dep.dependent_device.lower() == d]

    def get_fault_propagation_paths(self, source_device: str, max_depth: int = 2) -> List[List[str]]:
        """
        Identifies potential fault propagation paths from source device up to max_depth hops.
        """
        s = source_device.lower()
        if not self.g.has_node(s):
            return []

        paths: List[List[str]] = []
        for target in self.g.nodes():
            if target != s:
                try:
                    for path in nx.all_simple_paths(self.g, source=s, target=target, cutoff=max_depth):
                        paths.append(path)
                except nx.NetworkXNoPath:
                    pass
        return paths

    def validate_cross_device_path(self, device_a: str, device_b: str) -> bool:
        """
        Determines whether two devices share a valid topology relationship / path.
        Returns False if devices are disjoint or unlinked.
        """
        a, b = device_a.lower(), device_b.lower()
        if not self.g.has_node(a) or not self.g.has_node(b):
            return False
        return nx.has_path(self.g, a, b)

    def estimate_blast_radius(
        self,
        affected_devices: List[str],
        affected_interfaces: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Calculates direct impact, adjacent downstream blast radius, and prefix risk score.
        Preserves 100% backward compatibility with existing tests.
        """
        affected = set(d.lower() for d in affected_devices if self.g.has_node(d.lower()))
        interfaces = affected_interfaces or []

        directly_impacted_neighbors: Set[str] = set()
        bgp_peers_impacted: Set[str] = set()

        for d in affected:
            for neighbor in self.g.neighbors(d):
                if neighbor not in affected:
                    directly_impacted_neighbors.add(neighbor)
            for peer in self.get_bgp_peers(d):
                if peer.remote_device.lower() not in affected:
                    bgp_peers_impacted.add(peer.remote_device)

        # Blast radius score normalized [0.0 - 1.0]
        total_nodes = max(1, len(self.g.nodes()))
        impacted_nodes_count = len(affected) + len(directly_impacted_neighbors)
        blast_score = round(min(1.0, impacted_nodes_count / total_nodes), 3)

        return {
            "originating_devices": sorted(list(affected)),
            "affected_interfaces": interfaces,
            "directly_impacted_neighbors": sorted(list(directly_impacted_neighbors)),
            "bgp_peers_at_risk": sorted(list(bgp_peers_impacted)),
            "total_nodes_in_topology": total_nodes,
            "blast_radius_device_count": impacted_nodes_count,
            "blast_radius_score": blast_score,
            "severity_assessment": "CRITICAL" if blast_score > 0.5 else ("HIGH" if blast_score > 0.25 else "MEDIUM")
        }

    def to_topology_context(self, affected_devices: List[str]) -> TopologyContext:
        """
        Extracts sub-graph for affected devices and converts into canonical TopologyContext contract.
        """
        clean_devs = set(d.lower() for d in affected_devices)
        # Expand 1 hop to include immediate neighbors
        expanded_nodes: Set[str] = set(clean_devs)
        for d in clean_devs:
            if self.g.has_node(d):
                for n in self.g.neighbors(d):
                    expanded_nodes.add(n)

        # If empty or not in graph, provide available nodes
        if not expanded_nodes:
            expanded_nodes = set(list(self.g.nodes())[:4])

        nodes: List[TopologyNode] = []
        for n in expanded_nodes:
            if self.g.has_node(n):
                attrs = dict(self.g.nodes[n])
                node_type = attrs.pop("device_type", "router")
                nodes.append(TopologyNode(node_id=n, node_type=node_type, attributes=attrs))

        links: List[TopologyLink] = []
        for u in expanded_nodes:
            for v in expanded_nodes:
                if u < v and self.g.has_edge(u, v):
                    data = self.g.get_edge_data(u, v)
                    links.append(TopologyLink(
                        source=u,
                        target=v,
                        interface_source=data.get("source_interface"),
                        interface_target=data.get("target_interface"),
                        attributes={"speed": data.get("speed", 10000)}
                    ))

        neighbors_map: Dict[str, List[str]] = {}
        for n in expanded_nodes:
            if self.g.has_node(n):
                neighbors_map[n] = sorted([nbr for nbr in self.g.neighbors(n) if nbr in expanded_nodes])

        protocol_rel: Dict[str, Any] = {
            "bgp_peers": [
                p.model_dump() for p in self.model.bgp_peers
                if p.local_device in expanded_nodes and p.remote_device in expanded_nodes
            ],
            "ospf_adjacencies": [
                o.model_dump() for o in self.model.ospf_adjacencies
                if o.local_device in expanded_nodes and o.remote_device in expanded_nodes
            ]
        }

        affected_path = sorted(list(clean_devs))

        return TopologyContext(
            nodes=nodes,
            links=links,
            affected_path=affected_path,
            neighbors=neighbors_map,
            protocol_relationships=protocol_rel
        )

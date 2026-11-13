"""
validator.py — Parameter and Target Validation for Remediation Proposals.

Verifies target device existence, interface ownership, protocol relationships, and parameter consistency
against the verified network topology.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from services.ai.schemas.contracts import RemediationProposal
from services.ai.agents.topology.graph import TopologyGraph
from .action_registry import action_registry


class RemediationValidator:
    """
    Validates remediation targets, interfaces, and protocol bindings against actual network topology.
    """

    def __init__(self, topology_graph: Optional[TopologyGraph] = None) -> None:
        self.topology_graph = topology_graph

    def set_topology_graph(self, topology_graph: TopologyGraph) -> None:
        self.topology_graph = topology_graph

    def validate_proposal_targets(
        self,
        proposal: RemediationProposal,
        topology_graph: Optional[TopologyGraph] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validates target device, interface, and protocol relationships against topology.
        """
        graph = topology_graph or self.topology_graph
        errors: List[str] = []

        target_dev = proposal.target_device or proposal.target.split(":")[0]
        target_iface = proposal.target_interface or (proposal.target.split(":", 1)[1] if ":" in proposal.target else None)

        # 1. Device existence check
        if graph:
            d_lower = target_dev.lower()
            has_dev = graph.has_node(d_lower) if hasattr(graph, "has_node") else (graph.g.has_node(d_lower) if hasattr(graph, "g") else False)
            if not has_dev:
                errors.append(f"Target device '{target_dev}' does not exist in validated network topology.")
                return False, errors

            node_data = (graph.get_node(d_lower) if hasattr(graph, "get_node") else (dict(graph.g.nodes[d_lower]) if hasattr(graph, "g") and graph.g.has_node(d_lower) else {})) or {}
            device_type = (node_data.get("device_type") or node_data.get("role") or "").upper()
            action_def = action_registry.get(proposal.operation)

            # 2. Check if device type is allowed for this operation
            if action_def and action_def.allowed_device_types:
                allowed_types = [t.upper() for t in action_def.allowed_device_types]
                if device_type and device_type not in allowed_types:
                    errors.append(
                        f"Device '{target_dev}' has role '{device_type}', which is not permitted for operation '{proposal.operation}'. "
                        f"Allowed roles: {allowed_types}."
                    )

            # 3. Interface existence and ownership check
            if target_iface:
                device_interfaces = node_data.get("interfaces", [])
                # If interface list is in node data, verify ownership
                if device_interfaces and target_iface not in device_interfaces:
                    # Also check physical multigraph edges
                    has_edge_iface = False
                    phys_g = getattr(graph, "physical_multigraph", None)
                    if phys_g and phys_g.has_node(target_dev):
                        for _, _, edata in phys_g.edges(target_dev, data=True):
                            if edata.get("source_interface") == target_iface or edata.get("target_interface") == target_iface:
                                has_edge_iface = True
                                break
                    if not has_edge_iface:
                        errors.append(f"Interface '{target_iface}' does not belong to target device '{target_dev}'.")

            # 4. Protocol-specific checks
            if proposal.operation == "reset_bgp_session":
                peer_ip = proposal.parameters.get("peer_ip")
                if not peer_ip:
                    errors.append("BGP peer IP is required for reset_bgp_session.")
                else:
                    # Verify peer relationship in BGP layer if present
                    bgp_layer = getattr(graph, "bgp_digraph", None)
                    if bgp_layer and bgp_layer.has_node(target_dev):
                        has_peer = False
                        for _, neighbor, edata in bgp_layer.out_edges(target_dev, data=True):
                            if edata.get("peer_ip") == peer_ip or neighbor == peer_ip:
                                has_peer = True
                                break
                        # If peer IP not matched directly, check if target has any configured peers
                        if not has_peer and bgp_layer.out_degree(target_dev) == 0:
                            errors.append(f"Device '{target_dev}' has no active or configured BGP peering sessions.")

        return (len(errors) == 0, errors)


# Global singleton instance
remediation_validator = RemediationValidator()

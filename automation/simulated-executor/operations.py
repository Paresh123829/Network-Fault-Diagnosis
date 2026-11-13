"""
operations.py — Deterministic Execution Handlers for Allow-Listed Network Operations.

These handlers manipulate ONLY the in-memory simulated network state model.
They do NOT execute shell commands, invoke subprocesses, or communicate with external network equipment.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple
try:
    from .state_manager import NetworkSimulatorStateManager
except ImportError:
    from state_manager import NetworkSimulatorStateManager

logger = logging.getLogger(__name__)


def execute_restore_interface_admin_state(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Sets simulated interface admin_state to UP and transitions operational_state to UP.
    """
    device_id = parameters.get("target_device", "")
    interface_name = parameters.get("target_interface", "")
    admin_state = parameters.get("admin_state", "UP").upper()

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_interface_admin_state(device_id, interface_name, admin_state)
    logger.info(f"[SIMULATOR] Restored interface {device_id}:{interface_name} admin_state -> {admin_state}")

    post_iface = sim.get_interface(device_id, interface_name) or {}
    return True, f"Interface {device_id}:{interface_name} admin state successfully restored to {admin_state}.", post_iface


def execute_disable_interface_admin_state(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Rollback handler: Sets simulated interface admin_state to DOWN.
    """
    device_id = parameters.get("target_device", "")
    interface_name = parameters.get("target_interface", "")

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_interface_admin_state(device_id, interface_name, "DOWN")
    logger.info(f"[SIMULATOR ROLLBACK] Set interface {device_id}:{interface_name} admin_state -> DOWN")
    post_iface = sim.get_interface(device_id, interface_name) or {}
    return True, f"Interface {device_id}:{interface_name} reverted to DOWN.", post_iface


def execute_reset_bgp_session(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Soft-clears a simulated BGP session and restores it to ESTABLISHED state.
    """
    device_id = parameters.get("target_device", "")
    peer_ip = parameters.get("peer_ip", "")

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    # Soft-reset: cycle to ESTABLISHED
    sim.set_bgp_session_state(device_id, peer_ip, "ESTABLISHED")
    logger.info(f"[SIMULATOR] BGP session reset on {device_id} peer {peer_ip} -> ESTABLISHED")

    post_session = sim.get_bgp_session(device_id, peer_ip) or {}
    return True, f"BGP session on {device_id} to peer {peer_ip} reset and returned to ESTABLISHED.", post_session


def execute_reconfigure_bgp_session(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Rollback handler: Re-asserts baseline BGP configuration.
    """
    device_id = parameters.get("target_device", "")
    peer_ip = parameters.get("peer_ip", "")
    action = parameters.get("action", "reassert_baseline")

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_bgp_session_state(device_id, peer_ip, "IDLE")
    logger.info(f"[SIMULATOR ROLLBACK] BGP session on {device_id} peer {peer_ip} rolled back to IDLE")
    post_session = sim.get_bgp_session(device_id, peer_ip) or {}
    return True, f"BGP session on {device_id} to peer {peer_ip} rolled back.", post_session


def execute_restore_bfd_session(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Restores simulated BFD session state to UP.
    """
    device_id = parameters.get("target_device", "")
    peer_ip = parameters.get("peer_ip", "")

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_bfd_session_state(device_id, peer_ip, "UP")
    logger.info(f"[SIMULATOR] BFD session on {device_id} peer {peer_ip} restored -> UP")
    post_session = sim.get_bfd_session(device_id, peer_ip) or {}
    return True, f"BFD session on {device_id} to {peer_ip} restored to UP.", post_session


def execute_disable_bfd_session(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Rollback handler: Sets simulated BFD session to DOWN.
    """
    device_id = parameters.get("target_device", "")
    peer_ip = parameters.get("peer_ip", "")

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_bfd_session_state(device_id, peer_ip, "DOWN")
    logger.info(f"[SIMULATOR ROLLBACK] BFD session on {device_id} peer {peer_ip} set -> DOWN")
    post_session = sim.get_bfd_session(device_id, peer_ip) or {}
    return True, f"BFD session on {device_id} to {peer_ip} reverted to DOWN.", post_session


def execute_restore_ospf_adjacency(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Restores simulated OSPF neighbor state to FULL.
    """
    device_id = parameters.get("target_device", "")
    interface_name = parameters.get("interface", "")

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_ospf_neighbor_state(device_id, interface_name, "FULL")
    logger.info(f"[SIMULATOR] OSPF neighbor state on {device_id} interface {interface_name} restored -> FULL")
    post_ospf = sim.get_ospf_neighbor(device_id, interface_name) or {}
    return True, f"OSPF adjacency on {device_id}:{interface_name} restored to FULL.", post_ospf


def execute_disable_ospf_on_interface(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Rollback handler: Sets simulated OSPF neighbor state to DOWN.
    """
    device_id = parameters.get("target_device", "")
    interface_name = parameters.get("interface", "")

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_ospf_neighbor_state(device_id, interface_name, "DOWN")
    logger.info(f"[SIMULATOR ROLLBACK] OSPF state on {device_id}:{interface_name} reverted to DOWN")
    post_ospf = sim.get_ospf_neighbor(device_id, interface_name) or {}
    return True, f"OSPF on {device_id}:{interface_name} reverted to DOWN.", post_ospf


def execute_restore_vlan_membership(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Restores simulated VLAN membership on an interface.
    """
    device_id = parameters.get("target_device", "")
    interface_name = parameters.get("interface", "")
    vlan_id = parameters.get("vlan_id", 100)

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_vlan_membership(device_id, interface_name, vlan_id)
    logger.info(f"[SIMULATOR] VLAN membership on {device_id} interface {interface_name} restored -> VLAN {vlan_id}")
    return True, f"VLAN {vlan_id} membership on {device_id}:{interface_name} successfully restored.", {"vlan_id": vlan_id}


def execute_revert_vlan_membership(
    sim: NetworkSimulatorStateManager,
    parameters: Dict[str, Any]
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Rollback handler: Reverts VLAN membership to previous/default VLAN.
    """
    device_id = parameters.get("target_device", "")
    interface_name = parameters.get("interface", "")
    vlan_id = parameters.get("vlan_id", 1)

    if not sim.has_device(device_id):
        return False, f"Device '{device_id}' does not exist in simulation.", {}

    sim.set_vlan_membership(device_id, interface_name, vlan_id)
    logger.info(f"[SIMULATOR ROLLBACK] VLAN on {device_id}:{interface_name} reverted to VLAN {vlan_id}")
    return True, f"VLAN on {device_id}:{interface_name} reverted to VLAN {vlan_id}.", {"vlan_id": vlan_id}


# Operation dispatch table
OPERATION_HANDLERS = {
    "restore_interface_admin_state": execute_restore_interface_admin_state,
    "disable_interface_admin_state": execute_disable_interface_admin_state,
    "reset_bgp_session": execute_reset_bgp_session,
    "reconfigure_bgp_session": execute_reconfigure_bgp_session,
    "restore_bfd_session": execute_restore_bfd_session,
    "disable_bfd_session": execute_disable_bfd_session,
    "restore_ospf_adjacency": execute_restore_ospf_adjacency,
    "disable_ospf_on_interface": execute_disable_ospf_on_interface,
    "restore_vlan_membership": execute_restore_vlan_membership,
    "revert_vlan_membership": execute_revert_vlan_membership,
}

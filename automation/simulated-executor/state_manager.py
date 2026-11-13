"""
state_manager.py — Isolated In-Memory Network Simulation State Manager.

Maintains simulated operational states for devices, interfaces, BGP sessions, OSPF adjacencies,
BFD sessions, and VLAN allocations. Completely decoupled from physical or live production networks.
"""

from __future__ import annotations

import copy
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NetworkSimulatorStateManager:
    """
    In-memory simulated network state model with full snapshot and rollback capabilities.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._devices: Dict[str, Dict[str, Any]] = {}
        self._interfaces: Dict[str, Dict[str, Dict[str, Any]]] = {}  # device -> iface -> state
        self._bgp_sessions: Dict[str, Dict[str, Dict[str, Any]]] = {}  # device -> peer_ip -> state
        self._ospf_neighbors: Dict[str, Dict[str, Dict[str, Any]]] = {}  # device -> iface -> state
        self._bfd_sessions: Dict[str, Dict[str, Dict[str, Any]]] = {}  # device -> peer_ip -> state
        self._vlans: Dict[str, Dict[str, int]] = {}  # device -> iface -> vlan_id

        self.initialize_default_cisco_clos()

    def initialize_default_cisco_clos(self) -> None:
        """
        Initializes baseline healthy 4x8 Spine-Leaf Clos topology in the simulation state.
        Spines: spine1..spine4
        Leaves: leaf1..leaf8
        """
        with self._lock:
            self._devices.clear()
            self._interfaces.clear()
            self._bgp_sessions.clear()
            self._ospf_neighbors.clear()
            self._bfd_sessions.clear()
            self._vlans.clear()

            # 4 Spines
            for s in range(1, 5):
                s_id = f"spine{s}"
                self._devices[s_id] = {
                    "device_id": s_id,
                    "device_type": "SPINE",
                    "status": "UP",
                    "asn": 65000,
                }
                self._interfaces[s_id] = {}
                self._bgp_sessions[s_id] = {}
                for l in range(1, 9):
                    iface = f"Ethernet1/{l}"
                    self._interfaces[s_id][iface] = {
                        "admin_state": "UP",
                        "operational_state": "UP",
                        "speed": "100G",
                        "connected_to": f"leaf{l}",
                    }
                    peer_ip = f"10.0.{s}.{l*2}"
                    self._bgp_sessions[s_id][peer_ip] = {
                        "peer_device": f"leaf{l}",
                        "peer_asn": 65000 + l,
                        "session_state": "ESTABLISHED",
                        "uptime_seconds": 86400,
                        "prefixes_received": 120,
                    }

            # 8 Leaves
            for l in range(1, 9):
                l_id = f"leaf{l}"
                self._devices[l_id] = {
                    "device_id": l_id,
                    "device_type": "LEAF",
                    "status": "UP",
                    "asn": 65000 + l,
                }
                self._interfaces[l_id] = {}
                self._bgp_sessions[l_id] = {}
                self._vlans[l_id] = {}
                for s in range(1, 5):
                    iface = f"Ethernet1/{s}"
                    self._interfaces[l_id][iface] = {
                        "admin_state": "UP",
                        "operational_state": "UP",
                        "speed": "100G",
                        "connected_to": f"spine{s}",
                    }
                    peer_ip = f"10.0.{s}.{l*2 - 1}"
                    self._bgp_sessions[l_id][peer_ip] = {
                        "peer_device": f"spine{s}",
                        "peer_asn": 65000,
                        "session_state": "ESTABLISHED",
                        "uptime_seconds": 86400,
                        "prefixes_received": 500,
                    }

            # Add Containerlab 3-router linear chain as well
            for r in (1, 2, 3):
                r_id = f"r{r}"
                self._devices[r_id] = {
                    "device_id": r_id,
                    "device_type": "ROUTER",
                    "status": "UP",
                    "asn": 65010 + r,
                }
                self._interfaces[r_id] = {
                    "eth1": {"admin_state": "UP", "operational_state": "UP", "speed": "10G"},
                    "eth2": {"admin_state": "UP", "operational_state": "UP", "speed": "10G"},
                }
                self._bgp_sessions[r_id] = {}
                self._ospf_neighbors[r_id] = {
                    "eth1": {"neighbor_ip": f"10.1.{r}.2", "state": "FULL"},
                }

    # ─── Query Methods ────────────────────────────────────────────────────────

    def has_device(self, device_id: str) -> bool:
        with self._lock:
            return device_id in self._devices

    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._devices.get(device_id))

    def has_interface(self, device_id: str, interface_name: str) -> bool:
        with self._lock:
            return device_id in self._interfaces and interface_name in self._interfaces[device_id]

    def get_interface(self, device_id: str, interface_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if device_id in self._interfaces:
                return copy.deepcopy(self._interfaces[device_id].get(interface_name))
            return None

    def get_bgp_session(self, device_id: str, peer_ip: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if device_id in self._bgp_sessions:
                return copy.deepcopy(self._bgp_sessions[device_id].get(peer_ip))
            return None

    def get_bfd_session(self, device_id: str, peer_ip: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if device_id in self._bfd_sessions:
                return copy.deepcopy(self._bfd_sessions[device_id].get(peer_ip))
            return None

    def get_ospf_neighbor(self, device_id: str, interface_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if device_id in self._ospf_neighbors:
                return copy.deepcopy(self._ospf_neighbors[device_id].get(interface_name))
            return None

    def get_vlan(self, device_id: str, interface_name: str) -> Optional[int]:
        with self._lock:
            if device_id in self._vlans:
                return self._vlans[device_id].get(interface_name)
            return None

    # ─── Mutator Methods ──────────────────────────────────────────────────────

    def set_interface_admin_state(self, device_id: str, interface_name: str, admin_state: str) -> None:
        with self._lock:
            if device_id not in self._interfaces:
                self._interfaces[device_id] = {}
            if interface_name not in self._interfaces[device_id]:
                self._interfaces[device_id][interface_name] = {"speed": "100G"}

            admin_up = admin_state.upper() == "UP"
            self._interfaces[device_id][interface_name]["admin_state"] = "UP" if admin_up else "DOWN"
            self._interfaces[device_id][interface_name]["operational_state"] = "UP" if admin_up else "DOWN"

    def set_bgp_session_state(self, device_id: str, peer_ip: str, state: str) -> None:
        with self._lock:
            if device_id not in self._bgp_sessions:
                self._bgp_sessions[device_id] = {}
            if peer_ip not in self._bgp_sessions[device_id]:
                self._bgp_sessions[device_id][peer_ip] = {}
            self._bgp_sessions[device_id][peer_ip]["session_state"] = state.upper()

    def set_bfd_session_state(self, device_id: str, peer_ip: str, state: str) -> None:
        with self._lock:
            if device_id not in self._bfd_sessions:
                self._bfd_sessions[device_id] = {}
            if peer_ip not in self._bfd_sessions[device_id]:
                self._bfd_sessions[device_id][peer_ip] = {}
            self._bfd_sessions[device_id][peer_ip]["state"] = state.upper()

    def set_ospf_neighbor_state(self, device_id: str, interface_name: str, state: str) -> None:
        with self._lock:
            if device_id not in self._ospf_neighbors:
                self._ospf_neighbors[device_id] = {}
            if interface_name not in self._ospf_neighbors[device_id]:
                self._ospf_neighbors[device_id][interface_name] = {}
            self._ospf_neighbors[device_id][interface_name]["state"] = state.upper()

    def set_vlan_membership(self, device_id: str, interface_name: str, vlan_id: int) -> None:
        with self._lock:
            if device_id not in self._vlans:
                self._vlans[device_id] = {}
            self._vlans[device_id][interface_name] = vlan_id

    def set_interface_config(
        self,
        device_id: str,
        interface_name: str,
        admin_state: Optional[str] = None,
        operational_state: Optional[str] = None,
        speed: Optional[str] = None,
        vlan_id: Optional[int] = None,
        mode: Optional[str] = None,
        native_vlan: Optional[int] = None,
        allowed_vlans: Optional[List[int]] = None,
        mtu: Optional[int] = None,
    ) -> None:
        with self._lock:
            if device_id not in self._interfaces:
                self._interfaces[device_id] = {}
            if interface_name not in self._interfaces[device_id]:
                self._interfaces[device_id][interface_name] = {"speed": "100G"}

            iface = self._interfaces[device_id][interface_name]
            if admin_state is not None:
                iface["admin_state"] = admin_state.upper()
                if operational_state is None:
                    iface["operational_state"] = admin_state.upper()
            if operational_state is not None:
                iface["operational_state"] = operational_state.upper()
            if speed is not None:
                iface["speed"] = speed
            if vlan_id is not None:
                iface["vlan_id"] = vlan_id
                self.set_vlan_membership(device_id, interface_name, vlan_id)
            if mode is not None:
                iface["mode"] = mode.lower()
            if native_vlan is not None:
                iface["native_vlan"] = native_vlan
            if allowed_vlans is not None:
                iface["allowed_vlans"] = list(allowed_vlans)
            if mtu is not None:
                iface["mtu"] = mtu

    def set_bfd_session_config(
        self,
        device_id: str,
        peer_ip: str,
        interval_ms: Optional[int] = None,
        multiplier: Optional[int] = None,
        state: Optional[str] = None,
    ) -> None:
        with self._lock:
            if device_id not in self._bfd_sessions:
                self._bfd_sessions[device_id] = {}
            if peer_ip not in self._bfd_sessions[device_id]:
                self._bfd_sessions[device_id][peer_ip] = {}

            bfd = self._bfd_sessions[device_id][peer_ip]
            if interval_ms is not None:
                bfd["interval_ms"] = interval_ms
            if multiplier is not None:
                bfd["multiplier"] = multiplier
            if state is not None:
                bfd["state"] = state.upper()

    def set_ospf_neighbor_config(
        self,
        device_id: str,
        interface_name: str,
        area: Optional[str] = None,
        cost: Optional[int] = None,
        hello_interval: Optional[int] = None,
        dead_interval: Optional[int] = None,
        state: Optional[str] = None,
    ) -> None:
        with self._lock:
            if device_id not in self._ospf_neighbors:
                self._ospf_neighbors[device_id] = {}
            if interface_name not in self._ospf_neighbors[device_id]:
                self._ospf_neighbors[device_id][interface_name] = {}

            ospf = self._ospf_neighbors[device_id][interface_name]
            if area is not None:
                ospf["area"] = area
            if cost is not None:
                ospf["cost"] = cost
            if hello_interval is not None:
                ospf["hello_interval"] = hello_interval
            if dead_interval is not None:
                ospf["dead_interval"] = dead_interval
            if state is not None:
                ospf["state"] = state.upper()

    # ─── Snapshot & Restore ───────────────────────────────────────────────────

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Captures full atomic snapshot of simulated network state."""
        with self._lock:
            return {
                "devices": copy.deepcopy(self._devices),
                "interfaces": copy.deepcopy(self._interfaces),
                "bgp_sessions": copy.deepcopy(self._bgp_sessions),
                "ospf_neighbors": copy.deepcopy(self._ospf_neighbors),
                "bfd_sessions": copy.deepcopy(self._bfd_sessions),
                "vlans": copy.deepcopy(self._vlans),
            }

    def restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Restores network state from a previous snapshot."""
        with self._lock:
            self._devices = copy.deepcopy(snapshot.get("devices", {}))
            self._interfaces = copy.deepcopy(snapshot.get("interfaces", {}))
            self._bgp_sessions = copy.deepcopy(snapshot.get("bgp_sessions", {}))
            self._ospf_neighbors = copy.deepcopy(snapshot.get("ospf_neighbors", {}))
            self._bfd_sessions = copy.deepcopy(snapshot.get("bfd_sessions", {}))
            self._vlans = copy.deepcopy(snapshot.get("vlans", {}))


# Global singleton instance
simulator_state = NetworkSimulatorStateManager()


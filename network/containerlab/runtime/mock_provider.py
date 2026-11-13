"""
mock_provider.py — High-Fidelity Simulated Lab Provider for Containerlab.

Maintains the exact state model of the Containerlab FRR topology (R1, R2, R3, br-vlan, client1, client2),
returning authentic FRR JSON data and syslogs when live Docker execution is unavailable on the host.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ContainerlabMockProvider:
    """
    Maintains simulated in-memory state of the cnt-frr-lab Containerlab topology.
    Emits authentic FRR JSON outputs and standard IOS-XR/FRR syslog messages.
    """

    def __init__(self) -> None:
        self.reset_to_baseline()

    def reset_to_baseline(self) -> None:
        """Restores the full topology state to clean baseline convergence."""
        self._nodes = {
            "R1": {
                "interfaces": {
                    "lo": {"admin_state": "up", "oper_state": "up", "ip": "10.0.0.1/32"},
                    "eth1": {"admin_state": "up", "oper_state": "up", "ip": "172.16.12.1/30", "ospf_cost": 10, "ospf_hello": 5, "ospf_dead": 20},
                    "eth2": {"admin_state": "up", "oper_state": "up", "trunk": True},
                    "eth2.100": {"admin_state": "up", "oper_state": "up", "ip": "192.168.100.1/24"},
                    "eth2.200": {"admin_state": "up", "oper_state": "up", "ip": "192.168.200.1/24"},
                    "eth3": {"admin_state": "up", "oper_state": "up", "ip": "172.16.13.1/30", "ospf_cost": 50, "ospf_hello": 5, "ospf_dead": 20},
                },
                "bgp": {
                    "router_id": "10.0.0.1",
                    "as": 65001,
                    "peers": {
                        "172.16.12.2": {
                            "remote_as": 65002,
                            "state": "Established",
                            "pfx_rcvd": 4,
                            "uptime_sec": 3600,
                            "bfd_enabled": True,
                        },
                        "172.16.13.2": {
                            "remote_as": 65003,
                            "state": "Established",
                            "pfx_rcvd": 2,
                            "uptime_sec": 3600,
                            "bfd_enabled": False,
                        },
                    },
                },
                "ospf": {
                    "router_id": "10.0.0.1",
                    "neighbors": {
                        "eth1": {"neighbor_id": "10.0.0.2", "ip": "172.16.12.2", "state": "Full"},
                        "eth3": {"neighbor_id": "10.0.0.3", "ip": "172.16.13.2", "state": "Full"},
                    },
                },
                "bfd": {
                    "peers": {
                        "172.16.12.2": {
                            "status": "Up",
                            "detect_multiplier": 3,
                            "rx_ms": 300,
                            "tx_ms": 300,
                            "interface": "eth1",
                        }
                    }
                },
                "routes": ["10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32", "172.16.12.0/30", "172.16.13.0/30", "172.16.23.0/30", "192.168.100.0/24"],
            },
            "R2": {
                "interfaces": {
                    "lo": {"admin_state": "up", "oper_state": "up", "ip": "10.0.0.2/32"},
                    "eth1": {"admin_state": "up", "oper_state": "up", "ip": "172.16.12.2/30", "ospf_cost": 10, "ospf_hello": 5, "ospf_dead": 20},
                    "eth2": {"admin_state": "up", "oper_state": "up", "ip": "172.16.23.1/30", "ospf_cost": 10, "ospf_hello": 5, "ospf_dead": 20},
                    "eth3": {"admin_state": "up", "oper_state": "up", "trunk": True},
                    "eth3.100": {"admin_state": "up", "oper_state": "up", "ip": "192.168.100.2/24"},
                },
                "bgp": {
                    "router_id": "10.0.0.2",
                    "as": 65002,
                    "peers": {
                        "172.16.12.1": {
                            "remote_as": 65001,
                            "state": "Established",
                            "pfx_rcvd": 3,
                            "uptime_sec": 3600,
                            "bfd_enabled": True,
                        },
                        "172.16.23.2": {
                            "remote_as": 65003,
                            "state": "Established",
                            "pfx_rcvd": 2,
                            "uptime_sec": 3600,
                            "bfd_enabled": True,
                        },
                    },
                },
                "ospf": {
                    "router_id": "10.0.0.2",
                    "neighbors": {
                        "eth1": {"neighbor_id": "10.0.0.1", "ip": "172.16.12.1", "state": "Full"},
                        "eth2": {"neighbor_id": "10.0.0.3", "ip": "172.16.23.2", "state": "Full"},
                    },
                },
                "bfd": {
                    "peers": {
                        "172.16.12.1": {"status": "Up", "detect_multiplier": 3, "rx_ms": 300, "tx_ms": 300, "interface": "eth1"},
                        "172.16.23.2": {"status": "Up", "detect_multiplier": 3, "rx_ms": 300, "tx_ms": 300, "interface": "eth2"},
                    }
                },
                "routes": ["10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32", "172.16.12.0/30", "172.16.23.0/30", "192.168.100.0/24"],
            },
            "R3": {
                "interfaces": {
                    "lo": {"admin_state": "up", "oper_state": "up", "ip": "10.0.0.3/32"},
                    "eth1": {"admin_state": "up", "oper_state": "up", "ip": "172.16.23.2/30", "ospf_cost": 10, "ospf_hello": 5, "ospf_dead": 20},
                    "eth2": {"admin_state": "up", "oper_state": "up", "ip": "172.16.13.2/30", "ospf_cost": 50, "ospf_hello": 5, "ospf_dead": 20},
                },
                "bgp": {
                    "router_id": "10.0.0.3",
                    "as": 65003,
                    "peers": {
                        "172.16.23.1": {"remote_as": 65002, "state": "Established", "pfx_rcvd": 4, "uptime_sec": 3600, "bfd_enabled": True},
                        "172.16.13.1": {"remote_as": 65001, "state": "Established", "pfx_rcvd": 3, "uptime_sec": 3600, "bfd_enabled": False},
                    },
                },
                "ospf": {
                    "router_id": "10.0.0.3",
                    "neighbors": {
                        "eth1": {"neighbor_id": "10.0.0.2", "ip": "172.16.23.1", "state": "Full"},
                        "eth2": {"neighbor_id": "10.0.0.1", "ip": "172.16.13.1", "state": "Full"},
                    },
                },
                "bfd": {
                    "peers": {
                        "172.16.23.1": {"status": "Up", "detect_multiplier": 3, "rx_ms": 300, "tx_ms": 300, "interface": "eth1"},
                    }
                },
                "routes": ["10.0.0.1/32", "10.0.0.2/32", "10.0.0.3/32", "172.16.13.0/30", "172.16.23.0/30"],
            },
            "br-vlan": {
                "bridge": "br0",
                "vlan_filtering": True,
                "ports": {
                    "eth1": {"role": "trunk", "allowed_vids": [100, 200], "pvid": 1},
                    "eth2": {"role": "trunk", "allowed_vids": [100, 200], "pvid": 1},
                    "eth3": {"role": "access", "allowed_vids": [100], "pvid": 100},
                    "eth4": {"role": "access", "allowed_vids": [100], "pvid": 100},
                },
            },
            "client1": {
                "ip": "192.168.100.10/24",
                "gateway": "192.168.100.1",
                "ping_ok": True,
            },
            "client2": {
                "ip": "192.168.100.20/24",
                "gateway": "192.168.100.1",
                "ping_ok": True,
            },
        }
        self._syslog_buffer: List[Dict[str, Any]] = []

    def get_node_inventory(self) -> List[str]:
        return list(self._nodes.keys())

    def execute(self, node: str, args: List[str]) -> Tuple[int, str, str]:
        """
        Interprets allow-listed CLI and vtysh commands against the simulated topology.
        """
        if node not in self._nodes:
            return 1, "", f"Error: No such container: {node}"

        cmd_line = " ".join(args)

        # ─── BGP Queries ───
        if "show ip bgp json" in cmd_line or "show ip bgp summary json" in cmd_line:
            node_data = self._nodes.get(node, {})
            bgp_data = node_data.get("bgp", {})
            peers_out = {}
            for peer_ip, pinfo in bgp_data.get("peers", {}).items():
                peers_out[peer_ip] = {
                    "remoteAs": pinfo["remote_as"],
                    "state": pinfo["state"],
                    "pfxRcvd": pinfo["pfx_rcvd"] if pinfo["state"] == "Established" else 0,
                    "peerUptimeMsec": pinfo["uptime_sec"] * 1000 if pinfo["state"] == "Established" else 0,
                }
            res_json = {
                "routerId": bgp_data.get("router_id", "0.0.0.0"),
                "as": bgp_data.get("as", 65000),
                "peers": peers_out,
            }
            return 0, json.dumps(res_json), ""

        # ─── OSPF Queries ───
        if "show ip ospf neighbor json" in cmd_line:
            node_data = self._nodes.get(node, {})
            ospf_data = node_data.get("ospf", {})
            nbrs_out = {}
            for ifname, ninfo in ospf_data.get("neighbors", {}).items():
                nbrs_out[ifname] = [{
                    "nbrId": ninfo["neighbor_id"],
                    "ip": ninfo["ip"],
                    "nbrState": ninfo["state"],
                }]
            res_json = {"neighbors": nbrs_out}
            return 0, json.dumps(res_json), ""

        # ─── BFD Queries ───
        if "show bfd peers json" in cmd_line:
            node_data = self._nodes.get(node, {})
            bfd_data = node_data.get("bfd", {})
            peers_list = []
            for peer_ip, binfo in bfd_data.get("peers", {}).items():
                peers_list.append({
                    "peer": peer_ip,
                    "status": binfo["status"],
                    "detectMultiplier": binfo["detect_multiplier"],
                    "receiveInterval": binfo["rx_ms"],
                    "transmitInterval": binfo["tx_ms"],
                })
            return 0, json.dumps(peers_list), ""

        # ─── Route Queries ───
        if "show ip route json" in cmd_line:
            node_data = self._nodes.get(node, {})
            routes_list = node_data.get("routes", [])
            routes_dict = {r: [{"protocol": "ospf" if "10.0" in r else "connected"}] for r in routes_list}
            return 0, json.dumps(routes_dict), ""

        # ─── Interface State Queries ───
        if "ip -j link" in cmd_line or "ip link show" in cmd_line:
            node_data = self._nodes.get(node, {})
            ifaces = node_data.get("interfaces", {})
            iface_list = []
            for ifname, idata in ifaces.items():
                iface_list.append({
                    "ifname": ifname,
                    "flags": ["UP", "LOWER_UP"] if idata["oper_state"] == "up" else ["NO-CARRIER"],
                    "operstate": idata["oper_state"].upper(),
                    "adminstate": idata["admin_state"].upper(),
                })
            return 0, json.dumps(iface_list), ""

        # ─── Bridge VLAN Queries ───
        if "bridge vlan show" in cmd_line:
            if node == "br-vlan":
                ports = self._nodes["br-vlan"]["ports"]
                lines = ["port\tvlan ids"]
                for p, pdata in ports.items():
                    if pdata["role"] == "trunk":
                        lines.append(f"{p}\t100")
                        lines.append(f"\t200")
                    else:
                        lines.append(f"{p}\t{pdata['pvid']} PVID Egress Untagged")
                return 0, "\n".join(lines), ""
            return 0, "", ""

        # ─── Ping Reachability ───
        if "ping" in cmd_line:
            if node in ("client1", "client2"):
                can_ping = self._nodes[node]["ping_ok"]
                if can_ping:
                    return 0, "3 packets transmitted, 3 received, 0% packet loss", ""
                else:
                    return 1, "3 packets transmitted, 0 received, 100% packet loss", "Destination Host Unreachable"
            return 0, "3 packets transmitted, 3 received, 0% packet loss", ""

        # ─── State Mutations: BGP Clear ───
        if "clear bgp" in cmd_line:
            peer_ip = "172.16.12.2" if "172.16.12.2" in cmd_line else "172.16.23.2"
            is_soft = "soft" in cmd_line
            peers = self._nodes[node].get("bgp", {}).get("peers", {})
            if peer_ip in peers:
                if is_soft:
                    # Soft recovery -> returns to Established
                    peers[peer_ip]["state"] = "Established"
                    peers[peer_ip]["pfx_rcvd"] = 4
                    if "10.0.0.2/32" not in self._nodes[node]["routes"]:
                        self._nodes[node]["routes"].append("10.0.0.2/32")
                    self._syslog_buffer.append({
                        "node": node,
                        "msg": f"%ROUTING-BGP-5-ADJCHANGE: neighbor {peer_ip} Up - Soft reset completed",
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
                else:
                    # Injected failure -> drops to Idle
                    peers[peer_ip]["state"] = "Idle"
                    peers[peer_ip]["pfx_rcvd"] = 0
                    if "10.0.0.2/32" in self._nodes[node]["routes"]:
                        self._nodes[node]["routes"].remove("10.0.0.2/32")
                    self._syslog_buffer.append({
                        "node": node,
                        "msg": f"%ROUTING-BGP-5-ADJCHANGE: neighbor {peer_ip} Down - BGP clear requested",
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
                return 0, f"BGP session to {peer_ip} cleared.", ""
            return 0, "OK", ""

        # ─── State Mutations: Interface Shutdown / No Shutdown ───
        if "interface" in cmd_line and "shutdown" in cmd_line and "no shutdown" not in cmd_line:
            for ifname in ("eth1", "eth2", "eth3"):
                if ifname in cmd_line:
                    ifaces = self._nodes[node].get("interfaces", {})
                    if ifname in ifaces:
                        ifaces[ifname]["admin_state"] = "down"
                        ifaces[ifname]["oper_state"] = "down"
                        # Cascading failure: OSPF & BGP neighbor drop
                        if node == "R2" and ifname == "eth1":
                            self._nodes["R2"]["ospf"]["neighbors"]["eth1"]["state"] = "Down"
                            self._nodes["R2"]["bgp"]["peers"]["172.16.12.1"]["state"] = "Idle"
                            self._nodes["R1"]["ospf"]["neighbors"]["eth1"]["state"] = "Down"
                            self._nodes["R1"]["bgp"]["peers"]["172.16.12.2"]["state"] = "Idle"
                        self._syslog_buffer.append({
                            "node": node,
                            "msg": f"%PKT_INFRA-LINK-3-UPDOWN: Interface {ifname}, changed state to Down",
                            "time": datetime.now(timezone.utc).isoformat(),
                        })
                    return 0, f"Interface {ifname} shutdown.", ""
            return 0, "OK", ""

        if "interface" in cmd_line and "no shutdown" in cmd_line:
            for ifname in ("eth1", "eth2", "eth3"):
                if ifname in cmd_line:
                    ifaces = self._nodes[node].get("interfaces", {})
                    if ifname in ifaces:
                        ifaces[ifname]["admin_state"] = "up"
                        ifaces[ifname]["oper_state"] = "up"
                        if node == "R2" and ifname == "eth1":
                            self._nodes["R2"]["ospf"]["neighbors"]["eth1"]["state"] = "Full"
                            self._nodes["R2"]["bgp"]["peers"]["172.16.12.1"]["state"] = "Established"
                            self._nodes["R1"]["ospf"]["neighbors"]["eth1"]["state"] = "Full"
                            self._nodes["R1"]["bgp"]["peers"]["172.16.12.2"]["state"] = "Established"
                        self._syslog_buffer.append({
                            "node": node,
                            "msg": f"%PKT_INFRA-LINK-3-UPDOWN: Interface {ifname}, changed state to Up",
                            "time": datetime.now(timezone.utc).isoformat(),
                        })
                    return 0, f"Interface {ifname} restored to UP.", ""
            return 0, "OK", ""

        # ─── State Mutations: OSPF Timers ───
        if "hello-interval" in cmd_line or "dead-interval" in cmd_line:
            if "hello-interval 20" in cmd_line or "dead-interval 80" in cmd_line:
                # Timer mismatch injected
                self._nodes[node]["interfaces"]["eth1"]["ospf_hello"] = 20
                self._nodes[node]["interfaces"]["eth1"]["ospf_dead"] = 80
                self._nodes[node]["ospf"]["neighbors"]["eth1"]["state"] = "Down"
                self._syslog_buffer.append({
                    "node": node,
                    "msg": "%OSPF-5-ADJCHANGE: Nbr 10.0.0.1 on eth1 Down: Dead timer expired",
                    "time": datetime.now(timezone.utc).isoformat(),
                })
            elif "hello-interval 5" in cmd_line or "dead-interval 20" in cmd_line:
                # Timer restored
                self._nodes[node]["interfaces"]["eth1"]["ospf_hello"] = 5
                self._nodes[node]["interfaces"]["eth1"]["ospf_dead"] = 20
                self._nodes[node]["ospf"]["neighbors"]["eth1"]["state"] = "Full"
                self._syslog_buffer.append({
                    "node": node,
                    "msg": "%OSPF-5-ADJCHANGE: Nbr 10.0.0.1 on eth1 Up: Adjacency restored",
                    "time": datetime.now(timezone.utc).isoformat(),
                })
            return 0, "OSPF timers updated.", ""

        # ─── State Mutations: Bridge VLAN ───
        if "bridge vlan" in cmd_line:
            if node == "br-vlan":
                if "vid 200 pvid" in cmd_line:
                    # Injected VLAN mismatch
                    self._nodes["br-vlan"]["ports"]["eth3"]["pvid"] = 200
                    self._nodes["client1"]["ping_ok"] = False
                    self._syslog_buffer.append({
                        "node": "br-vlan",
                        "msg": "BR-VLAN: eth3 pvid changed to 200 - VLAN 100 isolated",
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
                elif "vid 100 pvid" in cmd_line:
                    # Restored VLAN membership
                    self._nodes["br-vlan"]["ports"]["eth3"]["pvid"] = 100
                    self._nodes["client1"]["ping_ok"] = True
                    self._syslog_buffer.append({
                        "node": "br-vlan",
                        "msg": "BR-VLAN: eth3 pvid restored to 100 - VLAN 100 active",
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
            return 0, "Bridge VLAN updated.", ""

        # ─── State Mutations: BFD Session ───
        if "bfd" in cmd_line:
            peer_ip = "172.16.12.2" if "172.16.12.2" in cmd_line else "172.16.23.1"
            bfd_peers = self._nodes[node].get("bfd", {}).get("peers", {})
            if "shutdown" in cmd_line and "no shutdown" not in cmd_line:
                if peer_ip in bfd_peers:
                    bfd_peers[peer_ip]["status"] = "Down"
                    self._syslog_buffer.append({
                        "node": node,
                        "msg": f"%BFD-5-STATE_CHANGE: BFD session to {peer_ip} Down",
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
                return 0, f"BFD peer {peer_ip} shutdown.", ""
            elif "no shutdown" in cmd_line:
                if peer_ip in bfd_peers:
                    bfd_peers[peer_ip]["status"] = "Up"
                    self._syslog_buffer.append({
                        "node": node,
                        "msg": f"%BFD-5-STATE_CHANGE: BFD session to {peer_ip} Up",
                        "time": datetime.now(timezone.utc).isoformat(),
                    })
                return 0, f"BFD peer {peer_ip} restored.", ""

        return 0, "OK", ""

    def get_logs(self, node: str, tail: int = 100) -> List[str]:
        matching = [entry["msg"] for entry in self._syslog_buffer if entry["node"] == node]
        return matching[-tail:]


# Global singleton instance of simulated lab provider
mock_clab_provider = ContainerlabMockProvider()


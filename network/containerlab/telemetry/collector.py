"""
collector.py — Live Telemetry & Evidence Collector for Containerlab Topology.

Collects structured FRR JSON outputs, Linux network states, and container syslogs across all nodes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from network.containerlab.runtime.driver import (
    execute_clab_command,
    get_clab_logs,
    VALID_LAB_NODES,
)

logger = logging.getLogger(__name__)


class LabObservationPayload:
    """
    Complete observational snapshot of the Containerlab topology at a specific timestamp.
    """

    def __init__(
        self,
        timestamp: datetime,
        bgp_state: Dict[str, Any],
        ospf_state: Dict[str, Any],
        bfd_state: Dict[str, Any],
        interfaces: Dict[str, Any],
        bridge_vlans: Dict[str, Any],
        routes: Dict[str, Any],
        ping_results: Dict[str, Any],
        syslog_lines: List[str],
    ) -> None:
        self.timestamp = timestamp
        self.bgp_state = bgp_state
        self.ospf_state = ospf_state
        self.bfd_state = bfd_state
        self.interfaces = interfaces
        self.bridge_vlans = bridge_vlans
        self.routes = routes
        self.ping_results = ping_results
        self.syslog_lines = syslog_lines

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "bgp_state": self.bgp_state,
            "ospf_state": self.ospf_state,
            "bfd_state": self.bfd_state,
            "interfaces": self.interfaces,
            "bridge_vlans": self.bridge_vlans,
            "routes": self.routes,
            "ping_results": self.ping_results,
            "syslog_lines_count": len(self.syslog_lines),
        }


class ClabTelemetryCollector:
    """
    Coordinates multi-protocol telemetry collection across FRR routers and Linux nodes.
    """

    def __init__(self, force_mock: bool = False) -> None:
        self.force_mock = force_mock

    def collect_topology_state(self) -> LabObservationPayload:
        now = datetime.now(timezone.utc)
        bgp_state: Dict[str, Any] = {}
        ospf_state: Dict[str, Any] = {}
        bfd_state: Dict[str, Any] = {}
        interfaces: Dict[str, Any] = {}
        routes: Dict[str, Any] = {}
        bridge_vlans: Dict[str, Any] = {}
        ping_results: Dict[str, Any] = {}
        syslog_lines: List[str] = []

        # 1. Query FRR Routers (R1, R2, R3)
        for r in ("R1", "R2", "R3"):
            # BGP summary
            code, out, _ = execute_clab_command(r, ["vtysh", "-c", "show ip bgp summary json"], force_mock=self.force_mock)
            if code == 0 and out.strip():
                try:
                    bgp_state[r] = json.loads(out)
                except Exception:
                    bgp_state[r] = {}

            # OSPF neighbors
            code, out, _ = execute_clab_command(r, ["vtysh", "-c", "show ip ospf neighbor json"], force_mock=self.force_mock)
            if code == 0 and out.strip():
                try:
                    ospf_state[r] = json.loads(out)
                except Exception:
                    ospf_state[r] = {}

            # BFD peers
            code, out, _ = execute_clab_command(r, ["vtysh", "-c", "show bfd peers json"], force_mock=self.force_mock)
            if code == 0 and out.strip():
                try:
                    bfd_state[r] = json.loads(out)
                except Exception:
                    bfd_state[r] = []

            # Interfaces
            code, out, _ = execute_clab_command(r, ["ip", "-j", "link"], force_mock=self.force_mock)
            if code == 0 and out.strip():
                try:
                    interfaces[r] = json.loads(out)
                except Exception:
                    interfaces[r] = []

            # Routes
            code, out, _ = execute_clab_command(r, ["vtysh", "-c", "show ip route json"], force_mock=self.force_mock)
            if code == 0 and out.strip():
                try:
                    routes[r] = json.loads(out)
                except Exception:
                    routes[r] = {}

            # Syslogs
            logs = get_clab_logs(r, tail=50, force_mock=self.force_mock)
            syslog_lines.extend(logs)

        # 2. Query br-vlan
        code, out, _ = execute_clab_command("br-vlan", ["bridge", "vlan", "show"], force_mock=self.force_mock)
        if code == 0 and out.strip():
            bridge_vlans["br-vlan"] = out

        # 3. Query client ping reachability
        code, out, _ = execute_clab_command("client1", ["ping", "-c", "2", "192.168.100.1"], force_mock=self.force_mock)
        ping_results["client1_to_gw"] = {
            "success": (code == 0),
            "output": out,
            "packet_loss": 0.0 if code == 0 else 100.0,
        }

        return LabObservationPayload(
            timestamp=now,
            bgp_state=bgp_state,
            ospf_state=ospf_state,
            bfd_state=bfd_state,
            interfaces=interfaces,
            bridge_vlans=bridge_vlans,
            routes=routes,
            ping_results=ping_results,
            syslog_lines=syslog_lines,
        )


# Global singleton instance
clab_telemetry_collector = ClabTelemetryCollector()


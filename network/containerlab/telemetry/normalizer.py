"""
normalizer.py — Normalizes Containerlab Observations into Canonical Incident Timeline.

Maps FRR JSON states and syslog events to StructuredEvent and IncidentTimeline contracts,
keeping lab experiments completely isolated from historical Cisco benchmarks.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services.ai.schemas.contracts import (
    EventType,
    IncidentStatus,
    IncidentTimeline,
    Severity,
    StructuredEvent,
    TimeWindow,
)
from .collector import LabObservationPayload

logger = logging.getLogger(__name__)


class ClabEvidenceNormalizer:
    """
    Transforms raw Containerlab multi-protocol observations into canonical StructuredEvents.
    """

    def normalize_observation(
        self,
        observation: LabObservationPayload,
        scenario_id: Optional[str] = None,
        incident_id: Optional[str] = None,
    ) -> IncidentTimeline:
        inc_id = incident_id or f"inc_clab_{uuid.uuid4().hex[:10]}"
        now = observation.timestamp
        events: List[StructuredEvent] = []
        affected_devices: set[str] = set()
        affected_interfaces: set[str] = set()
        suspected_protocols: set[str] = set()

        # ─── 1. BGP Events ───
        for router, binfo in observation.bgp_state.items():
            peers = binfo.get("peers", {})
            for peer_ip, pdata in peers.items():
                state = pdata.get("state", "Established")
                if state in ("Idle", "Active", "Connect", "Down"):
                    affected_devices.add(router)
                    affected_interfaces.add(peer_ip)
                    suspected_protocols.add("bgp")
                    events.append(StructuredEvent(
                        event_id=f"evt_bgp_{uuid.uuid4().hex[:8]}",
                        timestamp=now,
                        device_id=router,
                        interface=peer_ip,
                        event_type=EventType.BGP_NEIGHBOR_DOWN,
                        severity=Severity.HIGH,
                        normalized_fields={
                            "peer_ip": peer_ip,
                            "remote_as": pdata.get("remoteAs"),
                            "state": state,
                            "pfx_rcvd": pdata.get("pfxRcvd", 0),
                            "scenario_id": scenario_id or "unknown",
                        },
                        raw_reference=f"clab-{router}:vtysh_bgp_summary",
                    ))

        # ─── 2. OSPF Events ───
        for router, oinfo in observation.ospf_state.items():
            nbrs = oinfo.get("neighbors", {})
            for ifname, nlist in nbrs.items():
                for nentry in nlist:
                    state = nentry.get("nbrState", "Full")
                    if state in ("Down", "Init", "2-Way", "ExStart", "Exchange", "Loading"):
                        affected_devices.add(router)
                        affected_interfaces.add(ifname)
                        suspected_protocols.add("ospf")
                        events.append(StructuredEvent(
                            event_id=f"evt_ospf_{uuid.uuid4().hex[:8]}",
                            timestamp=now,
                            device_id=router,
                            interface=ifname,
                            event_type=EventType.OSPF_ADJACENCY_FAILURE,
                            severity=Severity.HIGH,
                            normalized_fields={
                                "neighbor_id": nentry.get("nbrId"),
                                "neighbor_ip": nentry.get("ip"),
                                "state": state,
                                "interface": ifname,
                                "scenario_id": scenario_id or "unknown",
                            },
                            raw_reference=f"clab-{router}:vtysh_ospf_neighbor",
                        ))

        # ─── 3. BFD Events ───
        for router, bfd_list in observation.bfd_state.items():
            for bentry in bfd_list:
                status = bentry.get("status", "Up")
                if status in ("Down", "AdminDown"):
                    peer_ip = bentry.get("peer", "unknown")
                    affected_devices.add(router)
                    affected_interfaces.add(peer_ip)
                    suspected_protocols.add("bfd")
                    events.append(StructuredEvent(
                        event_id=f"evt_bfd_{uuid.uuid4().hex[:8]}",
                        timestamp=now,
                        device_id=router,
                        interface=peer_ip,
                        event_type=EventType.PORT_DOWN,
                        severity=Severity.HIGH,
                        normalized_fields={
                            "peer_ip": peer_ip,
                            "status": status,
                            "protocol": "bfd",
                            "scenario_id": scenario_id or "unknown",
                        },
                        raw_reference=f"clab-{router}:vtysh_bfd_peers",
                    ))

        # ─── 4. Interface State Events ───
        for router, if_list in observation.interfaces.items():
            for iface in if_list:
                oper = iface.get("operstate", "UP")
                admin = iface.get("adminstate", "UP")
                ifname = iface.get("ifname", "")
                if oper in ("DOWN", "LOWERLAYERDOWN") or admin == "DOWN":
                    affected_devices.add(router)
                    affected_interfaces.add(ifname)
                    suspected_protocols.add("interface")
                    ev_type = EventType.PORT_ADMIN_SHUTDOWN if admin == "DOWN" else EventType.PORT_DOWN
                    events.append(StructuredEvent(
                        event_id=f"evt_if_{uuid.uuid4().hex[:8]}",
                        timestamp=now,
                        device_id=router,
                        interface=ifname,
                        event_type=ev_type,
                        severity=Severity.HIGH,
                        normalized_fields={
                            "ifname": ifname,
                            "operstate": oper,
                            "adminstate": admin,
                            "scenario_id": scenario_id or "unknown",
                        },
                        raw_reference=f"clab-{router}:ip_link",
                    ))

        # ─── 5. Bridge & VLAN Events ───
        br_output = observation.bridge_vlans.get("br-vlan", "")
        if "200 PVID" in br_output or "200 pvid" in br_output:
            affected_devices.add("br-vlan")
            affected_interfaces.add("eth3")
            suspected_protocols.add("vlan")
            events.append(StructuredEvent(
                event_id=f"evt_vlan_{uuid.uuid4().hex[:8]}",
                timestamp=now,
                device_id="br-vlan",
                interface="eth3",
                event_type=EventType.VLAN_FAULT,
                severity=Severity.HIGH,
                normalized_fields={
                    "bridge": "br0",
                    "interface": "eth3",
                    "observed_pvid": 200,
                    "expected_pvid": 100,
                    "scenario_id": scenario_id or "unknown",
                },
                raw_reference="clab-br-vlan:bridge_vlan_show",
            ))

        # Ping failure
        ping_c1 = observation.ping_results.get("client1_to_gw", {})
        if ping_c1.get("packet_loss", 0.0) >= 50.0:
            affected_devices.add("client1")
            suspected_protocols.add("vlan")
            events.append(StructuredEvent(
                event_id=f"evt_ping_{uuid.uuid4().hex[:8]}",
                timestamp=now,
                device_id="client1",
                interface="eth1",
                event_type=EventType.CONNECTIVITY_FAULT,
                severity=Severity.CRITICAL,
                normalized_fields={
                    "source": "client1",
                    "target": "192.168.100.1",
                    "packet_loss_percent": ping_c1.get("packet_loss", 100.0),
                    "scenario_id": scenario_id or "unknown",
                },
                raw_reference="clab-client1:ping",
            ))

        # If zero events detected, create baseline notice
        if not events:
            events.append(StructuredEvent(
                event_id=f"evt_info_{uuid.uuid4().hex[:8]}",
                timestamp=now,
                device_id="R1",
                interface="lo",
                event_type=EventType.UNKNOWN,
                severity=Severity.INFO,
                normalized_fields={"status": "baseline_healthy"},
                raw_reference="clab-telemetry:baseline",
            ))
            affected_devices.add("R1")

        start_time = now - timedelta(seconds=60)
        end_time = now + timedelta(seconds=10)

        return IncidentTimeline(
            incident_id=inc_id,
            time_window=TimeWindow(start=start_time, end=end_time),
            events=events,
            affected_devices=sorted(list(affected_devices)),
            affected_interfaces=sorted(list(affected_interfaces)),
            suspected_protocols=sorted(list(suspected_protocols)),
            status=IncidentStatus.OPEN,
        )


# Global singleton instance
clab_evidence_normalizer = ClabEvidenceNormalizer()


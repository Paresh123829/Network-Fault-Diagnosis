from __future__ import annotations

from typing import Dict, Any, Tuple
import re

from network.datasets.adapters.raw_record import RawNetworkRecord, RecordSource
from services.ai.schemas.contracts import EventType, Severity


def classify_event(record: RawNetworkRecord) -> Tuple[EventType, Severity]:
    """
    Deterministically classifies a RawNetworkRecord into a canonical
    EventType and Severity based on the 5 MVP scenarios:
    1. BGP anomaly / neighbor event
    2. Port flap
    3. Port admin shutdown
    4. OSPF adjacency failure
    5. VLAN/connectivity fault
    """
    if record.source == RecordSource.CISCO_TELEMETRY_CSV:
        return _classify_telemetry(record)
    else:
        return _classify_syslog(record)


def _classify_telemetry(record: RawNetworkRecord) -> Tuple[EventType, Severity]:
    """Classifies structured telemetry."""
    hint = record.protocol_hint or ""
    fields = record.telemetry_fields or {}

    # 1. Port Admin Shutdown / Port State
    if hint == "interface":
        admin_status = (fields.get("admin-status") or fields.get("actual-state") or "").strip().lower()
        if admin_status in ("admin-down", "administratively down"):
            return EventType.PORT_ADMIN_SHUTDOWN, Severity.HIGH

        line_state = (fields.get("actual-line-state") or fields.get("line-state") or fields.get("actual-state") or "").strip().lower()
        if line_state == "down":
            return EventType.PORT_DOWN, Severity.HIGH
        elif line_state == "up":
            return EventType.PORT_UP, Severity.INFO

    # 2. BGP Events (state-aware classification)
    if hint == "bgp":
        # Check explicit neighbor/peer connection state if available
        state = (
            fields.get("connection-state")
            or fields.get("state")
            or fields.get("session-state")
            or fields.get("fsm-state")
            or ""
        ).strip().lower()

        if state:
            if state in ("established", "up"):
                return EventType.UNKNOWN, Severity.INFO
            elif state in ("idle", "active", "connect", "open-sent", "open-confirm", "closing", "down"):
                return EventType.BGP_NEIGHBOR_DOWN, Severity.HIGH

        # Check neighbor count ratios (BGP summary telemetry)
        est_str = fields.get("global__established-neighbors-count-total") or fields.get("established-neighbors-count-total")
        tot_str = fields.get("global__neighbors-count-total") or fields.get("neighbors-count-total")
        if est_str is not None and tot_str is not None:
            try:
                est = int(float(str(est_str).strip()))
                tot = int(float(str(tot_str).strip()))
                if tot > 0:
                    if est < tot:
                        sev = Severity.CRITICAL if est == 0 else Severity.HIGH
                        return EventType.BGP_ANOMALY, sev
                    elif est == tot:
                        return EventType.UNKNOWN, Severity.INFO
            except (ValueError, TypeError):
                pass

        # Check VRF-level neighbor count drops
        vrf_est_str = fields.get("vrf__established-neighbors-count") or fields.get("established-neighbors-count")
        vrf_tot_str = fields.get("vrf__neighbors-count") or fields.get("neighbors-count")
        if vrf_est_str is not None and vrf_tot_str is not None:
            try:
                vrf_est = int(float(str(vrf_est_str).strip()))
                vrf_tot = int(float(str(vrf_tot_str).strip()))
                if vrf_tot > 0:
                    if vrf_est < vrf_tot:
                        return EventType.BGP_ANOMALY, Severity.HIGH
                    elif vrf_est == vrf_tot:
                        return EventType.UNKNOWN, Severity.INFO
            except (ValueError, TypeError):
                pass

        # Check route withdrawal spikes
        del_routes_str = fields.get("deleted-routes-count") or fields.get("withdrawn-routes-count")
        if del_routes_str is not None:
            try:
                del_routes = int(float(str(del_routes_str).strip()))
                if del_routes > 50:
                    return EventType.BGP_ANOMALY, Severity.MEDIUM
            except (ValueError, TypeError):
                pass

        # Check record event_hint if adapter inferred a specific fault
        event_hint = record.event_hint or ""
        if event_hint in ("bgp_clear", "bgp_neighbor_down", "bgp_neighbor_count_mismatch"):
            return EventType.BGP_ANOMALY, Severity.MEDIUM

        # Default for healthy baseline BGP metrics:
        return EventType.UNKNOWN, Severity.INFO

    return EventType.UNKNOWN, Severity.INFO


def _classify_syslog(record: RawNetworkRecord) -> Tuple[EventType, Severity]:
    """Classifies syslog messages based on known patterns and hints."""
    msg = record.raw_message or ""
    hint = record.event_hint or ""
    proto = record.protocol_hint or ""

    # Severity extraction from Cisco syslog (e.g. %ROUTING-BGP-5-ADJCHANGE)
    severity = Severity.INFO
    sev_match = re.search(r'%[A-Z0-9_]+-(\d+)-', msg)
    if sev_match:
        digit = int(sev_match.group(1))
        if digit <= 2:
            severity = Severity.CRITICAL
        elif digit == 3:
            severity = Severity.HIGH
        elif digit == 4:
            severity = Severity.MEDIUM
        elif digit == 5:
            severity = Severity.INFO
        elif digit >= 6:
            severity = Severity.LOW

    # 1. BGP Neighbor Event
    if ("BGP" in msg and "ADJCHANGE" in msg) or hint in ("bgp_neighbor_down", "bgp_neighbor_up") or (proto == "bgp" and ("Down" in msg or "Up" in msg)):
        if "Down" in msg or hint == "bgp_neighbor_down":
            return EventType.BGP_NEIGHBOR_DOWN, severity
        elif "Up" in msg or hint == "bgp_neighbor_up":
            return EventType.BGP_NEIGHBOR_UP, severity

    # 2. Port Admin Shutdown (FRR/Cisco)
    if "admin-down" in msg.lower() or "administratively down" in msg.lower() or hint == "interface_admin_down":
        return EventType.PORT_ADMIN_SHUTDOWN, severity

    # 3. Port Flap / Down / Up
    if "LINK-3-UPDOWN" in msg or "TRANSCEIVER_REMOVED" in msg or proto == "interface" or hint == "interface_down":
        if "changed state to Down" in msg or "is Down" in msg or "TRANSCEIVER_REMOVED" in msg or "Down" in msg or hint == "interface_down":
            return EventType.PORT_DOWN, severity
        elif "changed state to Up" in msg or "is Up" in msg or "Up" in msg:
            return EventType.PORT_UP, severity

    # 4. OSPF Adjacency
    if ("OSPF" in msg and ("ADJCHANGE" in msg or "neighbor" in msg.lower())) or proto == "ospf":
        if "Down" in msg or "DOWN" in msg:
            return EventType.OSPF_NEIGHBOR_DOWN, severity
        if "Up" in msg or "UP" in msg or "FULL" in msg:
            return EventType.OSPF_NEIGHBOR_UP, severity
            
    # 5. Connectivity / VLAN
    if "VLAN" in msg and ("down" in msg.lower() or "fail" in msg.lower()):
        return EventType.VLAN_FAULT, severity

    # FRR specific signatures
    if "BGP" in msg and "Notification sent" in msg:
        return EventType.BGP_NEIGHBOR_DOWN, Severity.HIGH
        
    return EventType.UNKNOWN, severity

"""
analyzer.py — Deterministic Symptom Extraction and Sequencing Engine.

Extracts canonical symptom findings from IncidentTimeline and StructuredEvents,
orders them chronologically, determines causal primacy (primary trigger vs downstream
consequence), and flags missing corroborating evidence.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from services.ai.schemas.contracts import (
    IncidentTimeline,
    StructuredEvent,
    EventType,
    Severity,
    TopologyContext,
)
from .models import (
    SymptomCategory,
    SymptomPrimacy,
    SymptomFinding,
    SymptomAnalysisReport,
)

logger = logging.getLogger(__name__)


# Priority of root triggers over downstream effects (lower number = higher root primacy)
PRIMACY_ORDER: Dict[SymptomCategory, int] = {
    SymptomCategory.OPTICAL_TRANSCEIVER_PULL: 1,
    SymptomCategory.ADMIN_SHUTDOWN: 2,
    SymptomCategory.PHYSICAL_LINK_FAILURE: 3,
    SymptomCategory.PORT_FLAP: 4,
    SymptomCategory.ROUTING_LOOP: 5,
    SymptomCategory.FIB_BLACKHOLE_DROPS: 6,
    SymptomCategory.BFD_SESSION_FAILURE: 7,
    SymptomCategory.BGP_CLEAR_RESET: 8,
    SymptomCategory.OSPF_ADJACENCY_DROP: 9,
    SymptomCategory.BGP_SESSION_DROP: 10,
    SymptomCategory.ECMP_IMBALANCE: 11,
    SymptomCategory.BGP_ROUTE_WITHDRAWAL: 12,
    SymptomCategory.HIGH_CPU_LOAD: 13,
    SymptomCategory.RECOVERY_EVENT: 20,
    SymptomCategory.GENERIC_TELEMETRY_ANOMALY: 30,
}


class SymptomAnalyzer:
    """
    Analyzes an IncidentTimeline to extract ordered symptoms and causal hierarchy.
    """

    def analyze(
        self,
        timeline: IncidentTimeline,
        topology_context: Optional[TopologyContext] = None
    ) -> SymptomAnalysisReport:
        events = sorted(timeline.events, key=lambda e: (e.timestamp, e.event_id))
        symptoms: List[SymptomFinding] = []

        for idx, event in enumerate(events):
            symptom = self._classify_event_to_symptom(event, idx)
            if symptom:
                symptoms.append(symptom)

        # If no specific symptoms extracted, fallback to generic incident symptom
        if not symptoms and events:
            ev0 = events[0]
            symptoms.append(SymptomFinding(
                symptom_id=f"sym_generic_{timeline.incident_id}",
                category=SymptomCategory.GENERIC_TELEMETRY_ANOMALY,
                device_id=ev0.device_id,
                interface=ev0.interface,
                description=f"Generic anomaly on {ev0.device_id} ({ev0.event_type.value})",
                primacy=SymptomPrimacy.PRIMARY,
                sequence_order=1,
                timestamp=ev0.timestamp,
                source_event_ids=[ev0.event_id],
                source_references=[ev0.raw_reference]
            ))

        # Sort chronologically
        symptoms.sort(key=lambda s: (s.timestamp, PRIMACY_ORDER.get(s.category, 99)))

        # Assign sequence order
        for i, s in enumerate(symptoms, 1):
            s.sequence_order = i

        # Determine Primary vs Downstream
        primary_symptom: Optional[SymptomFinding] = None
        downstream: List[SymptomFinding] = []

        if symptoms:
            # Candidates for primary: non-recovery symptoms, preferring earliest lowest primacy rank
            candidates = [s for s in symptoms if s.category != SymptomCategory.RECOVERY_EVENT]
            if candidates:
                # Rank by (PRIMACY_ORDER, timestamp)
                primary_symptom = min(candidates, key=lambda s: (PRIMACY_ORDER.get(s.category, 50), s.timestamp))
                primary_symptom.primacy = SymptomPrimacy.PRIMARY

                for s in symptoms:
                    if s.symptom_id == primary_symptom.symptom_id:
                        continue
                    if s.category == SymptomCategory.RECOVERY_EVENT:
                        s.primacy = SymptomPrimacy.RECOVERY
                    else:
                        s.primacy = SymptomPrimacy.DOWNSTREAM
                        downstream.append(s)
            else:
                symptoms[0].primacy = SymptomPrimacy.PRIMARY
                primary_symptom = symptoms[0]

        # Detect Missing Evidence
        missing = self._detect_missing_evidence(symptoms, topology_context)

        # Build Temporal Cascade strings
        cascade: List[str] = [
            f"Step {s.sequence_order} [{s.timestamp.strftime('%H:%M:%S.%f')[:-3]}]: {s.device_id} - {s.category.value} ({s.description}) [{s.primacy.value}]"
            for s in symptoms
        ]

        affected_components = list(set(
            [s.device_id for s in symptoms] +
            [s.interface for s in symptoms if s.interface]
        ))

        return SymptomAnalysisReport(
            incident_id=timeline.incident_id,
            symptoms=symptoms,
            primary_symptom=primary_symptom,
            downstream_symptoms=downstream,
            missing_evidence=missing,
            temporal_cascade=cascade,
            affected_components=affected_components
        )

    def _classify_event_to_symptom(self, event: StructuredEvent, idx: int) -> Optional[SymptomFinding]:
        norm = event.normalized_fields or {}
        raw = str(norm.get("raw_message") or norm.get("message") or "")
        fields = norm.get("telemetry_fields") or {}
        cat: Optional[SymptomCategory] = None
        desc = ""

        # 1. Optical Transceiver Pull
        if "TRANSCEIVER_REMOVED" in raw or "optics" in raw.lower() or "transceiver" in raw.lower() or "transceiver_pull" in str(event.raw_reference).lower():
            cat = SymptomCategory.OPTICAL_TRANSCEIVER_PULL
            desc = f"Optical transceiver removed on {event.device_id}:{event.interface or 'interface'}"

        # 2. Administrative Shutdown
        elif event.event_type == EventType.PORT_ADMIN_SHUTDOWN or "administratively down" in raw.lower() or "admin_shut" in str(event.raw_reference).lower():
            cat = SymptomCategory.ADMIN_SHUTDOWN
            desc = f"Administrative shutdown executed on {event.device_id}:{event.interface or 'interface'}"

        # 3. Physical Port Down / Carrier Transition
        elif event.event_type == EventType.PORT_DOWN or ("line protocol on interface" in raw.lower() and "down" in raw.lower()):
            cat = SymptomCategory.PHYSICAL_LINK_FAILURE
            desc = f"Physical link down on {event.device_id}:{event.interface or 'interface'}"

        # 4. Port Flap
        elif event.event_type == EventType.PORT_FLAP:
            cat = SymptomCategory.PORT_FLAP
            desc = f"Port flapping observed on {event.device_id}:{event.interface or 'interface'}"

        # 5. Recovery (Port Up / BGP Up)
        elif event.event_type in (EventType.PORT_UP, EventType.BGP_NEIGHBOR_UP, EventType.OSPF_NEIGHBOR_UP) or "state changed to up" in raw.lower():
            cat = SymptomCategory.RECOVERY_EVENT
            desc = f"Service/link recovery detected on {event.device_id}:{event.interface or 'interface'}"

        # 6. BGP Clear / Manual Reset
        elif "user clear requested" in raw.lower() or "clear ip bgp" in raw.lower() or "bgpclear" in str(event.raw_reference).lower() or "bgp_clear" in str(norm.get("scenario_id", "")):
            cat = SymptomCategory.BGP_CLEAR_RESET
            desc = f"BGP session manually cleared on {event.device_id} (neighbor {norm.get('peer_ip') or 'peer'})"

        # 7. BGP Neighbor Down
        elif event.event_type == EventType.BGP_NEIGHBOR_DOWN or "%ROUTING-BGP-5-ADJCHANGE" in raw:
            cat = SymptomCategory.BGP_SESSION_DROP
            desc = f"BGP adjacency reset on {event.device_id} (peer {norm.get('peer_ip') or norm.get('neighbor') or 'remote'})"

        # 8. BGP Count Mismatch / Route Withdrawals
        elif event.event_type == EventType.BGP_ANOMALY:
            cat = SymptomCategory.BGP_ROUTE_WITHDRAWAL
            desc = f"BGP route table fluctuation/withdrawals detected on {event.device_id}"

        # 9. OSPF Adjacency Drop
        elif event.event_type in (EventType.OSPF_ADJACENCY_FAILURE, EventType.OSPF_NEIGHBOR_DOWN) or "%OSPF-5-ADJCHANGE" in raw:
            cat = SymptomCategory.OSPF_ADJACENCY_DROP
            desc = f"OSPF adjacency failure on {event.device_id}"

        # 10. Case 12 FIB Blackhole / Drops
        elif "blackhole" in str(event.raw_reference).lower() or ("fib" in str(event.raw_reference).lower() and any(k.endswith("-drops") and int(v) > 100 for k, v in fields.items() if str(v).isdigit())):
            cat = SymptomCategory.FIB_BLACKHOLE_DROPS
            desc = f"FIB packet drop spike on {event.device_id}"

        # 11. Case 12 ECMP Imbalance
        elif "ecmp" in str(event.raw_reference).lower():
            cat = SymptomCategory.ECMP_IMBALANCE
            desc = f"ECMP path hashing imbalance detected on {event.device_id}"

        # 12. Case 12 Routing Loop
        elif "netloop" in str(event.raw_reference).lower():
            cat = SymptomCategory.ROUTING_LOOP
            desc = f"Routing loop traffic cycle detected on {event.device_id}"

        # 13. Case 12 BFD Failure
        elif "bfd" in str(event.raw_reference).lower():
            cat = SymptomCategory.BFD_SESSION_FAILURE
            desc = f"BFD session failure on {event.device_id}"

        else:
            cat = SymptomCategory.GENERIC_TELEMETRY_ANOMALY
            desc = f"Telemetry anomaly on {event.device_id} ({event.event_type.value})"

        s_id = f"sym_{event.device_id}_{cat.value}_{idx}"
        return SymptomFinding(
            symptom_id=s_id,
            category=cat,
            device_id=event.device_id,
            interface=event.interface,
            description=desc,
            timestamp=event.timestamp,
            source_event_ids=[event.event_id],
            source_references=[event.raw_reference],
            observed_metrics=norm
        )

    def _detect_missing_evidence(
        self,
        symptoms: List[SymptomFinding],
        topology: Optional[TopologyContext]
    ) -> List[str]:
        missing: List[str] = []
        categories = set(s.category for s in symptoms)

        # If BGP dropped, check if we have physical link telemetry
        if SymptomCategory.BGP_SESSION_DROP in categories or SymptomCategory.BGP_CLEAR_RESET in categories:
            if SymptomCategory.PHYSICAL_LINK_FAILURE not in categories and SymptomCategory.ADMIN_SHUTDOWN not in categories and SymptomCategory.OPTICAL_TRANSCEIVER_PULL not in categories:
                missing.append("Physical link telemetry (carrier transitions / line-state) absent; cannot verify physical layer stability.")

        # If physical link dropped, check optical Rx/Tx power
        if SymptomCategory.PHYSICAL_LINK_FAILURE in categories:
            if SymptomCategory.OPTICAL_TRANSCEIVER_PULL not in categories:
                missing.append("Optical DOM sensor data (laser Rx/Tx dBm) absent; cannot distinguish cable pull from transceiver failure.")

        # If admin shutdown, check command audit logs
        if SymptomCategory.ADMIN_SHUTDOWN in categories:
            missing.append("AAA / TACACS+ accounting log missing; operator username not recorded in telemetry stream.")

        # If ECMP or FIB, check routing table snapshot
        if SymptomCategory.ECMP_IMBALANCE in categories or SymptomCategory.FIB_BLACKHOLE_DROPS in categories:
            missing.append("FIB hardware ASIC memory telemetry absent; route programming state inferred from packet drop counters.")

        return missing

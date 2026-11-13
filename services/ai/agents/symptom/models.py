"""
models.py — Data Contracts for Symptom Contextualization.

Defines structured symptom findings, category enums, primacy classifications,
and temporal sequence ordering.
"""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SymptomCategory(str, Enum):
    OPTICAL_TRANSCEIVER_PULL = "optical_transceiver_pull"
    ADMIN_SHUTDOWN = "admin_shutdown"
    PHYSICAL_LINK_FAILURE = "physical_link_failure"
    PORT_FLAP = "port_flap"
    BGP_SESSION_DROP = "bgp_session_drop"
    BGP_CLEAR_RESET = "bgp_clear_reset"
    BGP_ROUTE_WITHDRAWAL = "bgp_route_withdrawal"
    OSPF_ADJACENCY_DROP = "ospf_adjacency_drop"
    ECMP_IMBALANCE = "ecmp_imbalance"
    FIB_BLACKHOLE_DROPS = "fib_blackhole_drops"
    ROUTING_LOOP = "routing_loop"
    BFD_SESSION_FAILURE = "bfd_session_failure"
    HIGH_CPU_LOAD = "high_cpu_load"
    RECOVERY_EVENT = "recovery_event"
    GENERIC_TELEMETRY_ANOMALY = "generic_telemetry_anomaly"


class SymptomPrimacy(str, Enum):
    PRIMARY = "primary"            # Root initiating trigger (e.g. optics pull, admin shut)
    DOWNSTREAM = "downstream"      # Cascading consequence (e.g. BFD drop, BGP down, route withdrawal)
    RECOVERY = "recovery"          # Fault resolution (e.g. link up, BGP established)
    INCONCLUSIVE = "inconclusive"


class SymptomFinding(BaseModel):
    symptom_id: str
    category: SymptomCategory
    device_id: str
    interface: Optional[str] = None
    description: str
    primacy: SymptomPrimacy = SymptomPrimacy.INCONCLUSIVE
    sequence_order: int = 0
    timestamp: datetime
    source_event_ids: List[str] = Field(default_factory=list)
    source_references: List[str] = Field(default_factory=list)
    observed_metrics: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class SymptomAnalysisReport(BaseModel):
    incident_id: str
    symptoms: List[SymptomFinding] = Field(default_factory=list)
    primary_symptom: Optional[SymptomFinding] = None
    downstream_symptoms: List[SymptomFinding] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    temporal_cascade: List[str] = Field(default_factory=list)
    affected_components: List[str] = Field(default_factory=list)


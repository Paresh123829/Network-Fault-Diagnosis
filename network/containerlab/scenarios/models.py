"""
models.py — Strongly Typed Data Contracts for Containerlab Fault Scenarios.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from services.ai.schemas.contracts import EventType, Severity


class FaultProtocol(str, Enum):
    BGP = "bgp"
    OSPF = "ospf"
    VLAN = "vlan"
    INTERFACE = "interface"
    BFD = "bfd"


class ScenarioPrecondition(BaseModel):
    check_type: str = Field(..., description="Type of check: bgp_neighbor, ospf_neighbor, interface_state, vlan_ping, bfd_peer")
    target_node: str
    target_identifier: str
    expected_value: Any


class ExpectedSymptom(BaseModel):
    event_type: EventType
    severity: Severity
    description: str
    syslog_pattern: Optional[str] = None


class ExpectedDiagnosis(BaseModel):
    expected_root_cause: str
    expected_device: str
    expected_component: Optional[str] = None
    expected_protocol: str


class RecoveryActionDefinition(BaseModel):
    operation: str
    parameters: Dict[str, Any]
    target_node: str
    is_compensating: bool = False


class VerificationCriteria(BaseModel):
    protocol: FaultProtocol
    target_node: str
    target_identifier: str
    expected_state: str
    expected_routes: List[str] = Field(default_factory=list)
    ping_target: Optional[str] = None
    max_packet_loss_percent: float = 0.0


class ScenarioDefinition(BaseModel):
    """
    Complete, deterministic declaration of a network fault scenario.
    """
    scenario_id: str
    name: str
    description: str
    protocol: FaultProtocol
    target_node: str
    target_component: str
    preconditions: List[ScenarioPrecondition]
    fault_operation: str
    fault_parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_symptoms: List[ExpectedSymptom]
    expected_diagnosis: ExpectedDiagnosis
    recovery_action: RecoveryActionDefinition
    verification_criteria: VerificationCriteria
    timeout_seconds: float = 30.0


class ScenarioRunResult(BaseModel):
    """
    Result of a single execution run of a scenario.
    """
    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:10]}")
    scenario_id: str
    run_index: int
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    # Step-by-step verification flags
    baseline_healthy: bool = False
    fault_injection_success: bool = False
    fault_observed: bool = False
    incident_created: bool = False
    diagnosis_produced: bool = False
    rca_matched: bool = False
    device_matched: bool = False
    protocol_matched: bool = False
    evidence_grounded: bool = False
    remediation_proposed: bool = False
    approval_required: bool = True
    approval_granted: bool = False
    remediation_executed: bool = False
    independently_verified: bool = False
    recovered: bool = False
    rollback_triggered: bool = False
    rollback_successful: bool = False

    # Timing metrics
    time_to_detect_ms: float = 0.0
    time_to_diagnose_ms: float = 0.0
    time_to_remediate_ms: float = 0.0
    time_to_recover_ms: float = 0.0
    duration_ms: float = 0.0

    raw_evidence: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


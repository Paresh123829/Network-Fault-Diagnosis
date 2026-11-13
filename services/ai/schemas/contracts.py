"""
contracts.py — Canonical inter-agent data contracts for the
Multi-Agent AI Framework for Intelligent Network Fault Diagnosis.

All agents produce and consume instances of these Pydantic models.
Any change to a contract field must be reflected in all agents that
read or write that field, and in the corresponding JSON Schema under
database/schemas/.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────
# Shared Enumerations
# ─────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EventType(str, Enum):
    BGP_NEIGHBOR_DOWN = "bgp_neighbor_down"
    BGP_NEIGHBOR_UP = "bgp_neighbor_up"
    BGP_ANOMALY = "bgp_anomaly"
    PORT_FLAP = "port_flap"
    PORT_DOWN = "port_down"
    PORT_UP = "port_up"
    PORT_ADMIN_SHUTDOWN = "port_admin_shutdown"
    OSPF_NEIGHBOR_DOWN = "ospf_neighbor_down"
    OSPF_NEIGHBOR_UP = "ospf_neighbor_up"
    OSPF_ADJACENCY_FAILURE = "ospf_adjacency_failure"
    VLAN_FAULT = "vlan_fault"
    CONNECTIVITY_FAULT = "connectivity_fault"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewerAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    REQUEST_MORE_DIAGNOSIS = "request_more_diagnosis"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_DIAGNOSIS = "needs_more_diagnosis"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REVOKED = "revoked"


class PolicyStatus(str, Enum):
    ALLOWED_FOR_REVIEW = "allowed_for_review"
    REJECTED_UNKNOWN_OPERATION = "rejected_unknown_operation"
    REJECTED_INVALID_PARAMETERS = "rejected_invalid_parameters"
    REJECTED_UNKNOWN_TARGET = "rejected_unknown_target"
    REJECTED_INVALID_TOPOLOGY = "rejected_invalid_topology"
    REJECTED_INSUFFICIENT_EVIDENCE = "rejected_insufficient_evidence"
    REJECTED_UNSAFE_OPERATION = "rejected_unsafe_operation"
    REJECTED_EXPIRED_PROPOSAL = "rejected_expired_proposal"
    REJECTED_KILL_SWITCH_ACTIVE = "rejected_kill_switch_active"
    REJECTED_INVALID_STATE = "rejected_invalid_state"


class ReviewerRole(str, Enum):
    NOC_ENGINEER = "noc_engineer"
    NETWORK_OPERATOR = "network_operator"
    SITE_RELIABILITY_ENGINEER = "site_reliability_engineer"
    ADMINISTRATOR = "administrator"
    AUTOMATION_SYSTEM = "automation_system"


class ExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VerificationStatus(str, Enum):
    NOT_VERIFIED = "not_verified"
    VERIFIED_RECOVERED = "verified_recovered"
    PARTIALLY_RECOVERED = "partially_recovered"
    RECOVERY_FAILED = "recovery_failed"
    UNKNOWN = "unknown"


class RollbackStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


class RemediationStatus(str, Enum):
    PROPOSED = "proposed"
    POLICY_REJECTED = "policy_rejected"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXECUTING = "executing"
    EXECUTION_FAILED = "execution_failed"
    VERIFYING = "verifying"
    RECOVERED = "recovered"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    ESCALATED_MANUAL_INTERVENTION = "escalated_manual_intervention"


class IncidentStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


# ─────────────────────────────────────────────
# AGENT 1 OUTPUT — StructuredEvent
# ─────────────────────────────────────────────

class StructuredEvent(BaseModel):
    """
    Output of the Ingestion Agent.
    Represents a single normalized network event.
    """
    event_id: str = Field(..., description="Unique event identifier (UUID or hash-based)")
    timestamp: datetime = Field(..., description="Normalized UTC timestamp")
    device_id: str = Field(..., description="Normalized device identifier")
    interface: Optional[str] = Field(None, description="Affected interface, if applicable")
    event_type: EventType = Field(..., description="Normalized event type")
    severity: Severity = Field(..., description="Normalized severity level")
    normalized_fields: Dict[str, Any] = Field(
        default_factory=dict,
        description="Protocol/event-specific normalized key-value pairs"
    )
    raw_reference: str = Field(
        ...,
        description="Reference to the original raw record (ID, filename, line number)"
    )

    @field_validator("device_id")
    @classmethod
    def device_id_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("device_id must not be empty or whitespace")
        return v.strip()


# ─────────────────────────────────────────────
# AGENT 2 OUTPUT — IncidentTimeline
# ─────────────────────────────────────────────

class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class IncidentTimeline(BaseModel):
    """
    Output of the Correlation Agent.
    Groups related StructuredEvents into a single incident.
    """
    incident_id: str = Field(..., description="Unique incident identifier")
    time_window: TimeWindow = Field(..., description="Start and end of the incident window")
    events: List[StructuredEvent] = Field(..., description="Ordered list of correlated events")
    affected_devices: List[str] = Field(..., description="Distinct device IDs involved")
    affected_interfaces: List[str] = Field(
        default_factory=list,
        description="Distinct interfaces involved"
    )
    suspected_protocols: List[str] = Field(
        default_factory=list,
        description="Protocols suspected to be involved (e.g., bgp, ospf, vlan)"
    )
    status: IncidentStatus = Field(
        default=IncidentStatus.OPEN,
        description="Lifecycle status of the incident"
    )
    correlation_reason: str = Field(
        default="",
        description="Deterministic explanation of why these events were grouped"
    )
    case_id: Optional[str] = Field(
        default=None,
        description="Originating dataset case identifier (e.g. '2', '3', '4')"
    )
    experiment_id: Optional[str] = Field(
        default=None,
        description="Originating experiment run identifier"
    )


# ─────────────────────────────────────────────
# AGENT 3 OUTPUT — TopologyContext
# ─────────────────────────────────────────────

class TopologyNode(BaseModel):
    node_id: str
    node_type: str = Field(..., description="e.g., router, switch, host")
    attributes: Dict[str, Any] = Field(default_factory=dict)


class TopologyLink(BaseModel):
    source: str = Field(..., description="Source node_id")
    target: str = Field(..., description="Target node_id")
    interface_source: Optional[str] = None
    interface_target: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class TopologyContext(BaseModel):
    """
    Output of the Topology Agent.
    Provides the network graph context around the incident.
    """
    nodes: List[TopologyNode] = Field(..., description="All nodes relevant to the incident")
    links: List[TopologyLink] = Field(..., description="All links between relevant nodes")
    affected_path: List[str] = Field(
        default_factory=list,
        description="Ordered list of node_ids on the affected path"
    )
    neighbors: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Adjacency map: node_id → [neighbor_node_ids]"
    )
    protocol_relationships: Dict[str, Any] = Field(
        default_factory=dict,
        description="Protocol-level relationships (e.g., BGP peers, OSPF area membership)"
    )


# ─────────────────────────────────────────────
# AGENT 4 OUTPUT — RetrievedEvidence
# ─────────────────────────────────────────────

class EvidencePassage(BaseModel):
    passage_id: str
    text: str
    source_id: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetrievedEvidence(BaseModel):
    """
    Output of the Knowledge Retrieval Agent.
    Contains passages retrieved from the Qdrant vector store.
    """
    query: str = Field(..., description="Query used to retrieve evidence")
    passages: List[EvidencePassage] = Field(default_factory=list)
    source_ids: List[str] = Field(default_factory=list, description="Distinct source identifiers")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    relevance_scores: List[float] = Field(default_factory=list)


# ─────────────────────────────────────────────
# AGENT 5 OUTPUT — DiagnosisResult
# ─────────────────────────────────────────────

class Hypothesis(BaseModel):
    hypothesis_id: str
    description: str
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    root_cause_category: str = Field(default="", description="Root-cause category (e.g. bgp_neighbor_down, physical_link_down)")
    supporting_evidence: List[str] = Field(default_factory=list, description="Explicit supporting evidence details")
    contradictory_evidence: List[str] = Field(default_factory=list, description="Contradictory evidence details")
    affected_devices: List[str] = Field(default_factory=list, description="Devices impacted by this hypothesis")
    affected_interfaces: List[str] = Field(default_factory=list, description="Interfaces impacted by this hypothesis")
    explanation: str = Field(default="", description="Diagnostic reasoning narrative")
    missing_evidence: List[str] = Field(default_factory=list, description="Missing signals or telemetry")


class DiagnosisResult(BaseModel):
    """
    Output of the Diagnostic Agent.
    """
    hypotheses: List[Hypothesis] = Field(
        ...,
        description="All hypotheses considered, ordered by confidence descending"
    )
    probable_root_cause: str = Field(
        ...,
        description="Single most probable root cause description"
    )
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="Evidence passage IDs supporting the diagnosis"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall diagnosis confidence")
    affected_components: List[str] = Field(
        default_factory=list,
        description="Device IDs / interface names identified as root-cause components"
    )
    symptom_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured symptom findings summary"
    )
    topology_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured topology context summary"
    )
    provenance: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Execution trace and benchmark provenance"
    )

    @property
    def primary_cause(self) -> str:
        if self.probable_root_cause:
            return self.probable_root_cause
        if self.hypotheses:
            return self.hypotheses[0].hypothesis_id
        return ""

    @property
    def root_causes(self) -> List[str]:
        res = []
        if self.probable_root_cause:
            res.append(self.probable_root_cause)
        for h in self.hypotheses:
            if h.hypothesis_id and h.hypothesis_id not in res:
                res.append(h.hypothesis_id)
        return res

    @property
    def contributing_factors(self) -> List[str]:
        factors = list(self.evidence_ids)
        for h in self.hypotheses:
            factors.extend(h.supporting_evidence_ids)
            factors.extend(h.supporting_evidence)
        return list(dict.fromkeys(factors))


# ─────────────────────────────────────────────
# AGENT 6 OUTPUT — RemediationProposal
# ─────────────────────────────────────────────

class RemediationProposal(BaseModel):
    """
    Output of the Remediation Agent.
    All operations must come from the predefined allow-list.
    The LLM MUST NOT generate arbitrary shell/network commands.
    """
    action_id: str = Field(..., description="Unique action identifier")
    incident_id: str = Field(default="", description="Associated incident identifier")
    diagnosis_id: str = Field(default="", description="Associated diagnosis identifier")
    root_cause_category: str = Field(default="", description="Root-cause category addressed")
    target: str = Field(..., description="Target device_id or interface")
    target_device: str = Field(default="", description="Canonical target device ID")
    target_interface: Optional[str] = Field(default=None, description="Canonical target interface if applicable")
    operation: str = Field(
        ...,
        description="Predefined operation name from the allow-list (e.g., clear_bgp_session)"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Operation-specific parameters (validated against the allow-list schema)"
    )
    risk: RiskLevel = Field(..., description="Classified risk level")
    risk_reasons: List[str] = Field(default_factory=list, description="Explanations for the assigned risk level")
    expected_effect: str = Field(default="", description="Human-readable expected outcome")
    expected_preconditions: Dict[str, Any] = Field(default_factory=dict, description="Preconditions required before execution")
    expected_postconditions: Dict[str, Any] = Field(default_factory=dict, description="Expected state conditions after execution")
    verification_condition: str = Field(
        default="",
        description="Condition to verify after execution (e.g., bgp_session_established)"
    )
    requires_human_approval: bool = Field(default=True, description="Strict human-in-the-loop requirement")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="Telemetry/event evidence supporting proposal")
    supporting_knowledge_ids: List[str] = Field(default_factory=list, description="Retrieved runbook/RFC IDs supporting proposal")
    rollback_plan: Optional[Dict[str, Any]] = Field(default=None, description="Deterministic rollback action and parameters")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Proposal creation timestamp")
    expires_at: Optional[datetime] = Field(default=None, description="Proposal expiration timestamp")
    canonical_hash: str = Field(default="", description="SHA-256 hash of canonical proposal payload")

    @property
    def proposal_id(self) -> str:
        return self.action_id

    @property
    def proposal_hash(self) -> str:
        return self.canonical_hash or self.calculate_canonical_hash()

    @property
    def risk_level(self) -> str:
        return self.risk.value if isinstance(self.risk, RiskLevel) else str(self.risk)

    def calculate_canonical_hash(self) -> str:
        """
        Calculates SHA-256 hash across canonical immutable proposal fields.
        """
        payload = {
            "action_id": self.action_id,
            "incident_id": self.incident_id,
            "diagnosis_id": self.diagnosis_id,
            "root_cause_category": self.root_cause_category,
            "target": self.target,
            "target_device": self.target_device or self.target.split(":")[0],
            "target_interface": self.target_interface or (self.target.split(":")[1] if ":" in self.target else None),
            "operation": self.operation,
            "parameters": self.parameters,
            "risk": self.risk.value if isinstance(self.risk, RiskLevel) else str(self.risk),
            "expected_preconditions": self.expected_preconditions,
            "expected_postconditions": self.expected_postconditions,
            "verification_condition": self.verification_condition,
            "rollback_plan": self.rollback_plan,
        }
        raw_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    def model_post_init(self, __context: Any) -> None:
        if not self.target_device and self.target:
            self.target_device = self.target.split(":")[0]
        if not self.target_interface and ":" in self.target:
            self.target_interface = self.target.split(":", 1)[1]
        if not self.canonical_hash:
            self.canonical_hash = self.calculate_canonical_hash()


# ─────────────────────────────────────────────
# AGENT 7 OUTPUT — PolicyDecision
# ─────────────────────────────────────────────

class PolicyDecision(BaseModel):
    """
    Deterministic safety policy evaluation output.
    """
    decision_id: str = Field(..., description="Unique policy decision ID")
    proposal_id: str = Field(..., description="Target proposal ID")
    status: PolicyStatus = Field(..., description="Policy evaluation status")
    is_allowed: bool = Field(..., description="Whether proposal is allowed to enter human approval review")
    reasons: List[str] = Field(default_factory=list, description="Detailed rationale for policy decision")
    checked_rules: List[str] = Field(default_factory=list, description="Rules audited during evaluation")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────
# AGENT 8 OUTPUT — ApprovalState & ApprovalDecision
# ─────────────────────────────────────────────

class ApprovalState(BaseModel):
    """
    Output of the Oversight / Safety Agent, updated by human reviewer.
    """
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    reviewer_action: Optional[ReviewerAction] = None
    timestamp: Optional[datetime] = None
    comments: Optional[str] = Field(
        None,
        description="Reviewer notes, edit rationale, or rejection reason"
    )
    policy_violations: List[str] = Field(
        default_factory=list,
        description="Policy checks that failed (empty if all passed)"
    )
    requires_human_approval: bool = Field(
        default=True,
        description="Safety agent decision — always True for state-changing operations"
    )


class ApprovalDecision(BaseModel):
    """
    Explicit, tamper-checked decision record from a verified human reviewer.
    """
    approval_id: str = Field(..., description="Unique approval identifier")
    proposal_id: str = Field(..., description="Target proposal ID (must match exactly)")
    incident_id: str = Field(default="", description="Associated incident ID")
    proposal_hash: str = Field(default="", description="Canonical hash of the proposal when approved")
    status: ApprovalStatus = Field(default=ApprovalStatus.APPROVED, description="Decision status (APPROVED, REJECTED, EXPIRED, CANCELLED)")
    reviewer: Optional[ReviewerRole] = None
    reviewer_identity: str = Field(default="operator", description="Identifier of human reviewer")
    reviewer_role: ReviewerRole = Field(default=ReviewerRole.NETWORK_OPERATOR, description="Verified role of human reviewer")
    comments: Optional[str] = Field(default=None, description="Reviewer justification or rejection notes")
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(default=None, description="Approval expiration timestamp")
    idempotency_key: str = Field(default="", description="Unique token preventing duplicate decision processing")


# ─────────────────────────────────────────────
# EXECUTOR OUTPUT — ExecutionResult
# ─────────────────────────────────────────────

class ExecutionResult(BaseModel):
    """
    Outcome of executing an approved remediation operation in the isolated simulator.
    """
    execution_id: str = Field(..., description="Unique execution identifier")
    proposal_id: str = Field(..., description="Associated proposal ID")
    approval_id: str = Field(..., description="Associated approval ID")
    operation: str = Field(..., description="Executed operation name")
    target_device: str = Field(..., description="Target device")
    status: ExecutionStatus = Field(..., description="Execution status (SUCCEEDED, FAILED, CANCELLED)")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    pre_state_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Simulator state before execution")
    post_state_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Simulator state after execution")
    stdout: str = Field(default="", description="Standard execution output log")
    stderr: str = Field(default="", description="Execution error output log")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed operational metadata")


# ─────────────────────────────────────────────
# EXECUTOR OUTPUT — VerificationResult
# ─────────────────────────────────────────────

class VerificationCheck(BaseModel):
    check_id: str
    description: str
    passed: bool
    observed_value: Optional[Any] = None
    expected_value: Optional[Any] = None


class VerificationResult(BaseModel):
    """
    Output of the Verification step (post-executor).
    Execution success does NOT imply network recovery.
    This result determines whether the incident is resolved.
    """
    verification_id: str = Field(default="", description="Unique verification ID")
    execution_id: str = Field(default="", description="Associated execution ID")
    status: VerificationStatus = Field(default=VerificationStatus.NOT_VERIFIED, description="Verification status")
    checks: List[Any] = Field(default_factory=list)
    observed_state: Dict[str, Any] = Field(default_factory=dict)
    expected_state: Dict[str, Any] = Field(default_factory=dict)
    success: bool = Field(
        ...,
        description="True only if ALL verification checks pass"
    )
    failure_reason: Optional[str] = Field(
        None,
        description="Human-readable explanation if success=False"
    )
    verified_at: Optional[datetime] = Field(default=None, description="Timestamp of verification check")


# ─────────────────────────────────────────────
# ROLLBACK OUTPUT — RollbackResult
# ─────────────────────────────────────────────

class RollbackResult(BaseModel):
    """
    Outcome of an automated rollback attempt when post-action verification fails.
    """
    rollback_id: str = Field(..., description="Unique rollback ID")
    proposal_id: str = Field(..., description="Associated proposal ID")
    execution_id: str = Field(..., description="Associated failed execution ID")
    operation: str = Field(..., description="Rollback operation executed")
    status: RollbackStatus = Field(..., description="Rollback execution status")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    restored_state: Dict[str, Any] = Field(default_factory=dict, description="State after rollback")
    is_verified: bool = Field(default=False, description="Whether restored baseline state was verified")
    failure_reason: Optional[str] = Field(default=None, description="Failure reason if rollback was not successful")


# ─────────────────────────────────────────────
# AUDIT LOGGING — AuditRecord & Chain
# ─────────────────────────────────────────────

class AuditRecord(BaseModel):
    """
    Immutable tamper-evident audit record in the sequential hash-chain.
    """
    record_id: str = Field(..., description="Unique audit record identifier")
    sequence_number: int = Field(..., ge=0, description="Monotonically increasing sequence number")
    incident_id: str = Field(..., description="Associated incident ID")
    action_type: str = Field(..., description="Type of action: PROPOSAL, POLICY, APPROVAL, EXECUTION, VERIFICATION, ROLLBACK, KILL_SWITCH")
    actor: str = Field(..., description="Entity triggering the action (agent or human user)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Canonical action payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prev_hash: str = Field(..., description="SHA-256 hash of previous record in the chain")
    current_hash: str = Field(..., description="SHA-256 hash of this record (prev_hash + sequence + timestamp + payload)")

    def calculate_hash(self) -> str:
        data = {
            "record_id": self.record_id,
            "sequence_number": self.sequence_number,
            "incident_id": self.incident_id,
            "action_type": self.action_type,
            "actor": self.actor,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "prev_hash": self.prev_hash,
        }
        raw_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


# ─── Verification & Rollback Models (Milestone 7 & 8) ────────────────────────
class CheckItem(BaseModel):
    name: str = ""
    passed: bool = True
    message: str = ""
    check_id: str = ""
    description: str = ""
    target_node: str = ""
    observed_value: Any = None
    expected_value: Any = None

    def model_post_init(self, __context: Any) -> None:
        if not self.check_id and self.name:
            self.check_id = self.name
        elif not self.name and self.check_id:
            self.name = self.check_id
        if not self.description and self.message:
            self.description = self.message
        elif not self.message and self.description:
            self.message = self.description


class RollbackClassification(str, Enum):
    """
    Explicit taxonomy of remediation rollback behavior.
    """
    EXACT_STATE_RESTORE = "EXACT_STATE_RESTORE"
    COMPENSATING_RECOVERY = "COMPENSATING_RECOVERY"
    NON_REVERSIBLE = "NON_REVERSIBLE"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"


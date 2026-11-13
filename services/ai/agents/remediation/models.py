
"""
models.py — Data contracts and specifications for the Remediation Agent and Safety Subsystem.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from services.ai.schemas.contracts import (
    RiskLevel,
    PolicyStatus,
    PolicyDecision,
    ApprovalStatus,
    ReviewerRole,
    ApprovalDecision,
    ExecutionStatus,
    ExecutionResult,
    VerificationStatus,
    VerificationResult,
    RollbackStatus,
    RollbackResult,
    RemediationProposal,
    RemediationStatus,
    AuditRecord,
)


class ActionDefinition(BaseModel):
    """
    Metadata specification for an allow-listed remediation action.
    """
    operation: str = Field(..., description="Unique operation identifier")
    description: str = Field(..., description="Human-readable summary of purpose")
    required_parameters: List[str] = Field(default_factory=list, description="Mandatory parameter keys")
    optional_parameters: List[str] = Field(default_factory=list, description="Optional parameter keys")
    parameter_schema: Dict[str, Any] = Field(default_factory=dict, description="Type validation rules for parameters")
    allowed_device_types: List[str] = Field(default_factory=list, description="Eligible target device roles")
    allowed_interface_types: List[str] = Field(default_factory=list, description="Eligible interface types")
    base_risk: RiskLevel = Field(..., description="Baseline risk classification")
    requires_human_approval: bool = Field(default=True, description="Strict human-in-the-loop requirement")
    is_reversible: bool = Field(default=True, description="Whether action supports automated rollback")
    rollback_operation: Optional[str] = Field(default=None, description="Registered rollback action name")
    default_timeout_seconds: float = Field(default=15.0, description="Maximum execution timeout")
    precondition_rules: List[str] = Field(default_factory=list, description="Prerequisite conditions before applying")
    postcondition_rules: List[str] = Field(default_factory=list, description="Expected state checks after applying")


class RemediationRiskAssessment(BaseModel):
    """
    Deterministic risk analysis output for a proposed remediation.
    """
    proposal_id: str
    risk_level: RiskLevel
    risk_score: float = Field(..., ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)
    affected_devices_count: int
    blast_radius_ier: float = Field(default=0.0)
    blast_radius_nur: float = Field(default=0.0)
    has_alternate_paths: bool = Field(default=True)
    is_reversible: bool = Field(default=True)
    protocol_criticality: str = Field(default="MEDIUM")
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

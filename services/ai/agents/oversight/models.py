"""
models.py — Data contracts for Human Oversight and Approval Workflow.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from services.ai.schemas.contracts import (
    ApprovalStatus,
    ReviewerRole,
    RemediationProposal,
    ApprovalDecision,
    PolicyDecision,
)


class ApprovalRequest(BaseModel):
    """
    Structured request dispatched to Human-in-the-Loop NOC review queue.
    """
    request_id: str = Field(..., description="Unique approval request identifier")
    proposal_id: str = Field(..., description="Target remediation proposal ID")
    incident_id: str = Field(..., description="Associated incident ID")
    proposal_hash: str = Field(..., description="Canonical SHA-256 hash of immutable proposal")
    operation: str = Field(..., description="Operation to be authorized")
    target: str = Field(..., description="Target device or interface")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated parameters")
    risk_level: str = Field(..., description="Risk assessment level (LOW, MEDIUM, HIGH, CRITICAL)")
    risk_reasons: List[str] = Field(default_factory=list, description="Risk justification points")
    policy_status: str = Field(..., description="Policy decision status (ALLOWED_FOR_REVIEW)")
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, description="Current approval status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="Hard expiration timestamp")
    decision: Optional[ApprovalDecision] = Field(default=None, description="Recorded reviewer decision")
    decision_history: List[Dict[str, Any]] = Field(default_factory=list, description="Audit trace of state transitions")


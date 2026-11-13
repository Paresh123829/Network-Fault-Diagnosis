"""
checkpoint_recovery.py — Workflow Restart Recovery & Reconciliation Engine.

Inspects incomplete or interrupted LangGraph remediation workflows after application restarts,
revalidates proposal hash integrity, approval validity, expiration SLAs, and kill switches,
enforces execution idempotency, and safely resumes approved workflows or fails closed.
"""

from __future__ import annotations

from enum import Enum
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    ExecutionResult,
    ExecutionStatus,
    RemediationProposal,
    VerificationStatus,
)
from services.ai.agents.oversight.kill_switch import kill_switch
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence

logger = logging.getLogger(__name__)


class WorkflowRecoveryStatus(str, Enum):
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPROVED_PENDING_EXECUTION = "APPROVED_PENDING_EXECUTION"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETED_PENDING_VERIFICATION = "EXECUTION_COMPLETED_PENDING_VERIFICATION"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    ROLLBACK_PENDING = "ROLLBACK_PENDING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"
    COMPLETED = "COMPLETED"


class WorkflowReconciliationReport(BaseModel):
    thread_id: str
    incident_id: str
    proposal_id: str
    recovery_status: WorkflowRecoveryStatus
    can_resume: bool
    rejection_reason: Optional[str] = None
    has_executed: bool = False
    execution_id: Optional[str] = None
    inspected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RemediationRestartRecoveryManager:
    """
    Durable workflow recovery and audit reconciliation controller.
    """

    def __init__(self, persistence=None) -> None:
        self.persistence = persistence or remediation_persistence

    def inspect_and_classify_workflow(
        self,
        thread_id: str,
        checkpoint_state: Optional[Dict[str, Any]] = None,
        incoming_decision: Optional[ApprovalDecision] = None,
    ) -> WorkflowReconciliationReport:
        """
        Reconciles checkpoint state with persistent database records to determine
        the truthful recovery status and safe resumption strategy.
        """
        now = datetime.now(timezone.utc)
        if not checkpoint_state:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id="unknown",
                proposal_id="unknown",
                recovery_status=WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED,
                can_resume=False,
                rejection_reason="No checkpoint state found for thread_id.",
            )

        # Extract workflow metadata
        incident_id = checkpoint_state.get("incident_id", "unknown")
        proposal_dict = checkpoint_state.get("remediation_proposal")
        if not proposal_dict:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id="unknown",
                recovery_status=WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED,
                can_resume=False,
                rejection_reason="Checkpoint state lacks remediation_proposal.",
            )

        if isinstance(proposal_dict, RemediationProposal):
            proposal = proposal_dict
        else:
            try:
                proposal = RemediationProposal(**proposal_dict)
            except Exception as e:
                return WorkflowReconciliationReport(
                    thread_id=thread_id,
                    incident_id=incident_id,
                    proposal_id="unknown",
                    recovery_status=WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED,
                    can_resume=False,
                    rejection_reason=f"Failed to parse remediation_proposal: {e}",
                )

        proposal_id = proposal.action_id

        # 1. Check Proposal Expiration
        if proposal.expires_at and proposal.expires_at < now:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id=proposal_id,
                recovery_status=WorkflowRecoveryStatus.EXPIRED,
                can_resume=False,
                rejection_reason=f"Proposal {proposal_id} expired at {proposal.expires_at.isoformat()}.",
            )

        # 2. Check Execution Idempotency
        existing_exec = self.persistence.get_execution_for_proposal(proposal_id)
        if existing_exec:
            # Execution has already occurred!
            if existing_exec.status == ExecutionStatus.SUCCEEDED:
                # Check verification
                ver_res = self.persistence.get_verification_for_execution(existing_exec.execution_id)
                if ver_res:
                    return WorkflowReconciliationReport(
                        thread_id=thread_id,
                        incident_id=incident_id,
                        proposal_id=proposal_id,
                        recovery_status=WorkflowRecoveryStatus.COMPLETED,
                        can_resume=False,
                        has_executed=True,
                        execution_id=existing_exec.execution_id,
                        rejection_reason="Workflow execution and verification already completed.",
                    )
                return WorkflowReconciliationReport(
                    thread_id=thread_id,
                    incident_id=incident_id,
                    proposal_id=proposal_id,
                    recovery_status=WorkflowRecoveryStatus.EXECUTION_COMPLETED_PENDING_VERIFICATION,
                    can_resume=True,
                    has_executed=True,
                    execution_id=existing_exec.execution_id,
                    rejection_reason=None,
                )
            elif existing_exec.status == ExecutionStatus.IN_PROGRESS:
                return WorkflowReconciliationReport(
                    thread_id=thread_id,
                    incident_id=incident_id,
                    proposal_id=proposal_id,
                    recovery_status=WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED,
                    can_resume=False,
                    has_executed=True,
                    execution_id=existing_exec.execution_id,
                    rejection_reason="Process crashed during execution. Simulator state must be assessed manually.",
                )

        # 3. Check Approval State (Use incoming decision if provided)
        appr_dec = incoming_decision
        if not appr_dec:
            appr_dec = self.persistence.get_approval_decision(proposal_id)
        if not appr_dec:
            # Checkpoint might carry an in-flight decision
            raw_dec = checkpoint_state.get("approval_decision")
            if raw_dec:
                appr_dec = raw_dec if isinstance(raw_dec, ApprovalDecision) else ApprovalDecision(**raw_dec)

        if not appr_dec:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id=proposal_id,
                recovery_status=WorkflowRecoveryStatus.WAITING_FOR_APPROVAL,
                can_resume=False,
                rejection_reason="Waiting for explicit human approval decision.",
            )

        # 4. Revalidate Decision Hash
        if appr_dec.proposal_hash != proposal.canonical_hash:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id=proposal_id,
                recovery_status=WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED,
                can_resume=False,
                rejection_reason=f"Proposal hash mismatch! Stored: {proposal.canonical_hash}, Decision: {appr_dec.proposal_hash}. Tamper detected.",
            )

        # 5. Check Approval Status
        if appr_dec.status == ApprovalStatus.REJECTED:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id=proposal_id,
                recovery_status=WorkflowRecoveryStatus.CANCELLED,
                can_resume=False,
                rejection_reason="Remediation proposal was rejected by operator.",
            )

        if appr_dec.status == ApprovalStatus.EXPIRED or (appr_dec.expires_at and appr_dec.expires_at < now):
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id=proposal_id,
                recovery_status=WorkflowRecoveryStatus.EXPIRED,
                can_resume=False,
                rejection_reason="Approval decision expired.",
            )

        if appr_dec.status != ApprovalStatus.APPROVED:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id=proposal_id,
                recovery_status=WorkflowRecoveryStatus.WAITING_FOR_APPROVAL,
                can_resume=False,
                rejection_reason=f"Approval status is {appr_dec.status.value}.",
            )

        # 6. Check Kill Switch
        can_run, ks_reason = kill_switch.can_execute(
            operation=proposal.operation,
            target_device=proposal.target_device or proposal.target.split(":")[0],
            agent_name="restart_recovery_manager",
        )
        if not can_run:
            return WorkflowReconciliationReport(
                thread_id=thread_id,
                incident_id=incident_id,
                proposal_id=proposal_id,
                recovery_status=WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED,
                can_resume=False,
                rejection_reason=f"Kill switch active during recovery: {ks_reason}",
            )

        # All checks passed: can resume execution safely
        return WorkflowReconciliationReport(
            thread_id=thread_id,
            incident_id=incident_id,
            proposal_id=proposal_id,
            recovery_status=WorkflowRecoveryStatus.APPROVED_PENDING_EXECUTION,
            can_resume=True,
            rejection_reason=None,
        )


# Global singleton instance
restart_recovery_manager = RemediationRestartRecoveryManager()

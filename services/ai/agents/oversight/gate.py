"""
gate.py — Human Approval Gate and LangGraph Execution Controller.

Evaluates approval status before allowing the workflow to proceed to the simulated executor.
Enforces fail-closed safety: execution is unreachable unless an explicit, valid human approval exists.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    RemediationProposal,
)
from .approval_manager import approval_manager, ApprovalManager
from .models import ApprovalRequest

logger = logging.getLogger(__name__)


class HumanApprovalGate:
    """
    Enforces authorization gates before any execution step.
    """

    def __init__(self, manager: Optional[ApprovalManager] = None) -> None:
        self.approval_manager = manager or approval_manager

    def evaluate_gate(
        self,
        proposal: Optional[RemediationProposal],
        approval_decision: Optional[ApprovalDecision] = None,
    ) -> Tuple[bool, str, Optional[ApprovalRequest]]:
        """
        Determines whether the workflow can proceed from approval to execution.
        Returns (is_approved_for_execution, reason, approval_request).
        """
        if not proposal:
            return False, "No remediation proposal provided.", None

        req = self.approval_manager.get_by_proposal_id(proposal.action_id)
        if not req:
            return False, f"Proposal '{proposal.action_id}' has not been submitted for approval.", None

        # Check for replay
        if self.approval_manager.is_executed(proposal.action_id):
            return False, f"Security violation: Proposal '{proposal.action_id}' has already been executed. Replay denied.", req

        # Check current status
        if req.status == ApprovalStatus.PENDING:
            return False, f"Proposal '{proposal.action_id}' is PENDING human authorization. Execution paused.", req

        if req.status == ApprovalStatus.REJECTED:
            return False, f"Proposal '{proposal.action_id}' was REJECTED by operator. Execution prohibited.", req

        if req.status == ApprovalStatus.EXPIRED:
            return False, f"Approval request for proposal '{proposal.action_id}' has EXPIRED. Execution prohibited.", req

        if req.status == ApprovalStatus.CANCELLED:
            return False, f"Approval request for proposal '{proposal.action_id}' was CANCELLED. Execution prohibited.", req

        if req.status == ApprovalStatus.APPROVED:
            # Revalidate hash integrity
            current_hash = proposal.calculate_canonical_hash()
            if req.proposal_hash != current_hash:
                return False, f"Security violation: Proposal hash mismatch! Claimed '{req.proposal_hash}', current '{current_hash}'. Tampering detected.", req

            # Decision must be attached
            if not req.decision or req.decision.status != ApprovalStatus.APPROVED:
                return False, "Approval record missing valid decision payload.", req

            return True, f"Proposal authorized by {req.decision.reviewer_identity} ({req.decision.reviewer_role.value}).", req

        return False, f"Unknown approval state '{req.status.value}'. Fail-closed.", req


# Global singleton instance
human_approval_gate = HumanApprovalGate()


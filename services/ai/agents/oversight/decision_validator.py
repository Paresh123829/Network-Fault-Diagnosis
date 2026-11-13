"""
decision_validator.py — Verification of Human Approval Signatures and Invariants.

Enforces:
1. Hash integrity binding proposal to approval.
2. Expiration timing.
3. Reviewer role authorization.
4. Non-replay protection.
5. Incident alignment.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Tuple

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    RemediationProposal,
    ReviewerRole,
)
from .models import ApprovalRequest

logger = logging.getLogger(__name__)


class ApprovalDecisionValidator:
    """
    Validates that a human approval decision is authentic, unexpired, and strictly bound to the proposal.
    """

    AUTHORIZED_ROLES = {
        ReviewerRole.NOC_ENGINEER,
        ReviewerRole.NETWORK_OPERATOR,
        ReviewerRole.SITE_RELIABILITY_ENGINEER,
        ReviewerRole.ADMINISTRATOR,
    }

    def validate_approval(
        self,
        decision: ApprovalDecision,
        proposal: RemediationProposal,
        request: ApprovalRequest,
    ) -> Tuple[bool, List[str]]:
        """
        Executes strict verification of an incoming approval decision.
        """
        errors: List[str] = []
        now = datetime.now(timezone.utc)

        # 1. Proposal ID alignment
        if decision.proposal_id != proposal.action_id:
            errors.append(
                f"Proposal ID mismatch: decision targets '{decision.proposal_id}' but active proposal is '{proposal.action_id}'."
            )

        # 2. Incident ID alignment
        if decision.incident_id != proposal.incident_id:
            errors.append(
                f"Incident ID mismatch: decision belongs to '{decision.incident_id}' but proposal belongs to '{proposal.incident_id}'."
            )

        # 3. Canonical Hash Verification (Anti-Tampering)
        calculated_hash = proposal.calculate_canonical_hash()
        if decision.proposal_hash != calculated_hash:
            errors.append(
                f"Security violation: Approval proposal_hash '{decision.proposal_hash}' does NOT match current canonical proposal hash '{calculated_hash}'. "
                "Proposal has been modified after review dispatch."
            )

        # 4. Expiration Check
        if request.expires_at and request.expires_at <= now:
            errors.append(f"Approval request expired at {request.expires_at.isoformat()}. Current time is {now.isoformat()}.")

        if decision.expires_at and decision.expires_at <= now:
            errors.append(f"Approval decision expired at {decision.expires_at.isoformat()}. Current time is {now.isoformat()}.")

        # 5. Reviewer Identity & Role Verification
        if not decision.reviewer_identity or decision.reviewer_identity.strip() == "":
            errors.append("Reviewer identity cannot be empty.")

        if decision.reviewer_role not in self.AUTHORIZED_ROLES:
            errors.append(
                f"Reviewer role '{decision.reviewer_role}' is not authorized to approve state-changing remediation actions. "
                f"Authorized roles: {[r.value for r in self.AUTHORIZED_ROLES]}."
            )

        # 6. Replay / Re-use Check
        if request.status not in (ApprovalStatus.PENDING,):
            errors.append(
                f"Approval request '{request.request_id}' is already in state '{request.status.value}'. Cannot accept duplicate or replayed decision."
            )

        return (len(errors) == 0, errors)


# Global singleton instance
decision_validator = ApprovalDecisionValidator()


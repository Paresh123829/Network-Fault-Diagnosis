"""
approval_manager.py — Human Approval Lifecycle Management and Anti-Replay Store.

Maintains pending requests, records explicit reviewer decisions, validates hash integrity,
and prevents double execution or replay attacks.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    PolicyDecision,
    RemediationProposal,
    ReviewerRole,
)
from .models import ApprovalRequest
from .decision_validator import decision_validator

logger = logging.getLogger(__name__)


class ApprovalManager:
    """
    Thread-safe repository and lifecycle controller for human approval requests.
    """

    def __init__(self, default_ttl_minutes: int = 30) -> None:
        self._lock = threading.RLock()
        self._requests: Dict[str, ApprovalRequest] = {}
        self._by_proposal: Dict[str, str] = {}
        self._executed_proposals: set[str] = set()
        self.default_ttl = timedelta(minutes=default_ttl_minutes)

    def create_request(
        self,
        proposal: RemediationProposal,
        policy_decision: PolicyDecision,
        risk_level: str = "MEDIUM",
        risk_reasons: Optional[List[str]] = None,
        ttl_minutes: Optional[int] = None,
    ) -> ApprovalRequest:
        """
        Creates a new PENDING approval request for an eligible remediation proposal.
        """
        with self._lock:
            # Check if active request already exists for this proposal
            existing_id = self._by_proposal.get(proposal.action_id)
            if existing_id and existing_id in self._requests:
                existing = self._requests[existing_id]
                if existing.status == ApprovalStatus.PENDING and existing.expires_at > datetime.now(timezone.utc):
                    return existing

            request_id = f"appr_{uuid.uuid4().hex[:12]}"
            ttl = timedelta(minutes=ttl_minutes) if ttl_minutes else self.default_ttl
            now = datetime.now(timezone.utc)
            expires_at = now + ttl

            req = ApprovalRequest(
                request_id=request_id,
                proposal_id=proposal.action_id,
                incident_id=proposal.incident_id,
                proposal_hash=proposal.calculate_canonical_hash(),
                operation=proposal.operation,
                target=proposal.target,
                parameters=proposal.parameters,
                risk_level=risk_level,
                risk_reasons=risk_reasons or proposal.risk_reasons,
                policy_status=policy_decision.status.value,
                status=ApprovalStatus.PENDING,
                created_at=now,
                expires_at=expires_at,
                decision=None,
                decision_history=[{
                    "event": "REQUEST_CREATED",
                    "status": ApprovalStatus.PENDING.value,
                    "timestamp": now.isoformat(),
                }]
            )

            self._requests[request_id] = req
            self._by_proposal[proposal.action_id] = request_id
            logger.info(f"Created approval request {request_id} for proposal {proposal.action_id} (expires {expires_at.isoformat()}).")
            return req

    def submit_decision(
        self,
        decision: ApprovalDecision,
        proposal: RemediationProposal,
    ) -> Tuple[bool, str, Optional[ApprovalRequest]]:
        """
        Submits and records an explicit decision from a human reviewer.
        Validates hash integrity, authorization, and anti-replay guards.
        """
        with self._lock:
            # 1. Lookup request
            request_id = self._by_proposal.get(proposal.action_id)
            if not request_id or request_id not in self._requests:
                return False, f"No approval request found for proposal '{proposal.action_id}'.", None

            req = self._requests[request_id]

            # 2. Replay & Double-Execution Guard
            if proposal.action_id in self._executed_proposals:
                return False, f"Security violation: Proposal '{proposal.action_id}' has already been executed. Replay denied.", req

            # 3. Decision validation
            valid, errors = decision_validator.validate_approval(decision, proposal, req)
            if not valid:
                logger.warning(f"Rejected invalid approval decision for request {req.request_id}: {errors}")
                return False, "; ".join(errors), req

            # 4. Record decision
            now = datetime.now(timezone.utc)
            req.decision = decision
            req.status = decision.status
            req.decision_history.append({
                "event": f"DECISION_{decision.status.value.upper()}",
                "reviewer": decision.reviewer_identity,
                "role": decision.reviewer_role.value,
                "status": decision.status.value,
                "comments": decision.comments,
                "timestamp": now.isoformat(),
            })

            logger.info(f"Recorded human decision '{decision.status.value}' for request {req.request_id} by {decision.reviewer_identity}.")
            return True, f"Decision '{decision.status.value}' successfully recorded.", req

    def cancel_request(self, proposal_id: str, reason: str, actor: str = "operator") -> Tuple[bool, str]:
        """Cancels a pending approval request."""
        with self._lock:
            request_id = self._by_proposal.get(proposal_id)
            if not request_id or request_id not in self._requests:
                return False, f"No request found for proposal {proposal_id}."

            req = self._requests[request_id]
            if req.status != ApprovalStatus.PENDING:
                return False, f"Cannot cancel request in state '{req.status.value}'."

            now = datetime.now(timezone.utc)
            req.status = ApprovalStatus.CANCELLED
            req.decision_history.append({
                "event": "REQUEST_CANCELLED",
                "actor": actor,
                "reason": reason,
                "timestamp": now.isoformat(),
            })
            return True, "Request cancelled successfully."

    def expire_stale_requests(self) -> int:
        """Audits all pending requests and transitions timed-out ones to EXPIRED."""
        with self._lock:
            now = datetime.now(timezone.utc)
            expired_count = 0
            for req in self._requests.values():
                if req.status == ApprovalStatus.PENDING and req.expires_at <= now:
                    req.status = ApprovalStatus.EXPIRED
                    req.decision_history.append({
                        "event": "REQUEST_EXPIRED",
                        "timestamp": now.isoformat(),
                    })
                    expired_count += 1
            return expired_count

    def mark_executed(self, proposal_id: str) -> None:
        """Marks proposal as executed to permanently prohibit replay."""
        with self._lock:
            self._executed_proposals.add(proposal_id)

    def is_executed(self, proposal_id: str) -> bool:
        """Checks if a proposal has already been executed."""
        with self._lock:
            return proposal_id in self._executed_proposals

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._requests.get(request_id)

    def get_by_proposal_id(self, proposal_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            rid = self._by_proposal.get(proposal_id)
            return self._requests.get(rid) if rid else None

    def get_pending_requests(self) -> List[ApprovalRequest]:
        with self._lock:
            self.expire_stale_requests()
            return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def reset_all(self) -> None:
        """Resets store for tests."""
        with self._lock:
            self._requests.clear()
            self._by_proposal.clear()
            self._executed_proposals.clear()


# Global singleton instance
approval_manager = ApprovalManager()


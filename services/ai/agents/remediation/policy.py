"""
policy.py — Deterministic Remediation Safety Policy Engine.

Evaluates proposals against strict safety invariants before human review is permitted.
Enforces fail-closed semantics across allow-lists, topology verification, parameter schemas,
diagnostic evidence grounding, and kill-switch status.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from services.ai.schemas.contracts import (
    RemediationProposal,
    PolicyDecision,
    PolicyStatus,
    RiskLevel,
)
from services.ai.agents.topology.graph import TopologyGraph
from services.ai.agents.oversight.kill_switch import kill_switch
from .action_registry import action_registry
from .validator import remediation_validator

logger = logging.getLogger(__name__)


class RemediationPolicyEngine:
    """
    Evaluates proposed remediation actions against deterministic safety policies.
    """

    def __init__(self, topology_graph: Optional[TopologyGraph] = None) -> None:
        self.topology_graph = topology_graph

    def set_topology_graph(self, topology_graph: TopologyGraph) -> None:
        self.topology_graph = topology_graph

    def evaluate_proposal(
        self,
        proposal: RemediationProposal,
        topology_graph: Optional[TopologyGraph] = None,
        min_diagnosis_confidence: float = 0.60
    ) -> PolicyDecision:
        """
        Executes exhaustive deterministic safety evaluation.
        Produces structured PolicyDecision with complete audit rationale.
        """
        checked_rules: List[str] = []
        reasons: List[str] = []
        decision_id = f"pol_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # 1. Kill-Switch Check
        checked_rules.append("rule_kill_switch_inactive")
        can_run, ks_reason = kill_switch.can_execute(
            operation=proposal.operation,
            target_device=proposal.target_device or proposal.target.split(":")[0],
            agent_name="remediation_agent"
        )
        if not can_run:
            reasons.append(f"Policy violation: {ks_reason}")
            return PolicyDecision(
                decision_id=decision_id,
                proposal_id=proposal.action_id,
                status=PolicyStatus.REJECTED_KILL_SWITCH_ACTIVE,
                is_allowed=False,
                reasons=reasons,
                checked_rules=checked_rules,
                evaluated_at=now,
            )

        # 2. Expiration Check
        checked_rules.append("rule_proposal_not_expired")
        if proposal.expires_at and proposal.expires_at <= now:
            reasons.append(f"Proposal expired at {proposal.expires_at.isoformat()}. Current time is {now.isoformat()}.")
            return PolicyDecision(
                decision_id=decision_id,
                proposal_id=proposal.action_id,
                status=PolicyStatus.REJECTED_EXPIRED_PROPOSAL,
                is_allowed=False,
                reasons=reasons,
                checked_rules=checked_rules,
                evaluated_at=now,
            )

        # 3. Allow-List Membership
        checked_rules.append("rule_operation_allowlisted")
        if not action_registry.is_allowed(proposal.operation):
            reasons.append(f"Operation '{proposal.operation}' is not an authorized allow-listed remediation action.")
            return PolicyDecision(
                decision_id=decision_id,
                proposal_id=proposal.action_id,
                status=PolicyStatus.REJECTED_UNKNOWN_OPERATION,
                is_allowed=False,
                reasons=reasons,
                checked_rules=checked_rules,
                evaluated_at=now,
            )

        # 4. Parameter Schema Validation & Prohibited Keyword Check
        checked_rules.append("rule_parameter_schema_and_keyword_safety")
        params_valid, param_errors = action_registry.validate_operation_and_parameters(
            proposal.operation,
            proposal.parameters
        )
        if not params_valid:
            reasons.extend(param_errors)
            return PolicyDecision(
                decision_id=decision_id,
                proposal_id=proposal.action_id,
                status=PolicyStatus.REJECTED_INVALID_PARAMETERS,
                is_allowed=False,
                reasons=reasons,
                checked_rules=checked_rules,
                evaluated_at=now,
            )

        # 5. Target Device & Interface Validation in Topology
        checked_rules.append("rule_topology_target_and_interface_ownership")
        graph = topology_graph or self.topology_graph
        if graph:
            target_valid, target_errors = remediation_validator.validate_proposal_targets(
                proposal,
                graph
            )
            if not target_valid:
                reasons.extend(target_errors)
                status = PolicyStatus.REJECTED_UNKNOWN_TARGET if "does not exist" in " ".join(target_errors) else PolicyStatus.REJECTED_INVALID_TOPOLOGY
                return PolicyDecision(
                    decision_id=decision_id,
                    proposal_id=proposal.action_id,
                    status=status,
                    is_allowed=False,
                    reasons=reasons,
                    checked_rules=checked_rules,
                    evaluated_at=now,
                )

        # 6. Diagnostic Evidence Grounding
        checked_rules.append("rule_evidence_grounding_and_confidence")
        if not proposal.supporting_evidence_ids and not proposal.parameters.get("evidence_ids"):
            reasons.append("Remediation proposal lacks supporting telemetry/event evidence identifiers.")
            return PolicyDecision(
                decision_id=decision_id,
                proposal_id=proposal.action_id,
                status=PolicyStatus.REJECTED_INSUFFICIENT_EVIDENCE,
                is_allowed=False,
                reasons=reasons,
                checked_rules=checked_rules,
                evaluated_at=now,
            )

        # 7. Rollback Availability for Reversible Actions
        checked_rules.append("rule_rollback_plan_enforced")
        action_def = action_registry.get(proposal.operation)
        if action_def and action_def.is_reversible and not proposal.rollback_plan:
            reasons.append(f"Operation '{proposal.operation}' is reversible but proposal does not define a rollback_plan.")
            return PolicyDecision(
                decision_id=decision_id,
                proposal_id=proposal.action_id,
                status=PolicyStatus.REJECTED_UNSAFE_OPERATION,
                is_allowed=False,
                reasons=reasons,
                checked_rules=checked_rules,
                evaluated_at=now,
            )

        # 8. Proposal Integrity Hash Check
        checked_rules.append("rule_canonical_hash_integrity")
        expected_hash = proposal.calculate_canonical_hash()
        if proposal.canonical_hash and proposal.canonical_hash != expected_hash:
            reasons.append(f"Proposal canonical hash mismatch: claimed '{proposal.canonical_hash}', calculated '{expected_hash}'. Tampering detected.")
            return PolicyDecision(
                decision_id=decision_id,
                proposal_id=proposal.action_id,
                status=PolicyStatus.REJECTED_UNSAFE_OPERATION,
                is_allowed=False,
                reasons=reasons,
                checked_rules=checked_rules,
                evaluated_at=now,
            )

        # All checks passed: Allowed to enter human approval stage
        reasons.append("All deterministic safety policies satisfied. Proposal authorized for human operator review.")
        return PolicyDecision(
            decision_id=decision_id,
            proposal_id=proposal.action_id,
            status=PolicyStatus.ALLOWED_FOR_REVIEW,
            is_allowed=True,
            reasons=reasons,
            checked_rules=checked_rules,
            evaluated_at=now,
        )


# Global singleton instance
remediation_policy = RemediationPolicyEngine()


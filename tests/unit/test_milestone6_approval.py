"""
test_milestone6_approval.py — Unit tests for Approval Lifecycle, Anti-Replay, and Human Approval Gate.
"""

import pytest
from datetime import datetime, timezone, timedelta

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    PolicyDecision,
    PolicyStatus,
    RemediationProposal,
    ReviewerRole,
    RiskLevel,
)
from services.ai.agents.oversight.approval_manager import ApprovalManager, approval_manager
from services.ai.agents.oversight.decision_validator import ApprovalDecisionValidator, decision_validator
from services.ai.agents.oversight.gate import HumanApprovalGate, human_approval_gate


@pytest.fixture
def sample_proposal():
    return RemediationProposal(
        action_id="act_appr_test_1",
        incident_id="inc_42",
        target="leaf1:Ethernet1/1",
        target_device="leaf1",
        target_interface="Ethernet1/1",
        operation="restore_interface_admin_state",
        parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
        risk=RiskLevel.MEDIUM,
        expected_effect="Restores admin state",
        verification_condition="interface_operational_state_is_up",
        supporting_evidence_ids=["ev_1"],
        rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
    )


@pytest.fixture
def sample_policy_decision(sample_proposal):
    return PolicyDecision(
        decision_id="pol_1",
        proposal_id=sample_proposal.action_id,
        status=PolicyStatus.ALLOWED_FOR_REVIEW,
        is_allowed=True,
    )


class TestApprovalLifecycle:
    def setup_method(self):
        approval_manager.reset_all()

    def teardown_method(self):
        approval_manager.reset_all()

    def test_create_approval_request(self, sample_proposal, sample_policy_decision):
        req = approval_manager.create_request(sample_proposal, sample_policy_decision)
        assert req.request_id.startswith("appr_")
        assert req.proposal_id == sample_proposal.action_id
        assert req.proposal_hash == sample_proposal.calculate_canonical_hash()
        assert req.status == ApprovalStatus.PENDING

    def test_approve_request_successfully(self, sample_proposal, sample_policy_decision):
        req = approval_manager.create_request(sample_proposal, sample_policy_decision)
        decision = ApprovalDecision(
            approval_id="dec_1",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash=sample_proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="alice_noc",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
            comments="Verified telemetry and approved.",
        )
        ok, msg, updated_req = approval_manager.submit_decision(decision, sample_proposal)
        assert ok is True
        assert updated_req.status == ApprovalStatus.APPROVED
        assert updated_req.decision is not None

    def test_reject_request_successfully(self, sample_proposal, sample_policy_decision):
        req = approval_manager.create_request(sample_proposal, sample_policy_decision)
        decision = ApprovalDecision(
            approval_id="dec_reject_1",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash=sample_proposal.calculate_canonical_hash(),
            status=ApprovalStatus.REJECTED,
            reviewer_identity="bob_sre",
            reviewer_role=ReviewerRole.SITE_RELIABILITY_ENGINEER,
            comments="Maintenance window closed.",
        )
        ok, msg, updated_req = approval_manager.submit_decision(decision, sample_proposal)
        assert ok is True
        assert updated_req.status == ApprovalStatus.REJECTED

    def test_negative_proposal_tampering_rejected(self, sample_proposal, sample_policy_decision):
        req = approval_manager.create_request(sample_proposal, sample_policy_decision)
        # Decision has mismatched proposal hash
        decision = ApprovalDecision(
            approval_id="dec_bad_hash",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash="f" * 64,  # Incorrect hash
            status=ApprovalStatus.APPROVED,
            reviewer_identity="alice_noc",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
        )
        ok, msg, _ = approval_manager.submit_decision(decision, sample_proposal)
        assert ok is False
        assert "does NOT match current canonical proposal hash" in msg

    def test_negative_expired_approval_rejected(self, sample_proposal, sample_policy_decision):
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        # Create request that expired in the past
        req = approval_manager.create_request(sample_proposal, sample_policy_decision, ttl_minutes=-10)
        decision = ApprovalDecision(
            approval_id="dec_expired",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash=sample_proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="alice_noc",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
        )
        ok, msg, _ = approval_manager.submit_decision(decision, sample_proposal)
        assert ok is False
        assert "Approval request expired" in msg

    def test_negative_unauthorized_role_rejected(self, sample_proposal, sample_policy_decision):
        req = approval_manager.create_request(sample_proposal, sample_policy_decision)
        # AUTOMATION_SYSTEM is not authorized to approve state-changing operations
        decision = ApprovalDecision(
            approval_id="dec_unauth",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash=sample_proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="auto_bot",
            reviewer_role=ReviewerRole.AUTOMATION_SYSTEM,
        )
        ok, msg, _ = approval_manager.submit_decision(decision, sample_proposal)
        assert ok is False
        assert "not authorized to approve" in msg

    def test_negative_replay_execution_prevented(self, sample_proposal, sample_policy_decision):
        req = approval_manager.create_request(sample_proposal, sample_policy_decision)
        decision = ApprovalDecision(
            approval_id="dec_exec_1",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash=sample_proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="alice_noc",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
        )
        ok, _, _ = approval_manager.submit_decision(decision, sample_proposal)
        assert ok is True

        # Simulate execution completion
        approval_manager.mark_executed(sample_proposal.action_id)

        # Attempt to submit a replayed decision for the executed proposal
        replayed_decision = ApprovalDecision(
            approval_id="dec_exec_2",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash=sample_proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="alice_noc",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
        )
        ok_replay, msg_replay, _ = approval_manager.submit_decision(replayed_decision, sample_proposal)
        assert ok_replay is False
        assert "has already been executed. Replay denied" in msg_replay

    def test_gate_evaluation_states(self, sample_proposal, sample_policy_decision):
        # 1. Before submission: gate blocks with PENDING
        req = approval_manager.create_request(sample_proposal, sample_policy_decision)
        can_exec, reason, _ = human_approval_gate.evaluate_gate(sample_proposal)
        assert can_exec is False
        assert "PENDING human authorization" in reason

        # 2. After approval: gate permits execution
        decision = ApprovalDecision(
            approval_id="dec_gate_1",
            proposal_id=sample_proposal.action_id,
            incident_id=sample_proposal.incident_id,
            proposal_hash=sample_proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="carol_netops",
            reviewer_role=ReviewerRole.NETWORK_OPERATOR,
        )
        approval_manager.submit_decision(decision, sample_proposal)
        can_exec_after, reason_after, _ = human_approval_gate.evaluate_gate(sample_proposal)
        assert can_exec_after is True
        assert "Proposal authorized by carol_netops" in reason_after


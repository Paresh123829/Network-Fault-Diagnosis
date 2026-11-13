"""
test_milestone7_remediation.py — Unit tests for Milestone 7 Safe Containerlab Remediation Adapter.
"""

import pytest

from network.containerlab.remediation.clab_adapter import ContainerlabRemediationAdapter
from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    ExecutionStatus,
    RemediationProposal,
    ReviewerRole,
    RiskLevel,
)
from services.ai.agents.oversight.kill_switch import kill_switch


@pytest.fixture
def adapter():
    return ContainerlabRemediationAdapter(force_mock=True)


@pytest.fixture
def sample_proposal():
    return RemediationProposal(
        action_id="act_clab_test_01",
        incident_id="inc_clab_01",
        diagnosis_id="diag_clab_01",
        root_cause_category="bgp_clear",
        target="R1:172.16.12.2",
        target_device="R1",
        target_interface="172.16.12.2",
        operation="reset_bgp_session",
        parameters={"target_device": "R1", "peer_ip": "172.16.12.2"},
        risk=RiskLevel.MEDIUM,
    )


@pytest.fixture
def valid_approval(sample_proposal):
    return ApprovalDecision(
        approval_id="appr_clab_test_01",
        proposal_id=sample_proposal.action_id,
        incident_id=sample_proposal.incident_id,
        proposal_hash=sample_proposal.canonical_hash,
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_test",
        reviewer_role=ReviewerRole.NETWORK_OPERATOR,
        comments="Approved for unit test",
    )


@pytest.fixture(autouse=True)
def cleanup_kill_switch():
    kill_switch.reset_all()
    yield
    kill_switch.reset_all()


def test_remediation_success(adapter, sample_proposal, valid_approval):
    res = adapter.execute_remediation(sample_proposal, valid_approval)
    assert res.status == ExecutionStatus.SUCCEEDED
    assert res.proposal_id == sample_proposal.action_id
    assert res.target_device == "R1"
    assert res.stderr is None or res.stderr == ""


def test_unauthorized_node_blocked(adapter, valid_approval):
    bad_proposal = RemediationProposal(
        action_id="act_bad_target",
        incident_id="inc_01",
        target="edge_router_prod_01",
        target_device="edge_router_prod_01",
        operation="reset_bgp_session",
        parameters={"peer_ip": "10.0.0.1"},
        risk=RiskLevel.HIGH,
    )
    bad_approval = valid_approval.model_copy(update={
        "proposal_id": bad_proposal.action_id,
        "proposal_hash": bad_proposal.canonical_hash,
    })
    res = adapter.execute_remediation(bad_proposal, bad_approval)
    assert res.status == ExecutionStatus.FAILED
    assert "unauthorized" in res.stderr.lower()


def test_unapproved_proposal_blocked(adapter, sample_proposal, valid_approval):
    unapproved = valid_approval.model_copy(update={"status": ApprovalStatus.REJECTED})
    res = adapter.execute_remediation(sample_proposal, unapproved)
    assert res.status == ExecutionStatus.FAILED
    assert "mandatory human approval" in res.stderr.lower()


def test_kill_switch_blocks_remediation(adapter, sample_proposal, valid_approval):
    kill_switch.activate_global(reason="Emergency stop for test")
    try:
        res = adapter.execute_remediation(sample_proposal, valid_approval)
        assert res.status == ExecutionStatus.FAILED
        assert "kill switch" in res.stderr.lower()
    finally:
        kill_switch.deactivate_global(reason="test cleanup")

"""
test_milestone7_security_negative.py — Security negative tests verifying strict invariant enforcement.
"""

import pytest

from network.containerlab.remediation.clab_adapter import ContainerlabRemediationAdapter
from network.containerlab.fault_injection.injector import FaultInjector
from network.containerlab.scenarios.registry import get_scenario
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
def injector():
    return FaultInjector(force_mock=True)


@pytest.fixture(autouse=True)
def cleanup_kill_switch():
    kill_switch.reset_all()
    yield
    kill_switch.reset_all()


def test_tampered_proposal_hash_rejected(adapter):
    proposal = RemediationProposal(
        action_id="act_tamper_test",
        incident_id="inc_tamper_01",
        target="R1:172.16.12.2",
        target_device="R1",
        operation="reset_bgp_session",
        parameters={"peer_ip": "172.16.12.2"},
        risk=RiskLevel.MEDIUM,
    )
    tampered_approval = ApprovalDecision(
        approval_id="appr_tamper_01",
        proposal_id=proposal.action_id,
        incident_id=proposal.incident_id,
        proposal_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # invalid hash
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_test",
        reviewer_role=ReviewerRole.NETWORK_OPERATOR,
    )
    res = adapter.execute_remediation(proposal, tampered_approval)
    assert res.status == ExecutionStatus.FAILED
    assert "tampering detected" in res.stderr.lower() or "hash mismatch" in res.stderr.lower()


def test_disallowed_operation_rejected(adapter):
    proposal = RemediationProposal(
        action_id="act_disallowed_op",
        incident_id="inc_disallowed",
        target="R1:eth1",
        target_device="R1",
        operation="rm_rf_root_filesystem",  # Malicious/unauthorized operation
        parameters={},
        risk=RiskLevel.CRITICAL,
    )
    approval = ApprovalDecision(
        approval_id="appr_disallowed",
        proposal_id=proposal.action_id,
        incident_id=proposal.incident_id,
        proposal_hash=proposal.canonical_hash,
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_test",
        reviewer_role=ReviewerRole.NETWORK_OPERATOR,
    )
    res = adapter.execute_remediation(proposal, approval)
    assert res.status == ExecutionStatus.FAILED
    assert "not in the containerlab allowlist" in res.stderr.lower() or "not allowed" in res.stderr.lower()


def test_external_node_remediation_rejected(adapter):
    proposal = RemediationProposal(
        action_id="act_ext_node",
        incident_id="inc_ext",
        target="core-router-nyc-01:ge-0/0/0",
        target_device="core-router-nyc-01",
        operation="restore_interface_admin_state",
        parameters={"interface": "ge-0/0/0"},
        risk=RiskLevel.HIGH,
    )
    approval = ApprovalDecision(
        approval_id="appr_ext",
        proposal_id=proposal.action_id,
        incident_id=proposal.incident_id,
        proposal_hash=proposal.canonical_hash,
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_test",
        reviewer_role=ReviewerRole.NETWORK_OPERATOR,
    )
    res = adapter.execute_remediation(proposal, approval)
    assert res.status == ExecutionStatus.FAILED
    assert "not an authorized containerlab node" in res.stderr.lower() or "unauthorized" in res.stderr.lower()


def test_kill_switch_active_blocks_all_remediation(adapter):
    proposal = RemediationProposal(
        action_id="act_kill_switch",
        incident_id="inc_ks",
        target="R2:eth1",
        target_device="R2",
        operation="restore_interface_admin_state",
        parameters={"interface": "eth1"},
        risk=RiskLevel.LOW,
    )
    approval = ApprovalDecision(
        approval_id="appr_ks",
        proposal_id=proposal.action_id,
        incident_id=proposal.incident_id,
        proposal_hash=proposal.canonical_hash,
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_test",
        reviewer_role=ReviewerRole.NETWORK_OPERATOR,
    )
    kill_switch.block_device(device_id="R2", reason="Safety test block R2")
    try:
        res = adapter.execute_remediation(proposal, approval)
        assert res.status == ExecutionStatus.FAILED
        assert "kill switch" in res.stderr.lower()
    finally:
        kill_switch.unblock_device(device_id="R2")

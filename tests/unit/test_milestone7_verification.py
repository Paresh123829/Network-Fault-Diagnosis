"""
test_milestone7_verification.py — Unit tests for Independent Post-Remediation Recovery Verification.
"""

import pytest

from network.containerlab.verification.recovery_verifier import ClabRecoveryVerifier
from network.containerlab.scenarios.registry import get_scenario
from network.containerlab.fault_injection.injector import FaultInjector
from network.containerlab.remediation.clab_adapter import ContainerlabRemediationAdapter
from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    RemediationProposal,
    ReviewerRole,
    RiskLevel,
    VerificationStatus,
)


@pytest.fixture
def verifier():
    return ClabRecoveryVerifier(force_mock=True)


@pytest.fixture
def injector():
    return FaultInjector(force_mock=True)


@pytest.fixture
def adapter():
    return ContainerlabRemediationAdapter(force_mock=True)


def test_bgp_recovery_verification(verifier, injector, adapter):
    sc = get_scenario("CLAB_SCENARIO_1_BGP")
    # 1. Fault injection
    injector.inject_fault(sc)
    # Check verification fails before remediation
    ver_pre = verifier.verify_scenario_recovery(sc, "exec_pre")
    assert ver_pre.success is False
    assert ver_pre.status == VerificationStatus.RECOVERY_FAILED

    # 2. Remediation execution
    proposal = RemediationProposal(
        action_id="act_bgp_ver",
        incident_id="inc_bgp_ver",
        target="R1:172.16.12.2",
        target_device="R1",
        operation="reset_bgp_session",
        parameters={"target_device": "R1", "peer_ip": "172.16.12.2"},
        risk=RiskLevel.MEDIUM,
    )
    approval = ApprovalDecision(
        approval_id="appr_bgp_ver",
        proposal_id=proposal.action_id,
        incident_id=proposal.incident_id,
        proposal_hash=proposal.canonical_hash,
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_test",
        reviewer_role=ReviewerRole.NETWORK_OPERATOR,
    )
    adapter.execute_remediation(proposal, approval)

    # 3. Independent recovery verification
    ver_post = verifier.verify_scenario_recovery(sc, "exec_post")
    assert ver_post.success is True
    assert ver_post.status == VerificationStatus.VERIFIED_RECOVERED
    assert any(c.check_id == "bgp_neighbor_established" and c.passed for c in ver_post.checks)


def test_vlan_recovery_verification(verifier, injector, adapter):
    sc = get_scenario("CLAB_SCENARIO_3_VLAN")
    injector.inject_fault(sc)

    proposal = RemediationProposal(
        action_id="act_vlan_ver",
        incident_id="inc_vlan_ver",
        target="br-vlan:eth3",
        target_device="br-vlan",
        operation="restore_vlan_membership",
        parameters={"target_device": "br-vlan", "target_interface": "eth3", "vlan_id": 100},
        risk=RiskLevel.LOW,
    )
    approval = ApprovalDecision(
        approval_id="appr_vlan_ver",
        proposal_id=proposal.action_id,
        incident_id=proposal.incident_id,
        proposal_hash=proposal.canonical_hash,
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_test",
        reviewer_role=ReviewerRole.NETWORK_OPERATOR,
    )
    adapter.execute_remediation(proposal, approval)

    ver_res = verifier.verify_scenario_recovery(sc, "exec_vlan_post")
    assert ver_res.success is True
    assert ver_res.status == VerificationStatus.VERIFIED_RECOVERED


"""
test_milestone6_executor.py — Unit tests for the Deterministic Simulated Executor.
"""

import pytest

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    ExecutionStatus,
    PolicyDecision,
    PolicyStatus,
    RemediationProposal,
    ReviewerRole,
    RiskLevel,
    VerificationStatus,
)
from services.ai.agents.oversight.approval_manager import approval_manager
from services.ai.agents.oversight.kill_switch import kill_switch
from automation.simulated_executor.state_manager import NetworkSimulatorStateManager
from automation.simulated_executor.executor import SimulatedRemediationExecutor


@pytest.fixture
def clean_simulator():
    sim = NetworkSimulatorStateManager()
    sim.initialize_default_cisco_clos()
    return sim


@pytest.fixture
def approved_bgp_proposal():
    prop = RemediationProposal(
        action_id="act_exec_bgp_1",
        incident_id="inc_bgp_exec",
        target="leaf1:10.0.1.1",
        target_device="leaf1",
        operation="reset_bgp_session",
        parameters={"target_device": "leaf1", "peer_ip": "10.0.1.1", "soft_reset": True},
        risk=RiskLevel.MEDIUM,
        expected_effect="Resets BGP",
        verification_condition="bgp_session_is_established",
        supporting_evidence_ids=["ev_bgp"],
        rollback_plan={"operation": "reconfigure_bgp_session", "parameters": {"target_device": "leaf1", "peer_ip": "10.0.1.1"}},
    )
    pol = PolicyDecision(
        decision_id="pol_exec_1",
        proposal_id=prop.action_id,
        status=PolicyStatus.ALLOWED_FOR_REVIEW,
        is_allowed=True,
    )
    req = approval_manager.create_request(prop, pol)
    decision = ApprovalDecision(
        approval_id="dec_exec_bgp",
        proposal_id=prop.action_id,
        incident_id=prop.incident_id,
        proposal_hash=prop.calculate_canonical_hash(),
        status=ApprovalStatus.APPROVED,
        reviewer_identity="operator_dave",
        reviewer_role=ReviewerRole.NOC_ENGINEER,
    )
    approval_manager.submit_decision(decision, prop)
    return prop, decision


class TestSimulatedRemediationExecutor:
    def setup_method(self):
        kill_switch.reset_all()
        approval_manager.reset_all()

    def teardown_method(self):
        kill_switch.reset_all()
        approval_manager.reset_all()

    def test_execute_bgp_session_reset(self, clean_simulator, approved_bgp_proposal):
        prop, decision = approved_bgp_proposal
        # Set session initially to IDLE in simulator
        clean_simulator.set_bgp_session_state("leaf1", "10.0.1.1", "IDLE")

        executor = SimulatedRemediationExecutor(sim=clean_simulator)
        exec_res, ver_res, rb_res = executor.execute_proposal(prop, decision)

        assert exec_res.status == ExecutionStatus.SUCCEEDED
        assert exec_res.pre_state_snapshot["bgp_sessions"]["leaf1"]["10.0.1.1"]["session_state"] == "IDLE"
        assert exec_res.post_state_snapshot["bgp_sessions"]["leaf1"]["10.0.1.1"]["session_state"] == "ESTABLISHED"
        assert ver_res.status == VerificationStatus.VERIFIED_RECOVERED
        assert ver_res.success is True
        assert rb_res is None

    def test_execute_interface_restoration(self, clean_simulator):
        prop = RemediationProposal(
            action_id="act_iface_exec_1",
            incident_id="inc_iface",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            target_interface="Ethernet1/1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Restores admin UP",
            verification_condition="interface_operational_state_is_up",
            supporting_evidence_ids=["ev_iface"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {"target_device": "leaf1", "target_interface": "Ethernet1/1"}},
        )
        pol = PolicyDecision(decision_id="pol_iface", proposal_id=prop.action_id, status=PolicyStatus.ALLOWED_FOR_REVIEW, is_allowed=True)
        approval_manager.create_request(prop, pol)
        decision = ApprovalDecision(
            approval_id="dec_iface",
            proposal_id=prop.action_id,
            incident_id=prop.incident_id,
            proposal_hash=prop.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="operator_eve",
            reviewer_role=ReviewerRole.NETWORK_OPERATOR,
        )
        approval_manager.submit_decision(decision, prop)

        # Set interface initially to DOWN
        clean_simulator.set_interface_admin_state("leaf1", "Ethernet1/1", "DOWN")

        executor = SimulatedRemediationExecutor(sim=clean_simulator)
        exec_res, ver_res, _ = executor.execute_proposal(prop, decision)

        assert exec_res.status == ExecutionStatus.SUCCEEDED
        assert ver_res.status == VerificationStatus.VERIFIED_RECOVERED
        assert ver_res.success is True
        assert clean_simulator.get_interface("leaf1", "Ethernet1/1")["admin_state"] == "UP"

    def test_execution_blocked_by_active_kill_switch(self, clean_simulator, approved_bgp_proposal):
        prop, decision = approved_bgp_proposal
        kill_switch.activate_global("Emergency freeze", actor="sec_ops")

        executor = SimulatedRemediationExecutor(sim=clean_simulator)
        exec_res, ver_res, _ = executor.execute_proposal(prop, decision)

        assert exec_res.status == ExecutionStatus.CANCELLED
        assert "Kill-switch active" in exec_res.stderr
        assert ver_res.status == VerificationStatus.NOT_VERIFIED

    def test_execution_blocked_without_human_approval(self, clean_simulator):
        prop = RemediationProposal(
            action_id="act_unapproved",
            incident_id="inc_unapp",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Unapproved action",
            verification_condition="none",
            supporting_evidence_ids=["ev_1"],
        )
        # Never submitted or approved
        executor = SimulatedRemediationExecutor(sim=clean_simulator)
        exec_res, ver_res, _ = executor.execute_proposal(prop, None)

        assert exec_res.status == ExecutionStatus.CANCELLED
        assert "Approval gate failure" in exec_res.stderr
        assert ver_res.status == VerificationStatus.NOT_VERIFIED


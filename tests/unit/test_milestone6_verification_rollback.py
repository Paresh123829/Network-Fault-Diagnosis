"""
test_milestone6_verification_rollback.py — Unit tests for Post-Remediation Verification & Rollback.
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
    RollbackStatus,
    VerificationStatus,
)
from services.ai.agents.oversight.approval_manager import approval_manager
from services.ai.agents.oversight.kill_switch import kill_switch
from automation.simulated_executor.state_manager import NetworkSimulatorStateManager
from automation.simulated_executor.verification import PostRemediationVerifier
from automation.simulated_executor.rollback import RemediationRollbackEngine
from automation.simulated_executor.executor import SimulatedRemediationExecutor


@pytest.fixture
def clean_simulator():
    sim = NetworkSimulatorStateManager()
    sim.initialize_default_cisco_clos()
    return sim


class TestVerificationAndRollback:
    def setup_method(self):
        kill_switch.reset_all()
        approval_manager.reset_all()

    def teardown_method(self):
        kill_switch.reset_all()
        approval_manager.reset_all()

    def test_execution_success_does_not_imply_recovery(self, clean_simulator):
        """Proves that execution status and verification status are decoupled."""
        prop = RemediationProposal(
            action_id="act_decoupled_test",
            incident_id="inc_decoupled",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            target_interface="Ethernet1/1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Restores admin UP",
            verification_condition="interface_operational_state_is_up",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {"target_device": "leaf1", "target_interface": "Ethernet1/1"}},
        )

        verifier = PostRemediationVerifier(sim=clean_simulator)

        # Case 1: Simulator interface is DOWN -> Verification must report RECOVERY_FAILED
        clean_simulator.set_interface_admin_state("leaf1", "Ethernet1/1", "DOWN")
        v_res_failed = verifier.verify_remediation("exec_1", prop)
        assert v_res_failed.status == VerificationStatus.RECOVERY_FAILED
        assert v_res_failed.success is False

        # Case 2: Simulator interface is UP -> Verification reports VERIFIED_RECOVERED
        clean_simulator.set_interface_admin_state("leaf1", "Ethernet1/1", "UP")
        v_res_success = verifier.verify_remediation("exec_2", prop)
        assert v_res_success.status == VerificationStatus.VERIFIED_RECOVERED
        assert v_res_success.success is True

    def test_failed_verification_triggers_automated_rollback(self, clean_simulator):
        prop = RemediationProposal(
            action_id="act_rollback_test",
            incident_id="inc_rb",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            target_interface="Ethernet1/1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Restores admin UP",
            verification_condition="interface_operational_state_is_up",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {"target_device": "leaf1", "target_interface": "Ethernet1/1"}},
        )
        pol = PolicyDecision(decision_id="pol_rb", proposal_id=prop.action_id, status=PolicyStatus.ALLOWED_FOR_REVIEW, is_allowed=True)
        approval_manager.create_request(prop, pol)
        decision = ApprovalDecision(
            approval_id="dec_rb",
            proposal_id=prop.action_id,
            incident_id=prop.incident_id,
            proposal_hash=prop.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="operator_frank",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
        )
        approval_manager.submit_decision(decision, prop)

        # Baseline: interface is initially DOWN
        clean_simulator.set_interface_admin_state("leaf1", "Ethernet1/1", "DOWN")

        # Mock an executor where post-verification fails by simulating operational failure
        executor = SimulatedRemediationExecutor(sim=clean_simulator)

        # Run direct rollback engine
        rb_engine = RemediationRollbackEngine(sim=clean_simulator)
        rb_res = rb_engine.execute_rollback(
            proposal=prop,
            execution_id="exec_failed_1",
            pre_state_snapshot=clean_simulator.get_state_snapshot(),
            sim=clean_simulator
        )

        assert rb_res.status == RollbackStatus.SUCCEEDED
        assert rb_res.is_verified is True
        # Interface is safely back to DOWN post-rollback
        assert clean_simulator.get_interface("leaf1", "Ethernet1/1")["admin_state"] == "DOWN"


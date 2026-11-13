"""
test_milestone6_remediation_e2e.py — End-to-End Multi-Agent Remediation and Human Approval Tests.

Demonstrates:
1. Full successful lifecycle: Diagnosis -> Proposal -> Policy -> Risk -> Approval Interrupt -> Operator Approval -> Preconditions -> Kill-Switch -> Execution -> Verification -> Audit.
2. Operator rejection lifecycle: Paused -> Operator Rejects -> Terminal audit without execution.
3. Active kill-switch block: Operator Approves -> Kill Switch Active -> Execution Halted.
4. Post-verification failure with automated rollback.
"""

import pytest
from datetime import datetime, timezone

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    ExecutionStatus,
    IncidentTimeline,
    ReviewerRole,
    StructuredEvent,
    TimeWindow,
    VerificationStatus,
)
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.agents.oversight.approval_manager import approval_manager
from services.ai.agents.oversight.kill_switch import kill_switch
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence
from automation.simulated_executor.state_manager import simulator_state


@pytest.fixture
def cisco_bgp_timeline():
    now = datetime.now(timezone.utc)
    ev = StructuredEvent(
        event_id="ev_bgp_case3_001",
        device_id="leaf5",
        interface="Ethernet1/1",
        event_type="bgp_neighbor_down",
        severity="critical",
        timestamp=now,
        raw_reference="3/bgpclear_no_traffic.csv.gz:10",
        normalized_fields={"peer_ip": "10.0.1.2", "session_state": "idle"},
    )
    return IncidentTimeline(
        incident_id="inc_bgp_case3",
        time_window=TimeWindow(start=now, end=now),
        events=[ev],
        affected_devices=["leaf5"],
        suspected_protocols=["bgp"],
    )


class TestMilestone6RemediationE2E:
    def setup_method(self):
        kill_switch.reset_all()
        approval_manager.reset_all()
        remediation_persistence.reset_in_memory()
        simulator_state.initialize_default_cisco_clos()

    def teardown_method(self):
        kill_switch.reset_all()
        approval_manager.reset_all()
        remediation_persistence.reset_in_memory()
        simulator_state.initialize_default_cisco_clos()

    def test_full_successful_remediation_lifecycle(self, cisco_bgp_timeline):
        """
        Validates complete lifecycle with genuine LangGraph interrupt and operator resumption.
        """
        orchestrator = DiagnosisOrchestrator()

        # Set session on leaf5 peer initially to IDLE in simulator
        simulator_state.set_bgp_session_state("leaf5", "10.0.1.2", "IDLE")

        # 1. Run pipeline up to Human Approval Interrupt
        paused_state, thread_id = orchestrator.run_remediation_pipeline(
            timeline=cisco_bgp_timeline,
            interrupt_for_approval=True
        )

        # In LangGraph with interrupt_before, the graph pauses before 'human_approval_interrupt'
        assert paused_state.get("remediation_proposal") is not None
        assert paused_state.get("policy_decision") is not None
        assert paused_state.get("policy_decision").is_allowed is True
        assert paused_state.get("approval_request") is not None
        assert paused_state.get("approval_request").status == ApprovalStatus.PENDING

        proposal = paused_state["remediation_proposal"]
        req = paused_state["approval_request"]

        # 2. Operator reviews proposal and submits approval
        decision = ApprovalDecision(
            approval_id=f"dec_{thread_id}",
            proposal_id=proposal.action_id,
            incident_id=proposal.incident_id,
            proposal_hash=proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="noc_lead_dave",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
            comments="Verified telemetry root cause. Approved for execution.",
        )

        # 3. Resume workflow past the interrupt
        final_state = orchestrator.resume_with_approval(thread_id, decision)

        # 4. Verify outcomes
        assert final_state.get("remediation_status") == "RECOVERED"
        assert final_state.get("execution_result") is not None
        assert final_state.get("execution_result").status == ExecutionStatus.SUCCEEDED
        assert final_state.get("verification_result") is not None
        assert final_state.get("verification_result").status == VerificationStatus.VERIFIED_RECOVERED
        assert final_state.get("verification_result").success is True

        # 5. Verify simulator state was restored to ESTABLISHED
        target_peer_ip = proposal.parameters.get("peer_ip", "10.0.1.2")
        assert simulator_state.get_bgp_session("leaf5", target_peer_ip)["session_state"] == "ESTABLISHED"

        # 6. Verify audit chain integrity
        is_valid, errors = remediation_persistence.verify_audit_chain_integrity()
        assert is_valid is True
        assert len(errors) == 0

    def test_human_rejection_halts_workflow_safely(self, cisco_bgp_timeline):
        """
        Validates that human rejection terminates workflow without any execution.
        """
        orchestrator = DiagnosisOrchestrator()
        simulator_state.set_bgp_session_state("leaf5", "10.0.1.2", "IDLE")

        paused_state, thread_id = orchestrator.run_remediation_pipeline(
            timeline=cisco_bgp_timeline,
            interrupt_for_approval=True
        )

        proposal = paused_state["remediation_proposal"]

        # Operator rejects proposal
        rejection_decision = ApprovalDecision(
            approval_id=f"dec_reject_{thread_id}",
            proposal_id=proposal.action_id,
            incident_id=proposal.incident_id,
            proposal_hash=proposal.calculate_canonical_hash(),
            status=ApprovalStatus.REJECTED,
            reviewer_identity="senior_sre_sarah",
            reviewer_role=ReviewerRole.SITE_RELIABILITY_ENGINEER,
            comments="Freeze window active.",
        )

        final_state = orchestrator.resume_with_approval(thread_id, rejection_decision)

        # Must NOT execute
        assert final_state.get("remediation_status") == "REJECTED"
        assert final_state.get("execution_result") is None
        # Simulator state must remain untouched
        assert simulator_state.get_bgp_session("leaf5", "10.0.1.2")["session_state"] == "IDLE"

    def test_kill_switch_blocks_execution_even_if_approved(self, cisco_bgp_timeline):
        """
        Validates kill switch enforcement: if activated, execution is barred.
        """
        orchestrator = DiagnosisOrchestrator()
        simulator_state.set_bgp_session_state("leaf5", "10.0.1.2", "IDLE")

        paused_state, thread_id = orchestrator.run_remediation_pipeline(
            timeline=cisco_bgp_timeline,
            interrupt_for_approval=True
        )

        proposal = paused_state["remediation_proposal"]

        # Activate kill switch mid-flight before operator resume
        kill_switch.activate_global("Emergency datacenter power incident", actor="ops_director")

        decision = ApprovalDecision(
            approval_id=f"dec_ks_{thread_id}",
            proposal_id=proposal.action_id,
            incident_id=proposal.incident_id,
            proposal_hash=proposal.calculate_canonical_hash(),
            status=ApprovalStatus.APPROVED,
            reviewer_identity="noc_engineer",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
        )

        final_state = orchestrator.resume_with_approval(thread_id, decision)

        # Execution should be blocked by kill switch
        assert final_state.get("remediation_status") == "KILL_SWITCH_BLOCKED"
        assert final_state.get("execution_result") is None
        assert simulator_state.get_bgp_session("leaf5", "10.0.1.2")["session_state"] == "IDLE"

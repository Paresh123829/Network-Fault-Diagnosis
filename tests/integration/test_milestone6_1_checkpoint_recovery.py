"""
Integration tests for Milestone 6.1 durable LangGraph checkpoint recovery and restart reconciliation.
"""

from datetime import datetime, timezone, timedelta
import os
import tempfile
import pytest

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    IncidentTimeline,
    ReviewerRole,
    StructuredEvent,
    TimeWindow,
)
from services.ai.orchestrator.checkpointer import FileCheckpointSaver
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.agents.oversight.checkpoint_recovery import (
    RemediationRestartRecoveryManager,
    WorkflowRecoveryStatus,
)
from services.ai.agents.oversight.kill_switch import kill_switch
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence


@pytest.fixture
def sample_timeline():
    now = datetime.now(timezone.utc)
    ev = StructuredEvent(
        event_id="ev_bgp_001",
        timestamp=now,
        device_id="leaf5",
        event_type="bgp_neighbor_down",
        severity="critical",
        protocol_hint="bgp",
        message="BGP session 10.0.1.2 down",
        raw_reference="3/bgpclear_no_traffic.csv.gz:10",
        attributes={"neighbor": "10.0.1.2", "state": "IDLE"}
    )
    return IncidentTimeline(
        incident_id="inc_recover_bgp_01",
        events=[ev],
        time_window=TimeWindow(start=now - timedelta(minutes=5), end=now),
        target_device="leaf5",
        affected_devices=["leaf5"],
    )


def test_crash_recovery_during_approval_wait(sample_timeline):
    """
    Scenario 1: Workflow interrupts for approval, application process crashes,
    new process starts, re-loads persistent checkpoint, validates decision, and resumes safely.
    """
    with tempfile.TemporaryDirectory() as td:
        cp_file = os.path.join(td, "workflow_state.pkl")
        thread_id = "thread_crash_test_01"

        # ─── Process 1: Start workflow and pause at approval interrupt ────────
        cp1 = FileCheckpointSaver(filepath=cp_file)
        orch1 = DiagnosisOrchestrator(checkpointer=cp1)

        state1, th_id = orch1.run_remediation_pipeline(
            timeline=sample_timeline,
            thread_id=thread_id,
            interrupt_for_approval=True,
        )

        assert state1.get("remediation_status") == "AWAITING_APPROVAL"
        proposal = state1.get("remediation_proposal")
        assert proposal is not None
        assert proposal.action_id.startswith("act_")

        # Simulate process crash: destroy orchestrator 1
        del orch1
        del cp1

        # ─── Process 2: Recover workflow in fresh instance ─────────────────────
        cp2 = FileCheckpointSaver(filepath=cp_file)
        orch2 = DiagnosisOrchestrator(checkpointer=cp2)

        # Inspect thread state
        recovered_state = orch2.get_thread_state(thread_id)
        assert recovered_state is not None
        recovered_prop = recovered_state.get("remediation_proposal")
        assert recovered_prop.action_id == proposal.action_id
        assert recovered_prop.canonical_hash == proposal.canonical_hash

        # Reconcile status before decision
        rec_mgr = RemediationRestartRecoveryManager()
        report_before = rec_mgr.inspect_and_classify_workflow(thread_id, recovered_state)
        assert report_before.recovery_status == WorkflowRecoveryStatus.WAITING_FOR_APPROVAL

        # Submit valid decision and resume
        dec = ApprovalDecision(
            approval_id="dec_crash_test_01",
            proposal_id=recovered_prop.action_id,
            incident_id=recovered_prop.incident_id,
            proposal_hash=recovered_prop.canonical_hash,
            status=ApprovalStatus.APPROVED,
            reviewer_identity="sre_operator",
            reviewer_role=ReviewerRole.SITE_RELIABILITY_ENGINEER,
            comments="Approved after simulated restart.",
        )

        final_state = orch2.recover_and_resume_workflow(thread_id, decision=dec)
        assert final_state.get("remediation_status") in ("RECOVERED", "VERIFIED_RECOVERED", "RECOVERY_FAILED")
        assert final_state.get("execution_result") is not None


def test_recovery_blocks_expired_proposal(sample_timeline):
    """
    Scenario: Proposal expires while application was offline.
    Restart recovery must detect expiration and refuse to resume.
    """
    with tempfile.TemporaryDirectory() as td:
        cp_file = os.path.join(td, "workflow_state_exp.pkl")
        thread_id = "thread_exp_01"

        cp = FileCheckpointSaver(filepath=cp_file)
        orch = DiagnosisOrchestrator(checkpointer=cp)
        state, _ = orch.run_remediation_pipeline(sample_timeline, thread_id=thread_id)

        # Force expiration on proposal
        prop = state["remediation_proposal"]
        prop.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        state["remediation_proposal"] = prop

        rec_mgr = RemediationRestartRecoveryManager()
        report = rec_mgr.inspect_and_classify_workflow(thread_id, state)
        assert report.can_resume is False
        assert report.recovery_status == WorkflowRecoveryStatus.EXPIRED


def test_recovery_blocks_tampered_proposal_hash(sample_timeline):
    """
    Scenario: Proposal parameter modified during downtime.
    Hash mismatch must fail closed to MANUAL_INTERVENTION_REQUIRED.
    """
    with tempfile.TemporaryDirectory() as td:
        cp_file = os.path.join(td, "workflow_state_tamper.pkl")
        thread_id = "thread_tamper_01"

        cp = FileCheckpointSaver(filepath=cp_file)
        orch = DiagnosisOrchestrator(checkpointer=cp)
        state, _ = orch.run_remediation_pipeline(sample_timeline, thread_id=thread_id)

        prop = state["remediation_proposal"]
        # Fake approval with old hash
        dec = ApprovalDecision(
            approval_id="dec_tamper_01",
            proposal_id=prop.action_id,
            incident_id=prop.incident_id,
            proposal_hash="tampered_different_hash_value",
            status=ApprovalStatus.APPROVED,
            reviewer_identity="admin",
            reviewer_role=ReviewerRole.SITE_RELIABILITY_ENGINEER,
        )
        state["approval_decision"] = dec

        rec_mgr = RemediationRestartRecoveryManager()
        report = rec_mgr.inspect_and_classify_workflow(thread_id, state)
        assert report.can_resume is False
        assert report.recovery_status == WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED
        assert "hash mismatch" in report.rejection_reason


def test_recovery_blocks_when_kill_switch_active(sample_timeline):
    """
    Scenario 8: Global kill switch activated while application restarts.
    """
    with tempfile.TemporaryDirectory() as td:
        cp_file = os.path.join(td, "workflow_state_ks.pkl")
        thread_id = "thread_ks_01"

        cp = FileCheckpointSaver(filepath=cp_file)
        orch = DiagnosisOrchestrator(checkpointer=cp)
        state, _ = orch.run_remediation_pipeline(sample_timeline, thread_id=thread_id)
        prop = state["remediation_proposal"]

        dec = ApprovalDecision(
            approval_id="dec_ks_01",
            proposal_id=prop.action_id,
            incident_id=prop.incident_id,
            proposal_hash=prop.canonical_hash,
            status=ApprovalStatus.APPROVED,
            reviewer_identity="admin",
            reviewer_role=ReviewerRole.SITE_RELIABILITY_ENGINEER,
        )
        state["approval_decision"] = dec

        # Activate kill switch
        kill_switch.activate_global("Emergency stop", actor="test_runner")
        try:
            rec_mgr = RemediationRestartRecoveryManager()
            report = rec_mgr.inspect_and_classify_workflow(thread_id, state)
            assert report.can_resume is False
            assert report.recovery_status == WorkflowRecoveryStatus.MANUAL_INTERVENTION_REQUIRED
            assert "Kill switch active" in report.rejection_reason
        finally:
            kill_switch.reset_all()

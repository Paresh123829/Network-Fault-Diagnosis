"""
Integration tests for Milestone 6.1 crash-after-execution idempotency and reconciliation.
"""

from datetime import datetime, timezone, timedelta
import os
import tempfile
import pytest

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    ExecutionResult,
    ExecutionStatus,
    IncidentTimeline,
    RemediationProposal,
    ReviewerRole,
    RiskLevel,
    StructuredEvent,
    TimeWindow,
)
from services.ai.orchestrator.checkpointer import FileCheckpointSaver
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.agents.oversight.checkpoint_recovery import (
    RemediationRestartRecoveryManager,
    WorkflowRecoveryStatus,
)
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence


def test_crash_after_execution_prevents_duplicate_run():
    """
    Scenario 3: Application terminates immediately after execution succeeds, before verification.
    On restart, the system detects that execution already occurred and prevents duplicate execution.
    """
    with tempfile.TemporaryDirectory() as td:
        cp_file = os.path.join(td, "checkpoints_idemp.pkl")
        thread_id = "thread_idemp_01"

        cp = FileCheckpointSaver(filepath=cp_file)
        orch = DiagnosisOrchestrator(checkpointer=cp)

        now = datetime.now(timezone.utc)
        prop = RemediationProposal(
            action_id="prop_idemp_01",
            incident_id="inc_idemp",
            target="leaf5:10.0.1.2",
            target_device="leaf5",
            operation="reset_bgp_session",
            parameters={"target_device": "leaf5", "peer_ip": "10.0.1.2", "soft_reset": True},
            risk=RiskLevel.MEDIUM,
            expected_effect="Test",
            verification_condition="none",
        )

        dec = ApprovalDecision(
            approval_id="dec_idemp_01",
            proposal_id=prop.action_id,
            incident_id=prop.incident_id,
            proposal_hash=prop.canonical_hash,
            status=ApprovalStatus.APPROVED,
            reviewer_identity="operator",
            reviewer_role=ReviewerRole.NOC_ENGINEER,
        )

        # Simulate checkpoint containing proposal and approval
        checkpoint_state = {
            "incident_id": "inc_idemp",
            "remediation_proposal": prop,
            "approval_decision": dec,
            "execution_trace": ["Init: started"],
        }

        # Simulate that execution was already persisted in MongoDB/memory prior to crash
        exec_res = ExecutionResult(
            execution_id="exec_idemp_01",
            proposal_id=prop.action_id,
            approval_id=dec.approval_id,
            operation=prop.operation,
            target_device=prop.target_device,
            status=ExecutionStatus.SUCCEEDED,
            started_at=now - timedelta(seconds=10),
            completed_at=now - timedelta(seconds=8),
        )
        remediation_persistence.save_execution_result(exec_res, incident_id="inc_idemp")

        # Reconcile on restart
        rec_mgr = RemediationRestartRecoveryManager(persistence=remediation_persistence)
        report = rec_mgr.inspect_and_classify_workflow(thread_id, checkpoint_state)

        assert report.has_executed is True
        assert report.execution_id == "exec_idemp_01"
        assert report.recovery_status == WorkflowRecoveryStatus.EXECUTION_COMPLETED_PENDING_VERIFICATION
        assert report.can_resume is True


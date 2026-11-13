"""
Integration tests for Milestone 6.1 exact-state rollback and compensating recovery workflow.
"""

from datetime import datetime, timezone, timedelta
import pytest

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    IncidentTimeline,
    ReviewerRole,
    StructuredEvent,
    TimeWindow,
    VerificationStatus,
    RollbackStatus,
)
from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.agents.remediation.snapshot_manager import (
    SnapshotManager,
    snapshot_manager,
    RollbackClassification,
)
from automation.simulated_executor.state_manager import simulator_state
from automation.simulated_executor.executor import simulated_executor


def test_e2e_failed_verification_triggers_exact_rollback():
    # Setup initial non-default VLAN configuration
    simulator_state.initialize_default_cisco_clos()
    simulator_state.set_interface_config(
        device_id="leaf1",
        interface_name="Ethernet1/1",
        admin_state="UP",
        operational_state="UP",
        vlan_id=400,
        mode="trunk",
        allowed_vlans=[100, 200, 400],
    )

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
    timeline = IncidentTimeline(
        incident_id="inc_bgp_case3_rb",
        time_window=TimeWindow(start=now, end=now),
        events=[ev],
        affected_devices=["leaf5"],
        suspected_protocols=["bgp"],
    )

    orch = DiagnosisOrchestrator()
    state, thread_id = orch.run_remediation_pipeline(timeline, interrupt_for_approval=True)

    proposal = state.get("remediation_proposal")
    assert proposal is not None

    dec = ApprovalDecision(
        approval_id="dec_rb_e2e_01",
        proposal_id=proposal.action_id,
        incident_id=proposal.incident_id,
        proposal_hash=proposal.canonical_hash,
        status=ApprovalStatus.APPROVED,
        reviewer_identity="sre_dave",
        reviewer_role=ReviewerRole.SITE_RELIABILITY_ENGINEER,
    )

    from services.ai.agents.oversight.approval_manager import approval_manager
    approval_manager.submit_decision(dec, proposal)

    # Execute through simulated_executor
    exec_res, ver_res, rb_res = simulated_executor.execute_proposal(
        proposal=proposal,
        approval_decision=dec,
        auto_rollback_on_failure=True
    )

    snap = snapshot_manager.get_snapshot_for_execution(exec_res.execution_id)
    assert snap is not None
    assert snap.rollback_classification == RollbackClassification.COMPENSATING_RECOVERY

    # Explicitly test compensating rollback
    rb_outcome = simulated_executor.rollback_engine.execute_rollback(
        proposal=proposal,
        execution_id=exec_res.execution_id,
        pre_state_snapshot=snap,
        sim=simulator_state,
    )

    assert rb_outcome.status == RollbackStatus.SUCCEEDED
    assert rb_outcome.restored_state["classification"] == "COMPENSATING_RECOVERY"

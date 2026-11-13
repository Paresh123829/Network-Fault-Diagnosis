"""
executor.py — Deterministic Simulated Remediation Executor.

Coordinates pre-execution validation, approval gate enforcement, kill-switch checks,
in-memory execution, post-action verification, and conditional rollback.
NEVER connects to real devices, physical switches, or production network environments.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import uuid

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ExecutionResult,
    ExecutionStatus,
    RemediationProposal,
    RollbackResult,
    RollbackStatus,
    VerificationResult,
    VerificationStatus,
)
from services.ai.agents.oversight.gate import human_approval_gate, HumanApprovalGate
from services.ai.agents.oversight.kill_switch import kill_switch, KillSwitchManager
from services.ai.agents.oversight.approval_manager import approval_manager, ApprovalManager
try:
    from .state_manager import NetworkSimulatorStateManager, simulator_state
    from .operations import OPERATION_HANDLERS
    from .verification import PostRemediationVerifier, post_remediation_verifier
    from .rollback import RemediationRollbackEngine, rollback_engine
except ImportError:
    from state_manager import NetworkSimulatorStateManager, simulator_state
    from operations import OPERATION_HANDLERS
    from verification import PostRemediationVerifier, post_remediation_verifier
    from rollback import RemediationRollbackEngine, rollback_engine

logger = logging.getLogger(__name__)


class SimulatedRemediationExecutor:
    """
    Deterministic simulated network execution engine.
    Applies bounded, approved remediation operations exclusively to simulated state.
    """

    def __init__(
        self,
        sim: Optional[NetworkSimulatorStateManager] = None,
        approval_gate: Optional[HumanApprovalGate] = None,
        ks: Optional[KillSwitchManager] = None,
        verifier: Optional[PostRemediationVerifier] = None,
        rb: Optional[RemediationRollbackEngine] = None,
    ) -> None:
        self.sim = sim or simulator_state
        self.approval_gate = approval_gate or human_approval_gate
        self.kill_switch = ks or kill_switch
        self.verifier = verifier or post_remediation_verifier
        self.rollback_engine = rb or rollback_engine

    def execute_proposal(
        self,
        proposal: RemediationProposal,
        approval_decision: Optional[ApprovalDecision] = None,
        auto_rollback_on_failure: bool = True,
    ) -> Tuple[ExecutionResult, VerificationResult, Optional[RollbackResult]]:
        """
        Executes an approved remediation proposal end-to-end:
        1. Precondition & target check
        2. Approval gate verification
        3. Kill-switch check
        4. State snapshot
        5. Handler dispatch
        6. Post-state snapshot
        7. Verification
        8. Conditional Rollback
        """
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        target_dev = proposal.target_device or proposal.target.split(":")[0]

        # 1. Approval Gate Check
        approved, gate_reason, req = self.approval_gate.evaluate_gate(proposal, approval_decision)
        if not approved:
            logger.warning(f"Execution rejected by approval gate: {gate_reason}")
            res = ExecutionResult(
                execution_id=execution_id,
                proposal_id=proposal.action_id,
                approval_id=req.request_id if req else "none",
                operation=proposal.operation,
                target_device=target_dev,
                status=ExecutionStatus.CANCELLED,
                started_at=now,
                completed_at=now,
                pre_state_snapshot={},
                post_state_snapshot={},
                stdout="",
                stderr=f"Approval gate failure: {gate_reason}",
                details={"gate_reason": gate_reason},
            )
            v_res = VerificationResult(
                verification_id=f"ver_{uuid.uuid4().hex[:12]}",
                execution_id=execution_id,
                status=VerificationStatus.NOT_VERIFIED,
                success=False,
                failure_reason="Execution halted by approval gate.",
            )
            return res, v_res, None

        # 2. Kill-Switch Check
        can_run, ks_reason = self.kill_switch.can_execute(
            operation=proposal.operation,
            target_device=target_dev,
            agent_name="simulated_executor"
        )
        if not can_run:
            logger.critical(f"Execution halted by kill switch: {ks_reason}")
            res = ExecutionResult(
                execution_id=execution_id,
                proposal_id=proposal.action_id,
                approval_id=req.request_id if req else "none",
                operation=proposal.operation,
                target_device=target_dev,
                status=ExecutionStatus.CANCELLED,
                started_at=now,
                completed_at=now,
                pre_state_snapshot={},
                post_state_snapshot={},
                stdout="",
                stderr=f"Kill-switch active: {ks_reason}",
                details={"kill_switch_reason": ks_reason},
            )
            v_res = VerificationResult(
                verification_id=f"ver_{uuid.uuid4().hex[:12]}",
                execution_id=execution_id,
                status=VerificationStatus.NOT_VERIFIED,
                success=False,
                failure_reason="Execution halted by kill switch.",
            )
            return res, v_res, None

        # 3. Preconditions & Target Verification on Simulator
        if not self.sim.has_device(target_dev):
            logger.error(f"Target device '{target_dev}' missing from simulation.")
            res = ExecutionResult(
                execution_id=execution_id,
                proposal_id=proposal.action_id,
                approval_id=req.request_id if req else "none",
                operation=proposal.operation,
                target_device=target_dev,
                status=ExecutionStatus.FAILED,
                started_at=now,
                completed_at=now,
                pre_state_snapshot={},
                post_state_snapshot={},
                stdout="",
                stderr=f"Precondition failure: target device '{target_dev}' does not exist in simulation.",
                details={"error": "device_not_found"},
            )
            v_res = VerificationResult(
                verification_id=f"ver_{uuid.uuid4().hex[:12]}",
                execution_id=execution_id,
                status=VerificationStatus.RECOVERY_FAILED,
                success=False,
                failure_reason="Target device missing.",
            )
            return res, v_res, None

        # 4. Capture Immutable Pre-Execution State Snapshot
        from services.ai.agents.remediation.snapshot_manager import snapshot_manager
        typed_snapshot = snapshot_manager.capture_pre_execution_snapshot(self.sim, proposal, execution_id)
        pre_snapshot = self.sim.get_state_snapshot()
        pre_snapshot["snapshot_id"] = typed_snapshot.snapshot_id
        pre_snapshot["snapshot_hash"] = typed_snapshot.snapshot_hash

        # 5. Execute Registered Operation Handler
        handler = OPERATION_HANDLERS.get(proposal.operation)
        if not handler:
            logger.critical(f"Security invariant broken: Unregistered handler for '{proposal.operation}' reached executor!")
            res = ExecutionResult(
                execution_id=execution_id,
                proposal_id=proposal.action_id,
                approval_id=req.request_id if req else "none",
                operation=proposal.operation,
                target_device=target_dev,
                status=ExecutionStatus.FAILED,
                started_at=now,
                completed_at=datetime.now(timezone.utc),
                pre_state_snapshot=pre_snapshot,
                post_state_snapshot=pre_snapshot,
                stdout="",
                stderr=f"Unknown operation handler: {proposal.operation}",
            )
            v_res = VerificationResult(
                verification_id=f"ver_{uuid.uuid4().hex[:12]}",
                execution_id=execution_id,
                status=VerificationStatus.RECOVERY_FAILED,
                success=False,
                failure_reason="Handler missing.",
            )
            return res, v_res, None

        exec_start = datetime.now(timezone.utc)
        success, msg, post_details = handler(self.sim, proposal.parameters)
        exec_end = datetime.now(timezone.utc)

        # 6. Mark Proposal as Executed (Anti-Replay)
        approval_manager.mark_executed(proposal.action_id)

        # 7. Capture Post-Execution State Snapshot
        post_snapshot = self.sim.get_state_snapshot()

        exec_status = ExecutionStatus.SUCCEEDED if success else ExecutionStatus.FAILED
        execution_result = ExecutionResult(
            execution_id=execution_id,
            proposal_id=proposal.action_id,
            approval_id=req.request_id if req else "none",
            operation=proposal.operation,
            target_device=target_dev,
            status=exec_status,
            started_at=exec_start,
            completed_at=exec_end,
            pre_state_snapshot=pre_snapshot,
            post_state_snapshot=post_snapshot,
            stdout=msg if success else "",
            stderr="" if success else msg,
            details=post_details,
        )

        # 8. Post-Remediation Verification
        verification_result = self.verifier.verify_remediation(
            execution_id=execution_id,
            proposal=proposal,
            sim=self.sim
        )

        # 9. Automated Rollback if verification failed
        rollback_result: Optional[RollbackResult] = None
        if not verification_result.success and auto_rollback_on_failure:
            logger.warning(
                f"[TRIGGERING ROLLBACK] Verification failed for {proposal.action_id} ({verification_result.failure_reason}). "
                "Executing automated rollback."
            )
            rollback_result = self.rollback_engine.execute_rollback(
                proposal=proposal,
                execution_id=execution_id,
                pre_state_snapshot=pre_snapshot,
                sim=self.sim
            )

        return execution_result, verification_result, rollback_result


# Global singleton instance
simulated_executor = SimulatedRemediationExecutor()

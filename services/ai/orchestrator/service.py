"""
service.py — High-Level Diagnosis & Safe Remediation Orchestration Service.

Executes the LangGraph StateGraph diagnosis and remediation workflows with checkpointing,
interrupt-and-resume human approval gates, error handling, and execution tracing.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from langgraph.checkpoint.memory import MemorySaver

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    DiagnosisResult,
    IncidentTimeline,
    RemediationProposal,
    ReviewerRole,
)
from services.ai.agents.oversight.approval_manager import approval_manager
from services.ai.agents.oversight.checkpoint_recovery import restart_recovery_manager, WorkflowRecoveryStatus
from .checkpointer import get_persistent_checkpointer
from .graph import build_diagnosis_graph, build_remediation_graph
from .state import IncidentState

logger = logging.getLogger(__name__)


class DiagnosisOrchestrator:
    """
    Orchestrates the multi-agent diagnostic and safe remediation pipeline using LangGraph.
    """

    def __init__(
        self,
        checkpointer: Optional[Any] = None,
        enable_remediation: bool = False,
    ):
        if checkpointer is not None:
            self.checkpointer = checkpointer
        else:
            self.checkpointer = get_persistent_checkpointer("auto")

        self.diagnosis_app = build_diagnosis_graph(checkpointer=self.checkpointer, enable_remediation=False)
        self.app = self.diagnosis_app
        self.remediation_app = build_remediation_graph(checkpointer=self.checkpointer, interrupt_for_approval=True)
        self.remediation_direct_app = build_remediation_graph(checkpointer=self.checkpointer, interrupt_for_approval=False)

    def diagnose_incident(
        self,
        timeline: IncidentTimeline,
        context_id: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the diagnosis StateGraph end-to-end for a given IncidentTimeline.
        Returns the final state containing DiagnosisResult, SymptomAnalysisReport,
        TopologyContext, and execution trace.
        """
        th_id = thread_id or f"thread_{timeline.incident_id}_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": th_id}}

        initial_state: IncidentState = {
            "incident_id": timeline.incident_id,
            "timeline": timeline,
            "context_id": context_id,
            "enable_remediation": False,
            "execution_trace": [f"Init: Started diagnosis workflow for incident {timeline.incident_id}"]
        }

        logger.info(f"Invoking LangGraph diagnosis graph on thread '{th_id}'...")
        final_state = self.diagnosis_app.invoke(initial_state, config=config)
        logger.info(f"LangGraph diagnosis graph completed with {len(final_state.get('execution_trace', []))} trace steps.")

        return final_state

    def run_remediation_pipeline(
        self,
        timeline: IncidentTimeline,
        context_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        interrupt_for_approval: bool = True
    ) -> Tuple[Dict[str, Any], str]:
        """
        Executes diagnosis through remediation proposal and pauses at the approval gate
        (if interrupt_for_approval=True). Returns (current_state, thread_id).
        """
        th_id = thread_id or f"thread_{timeline.incident_id}_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": th_id}}

        initial_state: IncidentState = {
            "incident_id": timeline.incident_id,
            "timeline": timeline,
            "context_id": context_id,
            "enable_remediation": True,
            "execution_trace": [f"Init: Started remediation workflow for incident {timeline.incident_id}"]
        }

        app = self.remediation_app if interrupt_for_approval else self.remediation_direct_app
        logger.info(f"Invoking remediation workflow on thread '{th_id}' (interrupt={interrupt_for_approval})...")
        state = app.invoke(initial_state, config=config)
        return state, th_id

    def resume_with_approval(
        self,
        thread_id: str,
        decision: ApprovalDecision,
    ) -> Dict[str, Any]:
        """
        Submits human reviewer decision and resumes the paused LangGraph workflow past the interrupt.
        """
        config = {"configurable": {"thread_id": thread_id}}
        current_state = self.remediation_app.get_state(config)

        if not current_state:
            raise ValueError(f"No checkpointed state found for thread_id '{thread_id}'.")

        proposal: Optional[RemediationProposal] = current_state.values.get("remediation_proposal")
        if not proposal:
            raise ValueError("No active remediation proposal found in checkpointed state.")

        # Record decision in approval manager
        success, msg, req = approval_manager.submit_decision(decision, proposal)
        if not success:
            raise ValueError(f"Approval rejected: {msg}")

        # Update thread state with decision and resume
        self.remediation_app.update_state(
            config,
            {
                "approval_decision": decision,
                "remediation_status": decision.status.value.upper(),
            }
        )

        logger.info(f"Resuming workflow on thread '{thread_id}' with decision '{decision.status.value}'...")
        final_state = self.remediation_app.invoke(None, config=config)
        return final_state

    def get_thread_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves checkpointed state on a thread."""
        config = {"configurable": {"thread_id": thread_id}}
        st = self.remediation_app.get_state(config)
        return st.values if st else None

    def recover_and_resume_workflow(
        self,
        thread_id: str,
        decision: Optional[ApprovalDecision] = None,
    ) -> Dict[str, Any]:
        """
        Reconciles interrupted workflow state after application restart.
        Evaluates recovery status, revalidates approval, expiry, and idempotency,
        and safely resumes or fails closed.
        """
        state_vals = self.get_thread_state(thread_id)
        report = restart_recovery_manager.inspect_and_classify_workflow(
            thread_id=thread_id,
            checkpoint_state=state_vals,
            incoming_decision=decision
        )

        logger.info(f"[RECOVERY INSPECTION] Thread '{thread_id}' status: {report.recovery_status.value} (can_resume={report.can_resume})")

        if not report.can_resume:
            return {
                "thread_id": thread_id,
                "recovery_status": report.recovery_status.value,
                "resumed": False,
                "error": report.rejection_reason,
            }

        if report.recovery_status == WorkflowRecoveryStatus.EXECUTION_COMPLETED_PENDING_VERIFICATION:
            # Execution already completed prior to crash; avoid double-execution
            config = {"configurable": {"thread_id": thread_id}}
            self.remediation_app.update_state(
                config,
                {
                    "remediation_status": "RECOVERED_POST_EXECUTION",
                    "execution_trace": list(state_vals.get("execution_trace", [])) + [
                        f"RestartRecovery: Reconciled thread '{thread_id}', skipping duplicate execution {report.execution_id}."
                    ]
                }
            )
            # Advance to verification/audit
            return self.remediation_app.invoke(None, config=config)

        # Standard approved resumption
        if decision:
            return self.resume_with_approval(thread_id, decision)
        elif state_vals and state_vals.get("approval_decision"):
            existing_dec = state_vals.get("approval_decision")
            dec_obj = existing_dec if isinstance(existing_dec, ApprovalDecision) else ApprovalDecision(**existing_dec)
            return self.resume_with_approval(thread_id, dec_obj)
        else:
            return {
                "thread_id": thread_id,
                "recovery_status": WorkflowRecoveryStatus.WAITING_FOR_APPROVAL.value,
                "resumed": False,
                "error": "No approval decision available to resume workflow.",
            }

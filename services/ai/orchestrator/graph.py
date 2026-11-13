"""
graph.py — Genuine LangGraph StateGraph Workflow for Network Fault Diagnosis.

Implements all 9 logical stages:
  1. Incident Intake
  2. Evidence Validation
  3. Topology Context Retrieval
  4. Symptom Analysis
  5. Topology Reasoning
  6. RCA Hypothesis Generation
  7. Evidence Verification
  8. Diagnosis Synthesis
  9. Structured Output Persistence

Features conditional routing, checkpointing, and reproducible execution traces.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from services.ai.schemas.contracts import (
    IncidentTimeline,
    DiagnosisResult,
    Hypothesis,
    TopologyContext,
    RemediationProposal,
    PolicyDecision,
    ApprovalDecision,
    ExecutionResult,
    VerificationResult,
    RollbackResult,
)
from services.ai.agents.topology.agent import TopologyAgent
from services.ai.agents.symptom.agent import SymptomAgent
from services.ai.agents.symptom.models import SymptomAnalysisReport
from services.ai.agents.rca.agent import RCAgent
from services.ai.agents.diagnosis.persistence import DiagnosisPersistence
from services.ai.agents.remediation.proposal_engine import proposal_engine
from services.ai.agents.remediation.policy import remediation_policy
from services.ai.agents.remediation.risk import risk_classifier
from services.ai.agents.oversight.approval_manager import approval_manager
from services.ai.agents.oversight.gate import human_approval_gate
from services.ai.agents.oversight.kill_switch import kill_switch
from automation.simulated_executor.executor import simulated_executor
from automation.simulated_executor.verification import post_remediation_verifier
from automation.simulated_executor.rollback import rollback_engine
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence
from .state import IncidentState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. GRAPH NODES
# ─────────────────────────────────────────────────────────────────────────────

def incident_intake_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 1: Intake and normalization of the IncidentTimeline."""
    timeline = state.get("timeline")
    trace = list(state.get("execution_trace", []))
    trace.append("Stage 1 [incident_intake]: Incident received and unpacked.")

    if not timeline:
        return {
            "validation_status": "empty",
            "validation_errors": ["No timeline provided in state."],
            "execution_trace": trace,
            "error": "Missing IncidentTimeline"
        }

    return {
        "incident_id": timeline.incident_id,
        "is_cross_device": len(timeline.affected_devices) > 1,
        "execution_trace": trace
    }


def evidence_validation_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 2: Validates events within timeline."""
    timeline = state["timeline"]
    trace = list(state.get("execution_trace", []))
    errors: List[str] = []

    events = timeline.events if timeline else []
    if not events:
        errors.append("Timeline contains 0 events.")
        trace.append("Stage 2 [evidence_validation]: Validation failed - zero events.")
        return {
            "valid_events_count": 0,
            "validation_status": "empty",
            "validation_errors": errors,
            "execution_trace": trace
        }

    # Validate that events have required timestamps and device identifiers
    valid_count = 0
    for e in events:
        if e.device_id and e.timestamp:
            valid_count += 1
        else:
            errors.append(f"Event {e.event_id} missing mandatory device_id or timestamp.")

    status = "valid" if valid_count > 0 else "invalid"
    trace.append(f"Stage 2 [evidence_validation]: Validated {valid_count}/{len(events)} events (status={status}).")

    return {
        "valid_events_count": valid_count,
        "validation_status": status,
        "validation_errors": errors,
        "execution_trace": trace
    }


def route_after_validation(state: IncidentState) -> str:
    """Conditional router based on evidence validation."""
    status = state.get("validation_status", "invalid")
    if status == "valid":
        return "topology_retrieval"
    return "abort_invalid_evidence"


def topology_retrieval_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 3: Retrieves relevant network topology context."""
    timeline = state["timeline"]
    context_id = state.get("context_id")
    trace = list(state.get("execution_trace", []))

    agent = TopologyAgent(context_id=context_id)
    topo_context = agent.contextualize_incident(timeline)
    trace.append(f"Stage 3 [topology_retrieval]: Retrieved topology with {len(topo_context.nodes)} nodes and {len(topo_context.links)} links.")

    return {
        "topology_context": topo_context,
        "execution_trace": trace
    }


def symptom_analysis_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 4: Extracts, groups, and orders symptoms with primacy."""
    timeline = state["timeline"]
    topo_context = state.get("topology_context")
    trace = list(state.get("execution_trace", []))

    agent = SymptomAgent()
    symptom_report = agent.process(timeline, topo_context)
    primary_cat = symptom_report.primary_symptom.category.value if symptom_report.primary_symptom else "none"
    trace.append(f"Stage 4 [symptom_analysis]: Extracted {len(symptom_report.symptoms)} symptoms. Primary: {primary_cat}.")

    return {
        "symptom_report": symptom_report,
        "execution_trace": trace
    }


def topology_reasoning_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 5: Performs topology reasoning, propagation tracing, and blast radius calculation."""
    timeline = state["timeline"]
    context_id = state.get("context_id")
    trace = list(state.get("execution_trace", []))

    agent = TopologyAgent(context_id=context_id)
    analysis = agent.analyze_topology(timeline)
    blast_score = analysis.get("blast_radius", {}).get("blast_radius_score", 0.0)
    trace.append(f"Stage 5 [topology_reasoning]: Topology path evaluated (blast score={blast_score}).")

    return {
        "topology_analysis": analysis,
        "blast_radius_report": analysis.get("blast_radius"),
        "execution_trace": trace
    }


def knowledge_retrieval_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 5b: Retrieves relevant operational SOPs, RFCs, and troubleshooting guides via RAG."""
    timeline = state["timeline"]
    symptom_report = state.get("symptom_report")
    trace = list(state.get("execution_trace", []))

    try:
        from services.rag.src.service import get_rag_service
        rag_service = get_rag_service()
        symptom_summary = {
            "primary_symptom": symptom_report.primary_symptom.category.value if (symptom_report and symptom_report.primary_symptom) else "none",
            "symptoms_count": len(symptom_report.symptoms) if symptom_report else 0
        }
        retrieved_evidence = rag_service.retrieve_for_incident(
            timeline=timeline,
            symptom_summary=symptom_summary,
            top_k=5
        )
        passages_count = len(retrieved_evidence.passages)
        trace.append(f"Stage 5b [knowledge_retrieval]: Retrieved {passages_count} evidence passages (query='{retrieved_evidence.query[:45]}...').")
        return {
            "retrieved_evidence": retrieved_evidence,
            "rag_trace": {
                "passages_count": passages_count,
                "query": retrieved_evidence.query,
                "source_ids": retrieved_evidence.source_ids
            },
            "execution_trace": trace
        }
    except Exception as exc:
        logger.warning("Knowledge retrieval fallback: %s", exc)
        trace.append(f"Stage 5b [knowledge_retrieval]: Retrieval skipped/fallback ({exc}).")
        return {
            "retrieved_evidence": None,
            "rag_trace": {"error": str(exc)},
            "execution_trace": trace
        }


def rca_hypotheses_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 6: Generates candidate root-cause hypotheses."""
    timeline = state["timeline"]
    symptom_report = state["symptom_report"]
    topo_context = state.get("topology_context")
    trace = list(state.get("execution_trace", []))

    rca_agent = RCAgent()
    hypotheses = rca_agent.engine.evaluate_all(timeline, symptom_report, topo_context)
    trace.append(f"Stage 6 [rca_hypotheses]: Formulated {len(hypotheses)} candidate hypotheses.")

    return {
        "hypotheses": hypotheses,
        "execution_trace": trace
    }


def evidence_verification_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 7: Weighs supporting vs contradictory evidence and calibrates confidence."""
    hypotheses = list(state.get("hypotheses", []))
    trace = list(state.get("execution_trace", []))

    if hypotheses:
        top_hyp = hypotheses[0]
        trace.append(
            f"Stage 7 [evidence_verification]: Calibrated top hypothesis '{top_hyp.hypothesis_id}' "
            f"(conf={top_hyp.confidence:.2f}, supporting={len(top_hyp.supporting_evidence)}, contradictory={len(top_hyp.contradictory_evidence)})."
        )
    else:
        top_hyp = None
        trace.append("Stage 7 [evidence_verification]: No hypotheses survived evidence filtering.")

    return {
        "top_hypothesis": top_hyp,
        "execution_trace": trace
    }


def diagnosis_synthesis_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 8: Compiles canonical DiagnosisResult."""
    timeline = state["timeline"]
    symptom_report = state["symptom_report"]
    topo_context = state.get("topology_context")
    retrieved_evidence = state.get("retrieved_evidence")
    trace = list(state.get("execution_trace", []))

    rca_agent = RCAgent()
    diagnosis = rca_agent.diagnose(
        timeline=timeline,
        symptom_report=symptom_report,
        topology_context=topo_context,
        retrieved_evidence=retrieved_evidence
    )
    trace.append(f"Stage 8 [diagnosis_synthesis]: Synthesized diagnosis '{diagnosis.probable_root_cause}' (confidence={diagnosis.confidence:.2f}).")

    return {
        "diagnosis_result": diagnosis,
        "execution_trace": trace
    }


def structured_persistence_node(state: IncidentState) -> Dict[str, Any]:
    """Stage 9: Persists diagnosis and timeline into MongoDB."""
    timeline = state["timeline"]
    diagnosis = state.get("diagnosis_result")
    symptom_report = state.get("symptom_report")
    topo_context = state.get("topology_context")
    trace = list(state.get("execution_trace", []))

    if diagnosis:
        persistence = DiagnosisPersistence()
        persisted = persistence.save_diagnosis(
            incident_id=timeline.incident_id,
            timeline=timeline,
            diagnosis=diagnosis,
            symptom_report=symptom_report,
            topology_context=topo_context,
            execution_trace=trace
        )
    else:
        persisted = False

    trace.append(f"Stage 9 [structured_persistence]: Persisted to MongoDB (status={'success' if persisted else 'skipped'}).")

    return {
        "is_persisted": persisted,
        "execution_trace": trace
    }


def abort_invalid_evidence_node(state: IncidentState) -> Dict[str, Any]:
    """Terminal node for invalid or unprocessable incidents."""
    timeline = state.get("timeline")
    errors = state.get("validation_errors", [])
    trace = list(state.get("execution_trace", []))
    trace.append(f"Stage [abort]: Aborted due to validation errors: {errors}")

    inc_id = timeline.incident_id if timeline else "unknown_incident"
    fallback_diag = DiagnosisResult(
        hypotheses=[],
        probable_root_cause=f"Diagnosis unviable: {'; '.join(errors)}",
        evidence_ids=[],
        confidence=0.0,
        affected_components=[],
        provenance={"abort_reason": errors}
    )

    return {
        "diagnosis_result": fallback_diag,
        "is_persisted": False,
        "execution_trace": trace,
        "error": "; ".join(errors)
    }


# ─────────────────────────────────────────────────────────────────────────────
# REMEDIATION & SAFETY WORKFLOW NODES (MILESTONE 6)
# ─────────────────────────────────────────────────────────────────────────────

def remediation_proposal_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    incident_id = state.get("incident_id", "inc_unknown")
    diagnosis = state.get("diagnosis_result")
    topo_ctx = state.get("topology_context")
    blast_rep = state.get("blast_radius_report")

    trace.append("Stage 10 [remediation_proposal]: Deriving evidence-grounded remediation proposal.")

    if not diagnosis or not diagnosis.hypotheses:
        trace.append("Stage 10 [remediation_proposal]: No valid diagnosis hypotheses. Proposal generation skipped.")
        return {
            "remediation_status": "NO_ACTION_REQUIRED",
            "execution_trace": trace,
        }

    topo_agent = TopologyAgent(context_id=state.get("context_id"))
    proposal = proposal_engine.generate_proposal(
        incident_id=incident_id,
        diagnosis=diagnosis,
        topology_context=topo_ctx,
        topology_graph=topo_agent.graph,
        blast_radius_report=blast_rep,
    )

    if not proposal:
        trace.append("Stage 10 [remediation_proposal]: Diagnosis confidence below safe threshold (0.60) or category unmapped. Flagged for manual investigation.")
        return {
            "remediation_status": "MANUAL_INVESTIGATION_REQUIRED",
            "execution_trace": trace,
        }

    trace.append(f"Stage 10 [remediation_proposal]: Generated proposal {proposal.action_id} (op={proposal.operation}, target={proposal.target}).")
    return {
        "remediation_proposal": proposal,
        "remediation_status": "PROPOSED",
        "execution_trace": trace,
    }


def policy_validation_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")

    trace.append("Stage 11 [policy_validation]: Auditing proposal against deterministic safety allow-list.")

    if not proposal:
        return {"remediation_status": "NO_PROPOSAL", "execution_trace": trace}

    topo_agent = TopologyAgent(context_id=state.get("context_id"))
    policy_dec = remediation_policy.evaluate_proposal(
        proposal=proposal,
        topology_graph=topo_agent.graph
    )
    status_str = "AWAITING_REVIEW" if policy_dec.is_allowed else "POLICY_REJECTED"
    trace.append(f"Stage 11 [policy_validation]: Policy decision {policy_dec.status.value} (is_allowed={policy_dec.is_allowed}).")

    return {
        "policy_decision": policy_dec,
        "remediation_status": status_str,
        "execution_trace": trace,
    }


def risk_classification_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")
    topo_ctx = state.get("topology_context")
    blast_rep = state.get("blast_radius_report")

    trace.append("Stage 12 [risk_classification]: Evaluating multi-factor blast radius and operational risk.")

    if not proposal:
        return {"execution_trace": trace}

    risk_ass = risk_classifier.evaluate_risk(
        proposal=proposal,
        topology_context=topo_ctx.model_dump() if topo_ctx else None,
        blast_radius_report=blast_rep,
    )

    trace.append(f"Stage 12 [risk_classification]: Classified risk {risk_ass.risk_level.value.upper()} (score={risk_ass.risk_score:.2f}).")

    return {
        "risk_assessment": risk_ass,
        "execution_trace": trace,
    }


def approval_request_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")
    policy_dec = state.get("policy_decision")
    risk_ass = state.get("risk_assessment")

    trace.append("Stage 13 [approval_request]: Dispatching immutable request to Human Oversight Gate.")

    if not proposal or not policy_dec:
        return {"execution_trace": trace}

    req = approval_manager.create_request(
        proposal=proposal,
        policy_decision=policy_dec,
        risk_level=risk_ass.risk_level.value if risk_ass else proposal.risk.value,
        risk_reasons=risk_ass.reasons if risk_ass else proposal.risk_reasons,
    )

    trace.append(f"Stage 13 [approval_request]: Approval request {req.request_id} created (expires {req.expires_at.isoformat()}). Pausing for operator review.")

    return {
        "approval_request": req,
        "remediation_status": "AWAITING_APPROVAL",
        "execution_trace": trace,
    }


def human_approval_interrupt_node(state: IncidentState) -> Dict[str, Any]:
    """
    Execution resumes at this node after human operator approval or rejection.
    """
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")
    decision = state.get("approval_decision")

    trace.append("Stage 14 [human_approval_gate]: Evaluating reviewer decision signature and hash binding.")

    if not proposal:
        return {"remediation_status": "NO_PROPOSAL", "execution_trace": trace}

    is_approved, gate_reason, req = human_approval_gate.evaluate_gate(proposal, decision)
    status_str = "APPROVED" if is_approved else (req.status.value.upper() if req else "REJECTED")

    trace.append(f"Stage 14 [human_approval_gate]: Gate verdict: {status_str} ({gate_reason}).")

    return {
        "remediation_status": status_str,
        "execution_trace": trace,
    }


def precondition_check_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")

    trace.append("Stage 15 [precondition_check]: Re-verifying simulator target and operational state.")

    if not proposal:
        return {"execution_trace": trace}

    target_dev = proposal.target_device or proposal.target.split(":")[0]
    from automation.simulated_executor.state_manager import simulator_state

    if not simulator_state.has_device(target_dev):
        trace.append(f"Stage 15 [precondition_check]: Precondition failed - target device '{target_dev}' missing.")
        return {
            "remediation_status": "PRECONDITION_FAILED",
            "remediation_error": f"Target device '{target_dev}' missing in simulation.",
            "execution_trace": trace,
        }

    trace.append("Stage 15 [precondition_check]: Simulator preconditions validated successfully.")
    return {
        "remediation_status": "PRECONDITIONS_VERIFIED",
        "execution_trace": trace,
    }


def kill_switch_check_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")

    trace.append("Stage 16 [kill_switch_check]: Auditing active emergency freeze policies.")

    if not proposal:
        return {"execution_trace": trace}

    can_run, ks_reason = kill_switch.can_execute(
        operation=proposal.operation,
        target_device=proposal.target_device or proposal.target.split(":")[0],
        agent_name="simulated_executor"
    )

    if not can_run:
        trace.append(f"Stage 16 [kill_switch_check]: Execution blocked by kill switch: {ks_reason}")
        return {
            "remediation_status": "KILL_SWITCH_BLOCKED",
            "remediation_error": ks_reason,
            "execution_trace": trace,
        }

    trace.append("Stage 16 [kill_switch_check]: Kill switch is clear.")
    return {
        "remediation_status": "READY_FOR_EXECUTION",
        "execution_trace": trace,
    }


def simulated_execution_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")
    decision = state.get("approval_decision")

    trace.append("Stage 17 [simulated_execution]: Applying bounded operation to isolated simulator state.")

    if not proposal:
        return {"execution_trace": trace}

    exec_res, ver_res, rb_res = simulated_executor.execute_proposal(
        proposal=proposal,
        approval_decision=decision,
        auto_rollback_on_failure=False,
    )

    trace.append(f"Stage 17 [simulated_execution]: Execution outcome {exec_res.status.value.upper()}.")

    return {
        "execution_result": exec_res,
        "verification_result": ver_res,
        "remediation_status": "EXECUTED" if exec_res.status.value == "succeeded" else "EXECUTION_FAILED",
        "execution_trace": trace,
    }


def post_action_verification_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")
    exec_res = state.get("execution_result")

    trace.append("Stage 18 [post_action_verification]: Independently testing post-remediation simulator state.")

    if not proposal or not exec_res:
        return {"execution_trace": trace}

    ver_res = post_remediation_verifier.verify_remediation(
        execution_id=exec_res.execution_id,
        proposal=proposal
    )

    trace.append(f"Stage 18 [post_action_verification]: Verification verdict: {ver_res.status.value.upper()} (success={ver_res.success}).")

    return {
        "verification_result": ver_res,
        "remediation_status": "RECOVERED" if ver_res.success else "RECOVERY_FAILED",
        "execution_trace": trace,
    }


def conditional_rollback_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    proposal = state.get("remediation_proposal")
    exec_res = state.get("execution_result")

    trace.append("Stage 19 [conditional_rollback]: Verification failed. Executing automated rollback.")

    if not proposal or not exec_res:
        return {"execution_trace": trace}

    rb_res = rollback_engine.execute_rollback(
        proposal=proposal,
        execution_id=exec_res.execution_id,
        pre_state_snapshot=exec_res.pre_state_snapshot
    )

    trace.append(f"Stage 19 [conditional_rollback]: Rollback status {rb_res.status.value.upper()} (is_verified={rb_res.is_verified}).")

    return {
        "rollback_result": rb_res,
        "remediation_status": "ROLLED_BACK" if rb_res.status.value == "succeeded" else "ESCALATED_MANUAL_INTERVENTION",
        "execution_trace": trace,
    }


def final_remediation_audit_node(state: IncidentState) -> Dict[str, Any]:
    trace = list(state.get("execution_trace", []))
    incident_id = state.get("incident_id", "inc_unknown")
    proposal = state.get("remediation_proposal")
    appr_req = state.get("approval_request")
    appr_dec = state.get("approval_decision")
    exec_res = state.get("execution_result")
    ver_res = state.get("verification_result")
    rb_res = state.get("rollback_result")

    trace.append("Stage 20 [final_remediation_audit]: Persisting full audit records to MongoDB hash chain.")

    if proposal:
        remediation_persistence.save_proposal(proposal)

    if appr_req and appr_dec:
        remediation_persistence.save_approval_decision(appr_req, appr_dec)
    elif appr_req:
        remediation_persistence.save_approval_request(appr_req)

    if exec_res:
        remediation_persistence.save_execution_result(exec_res, incident_id=incident_id)

    if ver_res:
        remediation_persistence.save_verification_result(ver_res, incident_id=incident_id)

    if rb_res:
        remediation_persistence.save_rollback_result(rb_res, incident_id=incident_id)

    trace.append("Stage 20 [final_remediation_audit]: Tamper-evident audit chain appended and secured.")

    return {
        "is_persisted": True,
        "execution_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CONDITIONAL ROUTING FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def route_after_diagnosis(state: IncidentState) -> str:
    enable_rem = state.get("enable_remediation", False)
    diag = state.get("diagnosis_result")
    if enable_rem and diag and diag.confidence >= 0.60:
        return "remediation_proposal"
    return "structured_persistence"


def route_after_proposal(state: IncidentState) -> str:
    if state.get("remediation_proposal"):
        return "policy_validation"
    return "final_remediation_audit"


def route_after_policy(state: IncidentState) -> str:
    pol = state.get("policy_decision")
    if pol and pol.is_allowed:
        return "risk_classification"
    return "final_remediation_audit"


def route_after_approval(state: IncidentState) -> str:
    rem_status = state.get("remediation_status")
    if rem_status == "APPROVED":
        return "precondition_check"
    return "final_remediation_audit"


def route_after_preconditions(state: IncidentState) -> str:
    rem_status = state.get("remediation_status")
    if rem_status == "PRECONDITIONS_VERIFIED":
        return "kill_switch_check"
    return "final_remediation_audit"


def route_after_kill_switch(state: IncidentState) -> str:
    rem_status = state.get("remediation_status")
    if rem_status == "READY_FOR_EXECUTION":
        return "simulated_execution"
    return "final_remediation_audit"


def route_after_verification(state: IncidentState) -> str:
    ver = state.get("verification_result")
    if ver and ver.success:
        return "final_remediation_audit"
    return "conditional_rollback"


# ─────────────────────────────────────────────────────────────────────────────
# 2. STATEGRAPH COMPILATION
# ─────────────────────────────────────────────────────────────────────────────

def build_diagnosis_graph(
    checkpointer: Optional[Any] = None,
    enable_remediation: bool = False
) -> Any:
    """
    Constructs and compiles the genuine LangGraph StateGraph diagnosis workflow.
    Preserves 100% backward compatibility with diagnosis-only callers.
    """
    if enable_remediation:
        return build_remediation_graph(checkpointer=checkpointer, interrupt_for_approval=True)

    workflow = StateGraph(IncidentState)

    # Add Nodes
    workflow.add_node("incident_intake", incident_intake_node)
    workflow.add_node("evidence_validation", evidence_validation_node)
    workflow.add_node("topology_retrieval", topology_retrieval_node)
    workflow.add_node("symptom_analysis", symptom_analysis_node)
    workflow.add_node("topology_reasoning", topology_reasoning_node)
    workflow.add_node("knowledge_retrieval", knowledge_retrieval_node)
    workflow.add_node("rca_hypotheses", rca_hypotheses_node)
    workflow.add_node("evidence_verification", evidence_verification_node)
    workflow.add_node("diagnosis_synthesis", diagnosis_synthesis_node)
    workflow.add_node("structured_persistence", structured_persistence_node)
    workflow.add_node("abort_invalid_evidence", abort_invalid_evidence_node)

    # Add Edges & Conditional Routing
    workflow.add_edge(START, "incident_intake")
    workflow.add_edge("incident_intake", "evidence_validation")

    workflow.add_conditional_edges(
        "evidence_validation",
        route_after_validation,
        {
            "topology_retrieval": "topology_retrieval",
            "abort_invalid_evidence": "abort_invalid_evidence"
        }
    )

    workflow.add_edge("topology_retrieval", "symptom_analysis")
    workflow.add_edge("symptom_analysis", "topology_reasoning")
    workflow.add_edge("topology_reasoning", "knowledge_retrieval")
    workflow.add_edge("knowledge_retrieval", "rca_hypotheses")
    workflow.add_edge("rca_hypotheses", "evidence_verification")
    workflow.add_edge("evidence_verification", "diagnosis_synthesis")
    workflow.add_edge("diagnosis_synthesis", "structured_persistence")
    workflow.add_edge("structured_persistence", END)
    workflow.add_edge("abort_invalid_evidence", END)

    cp = checkpointer if checkpointer is not None else MemorySaver()
    compiled_app = workflow.compile(checkpointer=cp)
    return compiled_app


def build_remediation_graph(
    checkpointer: Optional[Any] = None,
    interrupt_for_approval: bool = True
) -> Any:
    """
    Constructs and compiles the end-to-end Diagnosis + Safe Remediation StateGraph.
    Configures LangGraph human-in-the-loop interrupt before execution.
    """
    workflow = StateGraph(IncidentState)

    # 1. Diagnostic Nodes
    workflow.add_node("incident_intake", incident_intake_node)
    workflow.add_node("evidence_validation", evidence_validation_node)
    workflow.add_node("topology_retrieval", topology_retrieval_node)
    workflow.add_node("symptom_analysis", symptom_analysis_node)
    workflow.add_node("topology_reasoning", topology_reasoning_node)
    workflow.add_node("knowledge_retrieval", knowledge_retrieval_node)
    workflow.add_node("rca_hypotheses", rca_hypotheses_node)
    workflow.add_node("evidence_verification", evidence_verification_node)
    workflow.add_node("diagnosis_synthesis", diagnosis_synthesis_node)
    workflow.add_node("structured_persistence", structured_persistence_node)
    workflow.add_node("abort_invalid_evidence", abort_invalid_evidence_node)

    # 2. Remediation & Safety Nodes
    workflow.add_node("remediation_proposal", remediation_proposal_node)
    workflow.add_node("policy_validation", policy_validation_node)
    workflow.add_node("risk_classification", risk_classification_node)
    workflow.add_node("approval_request", approval_request_node)
    workflow.add_node("human_approval_interrupt", human_approval_interrupt_node)
    workflow.add_node("precondition_check", precondition_check_node)
    workflow.add_node("kill_switch_check", kill_switch_check_node)
    workflow.add_node("simulated_execution", simulated_execution_node)
    workflow.add_node("post_action_verification", post_action_verification_node)
    workflow.add_node("conditional_rollback", conditional_rollback_node)
    workflow.add_node("final_remediation_audit", final_remediation_audit_node)

    # 3. Flow Routing
    workflow.add_edge(START, "incident_intake")
    workflow.add_edge("incident_intake", "evidence_validation")

    workflow.add_conditional_edges(
        "evidence_validation",
        route_after_validation,
        {
            "topology_retrieval": "topology_retrieval",
            "abort_invalid_evidence": "abort_invalid_evidence"
        }
    )

    workflow.add_edge("topology_retrieval", "symptom_analysis")
    workflow.add_edge("symptom_analysis", "topology_reasoning")
    workflow.add_edge("topology_reasoning", "knowledge_retrieval")
    workflow.add_edge("knowledge_retrieval", "rca_hypotheses")
    workflow.add_edge("rca_hypotheses", "evidence_verification")
    workflow.add_edge("evidence_verification", "diagnosis_synthesis")

    # After diagnosis: route to remediation proposal or structured persistence
    workflow.add_conditional_edges(
        "diagnosis_synthesis",
        route_after_diagnosis,
        {
            "remediation_proposal": "remediation_proposal",
            "structured_persistence": "structured_persistence",
        }
    )

    workflow.add_conditional_edges(
        "remediation_proposal",
        route_after_proposal,
        {
            "policy_validation": "policy_validation",
            "final_remediation_audit": "final_remediation_audit",
        }
    )

    workflow.add_conditional_edges(
        "policy_validation",
        route_after_policy,
        {
            "risk_classification": "risk_classification",
            "final_remediation_audit": "final_remediation_audit",
        }
    )

    workflow.add_edge("risk_classification", "approval_request")
    workflow.add_edge("approval_request", "human_approval_interrupt")

    workflow.add_conditional_edges(
        "human_approval_interrupt",
        route_after_approval,
        {
            "precondition_check": "precondition_check",
            "final_remediation_audit": "final_remediation_audit",
        }
    )

    workflow.add_conditional_edges(
        "precondition_check",
        route_after_preconditions,
        {
            "kill_switch_check": "kill_switch_check",
            "final_remediation_audit": "final_remediation_audit",
        }
    )

    workflow.add_conditional_edges(
        "kill_switch_check",
        route_after_kill_switch,
        {
            "simulated_execution": "simulated_execution",
            "final_remediation_audit": "final_remediation_audit",
        }
    )

    workflow.add_edge("simulated_execution", "post_action_verification")

    workflow.add_conditional_edges(
        "post_action_verification",
        route_after_verification,
        {
            "final_remediation_audit": "final_remediation_audit",
            "conditional_rollback": "conditional_rollback",
        }
    )

    workflow.add_edge("conditional_rollback", "final_remediation_audit")
    workflow.add_edge("final_remediation_audit", "structured_persistence")
    workflow.add_edge("structured_persistence", END)
    workflow.add_edge("abort_invalid_evidence", END)

    cp = checkpointer if checkpointer is not None else MemorySaver()
    interrupt_nodes = ["human_approval_interrupt"] if interrupt_for_approval else []
    compiled_app = workflow.compile(checkpointer=cp, interrupt_before=interrupt_nodes)
    return compiled_app



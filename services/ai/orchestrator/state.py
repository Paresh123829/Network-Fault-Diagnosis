"""
state.py — Typed Shared State for LangGraph Multi-Agent Orchestration.

Maintains the state across all stages of the diagnostic StateGraph.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from services.ai.schemas.contracts import (
    IncidentTimeline,
    TopologyContext,
    DiagnosisResult,
    Hypothesis,
    RetrievedEvidence,
    RemediationProposal,
    PolicyDecision,
    ApprovalDecision,
    ExecutionResult,
    VerificationResult,
    RollbackResult,
)
from services.ai.agents.symptom.models import SymptomAnalysisReport
from services.ai.agents.remediation.models import RemediationRiskAssessment
from services.ai.agents.oversight.models import ApprovalRequest


class IncidentState(TypedDict, total=False):
    """
    Typed shared state passing through LangGraph nodes.
    """
    # 1. Intake
    incident_id: str
    timeline: IncidentTimeline
    context_id: Optional[str]

    # 2. Evidence Validation
    valid_events_count: int
    validation_status: str  # "valid", "empty", "invalid"
    validation_errors: List[str]

    # 3. Topology Retrieval & Reasoning
    topology_context: Optional[TopologyContext]
    topology_analysis: Optional[Dict[str, Any]]
    blast_radius_report: Optional[Dict[str, Any]]
    is_cross_device: bool

    # 4. Symptom Analysis
    symptom_report: Optional[SymptomAnalysisReport]

    # 5. Knowledge Retrieval (RAG)
    retrieved_evidence: Optional[RetrievedEvidence]
    rag_trace: Optional[Dict[str, Any]]

    # 6. RCA Hypotheses & Evidence Verification
    hypotheses: List[Hypothesis]
    top_hypothesis: Optional[Hypothesis]

    # 7. Diagnosis Synthesis & Persistence
    diagnosis_result: Optional[DiagnosisResult]
    is_persisted: bool

    # 8. Remediation & Safety Pipeline
    enable_remediation: bool
    remediation_proposal: Optional[RemediationProposal]
    policy_decision: Optional[PolicyDecision]
    risk_assessment: Optional[RemediationRiskAssessment]
    approval_request: Optional[ApprovalRequest]
    approval_decision: Optional[ApprovalDecision]
    execution_result: Optional[ExecutionResult]
    verification_result: Optional[VerificationResult]
    rollback_result: Optional[RollbackResult]
    remediation_status: Optional[str]
    remediation_error: Optional[str]

    # Execution Trace & Diagnostics
    execution_trace: List[str]
    error: Optional[str]


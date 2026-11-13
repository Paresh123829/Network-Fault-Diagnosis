"""
agent.py — Remediation Agent Interface.

Coordinates remediation proposal synthesis, deterministic safety policy checking,
and risk classification.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from services.ai.schemas.contracts import (
    DiagnosisResult,
    PolicyDecision,
    PolicyStatus,
    RemediationProposal,
    TopologyContext,
)
from services.ai.agents.topology.graph import TopologyGraph
from .proposal_engine import RemediationProposalEngine, proposal_engine
from .policy import RemediationPolicyEngine, remediation_policy
from .risk import RemediationRiskClassifier, risk_classifier
from .models import RemediationRiskAssessment

logger = logging.getLogger(__name__)


class RemediationAgent:
    """
    Intelligent Remediation Agent that synthesizes bounded, explainable corrective proposals.
    All outputs strictly adhere to the allow-list and fail-closed safety policies.
    """

    def __init__(
        self,
        engine: Optional[RemediationProposalEngine] = None,
        policy_engine: Optional[RemediationPolicyEngine] = None,
        risk_engine: Optional[RemediationRiskClassifier] = None,
    ) -> None:
        self.proposal_engine = engine or proposal_engine
        self.policy_engine = policy_engine or remediation_policy
        self.risk_classifier = risk_engine or risk_classifier

    def propose_remediation(
        self,
        incident_id: str,
        diagnosis: DiagnosisResult,
        topology_context: Optional[TopologyContext] = None,
        topology_graph: Optional[TopologyGraph] = None,
        blast_radius_report: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[RemediationProposal], Optional[PolicyDecision], Optional[RemediationRiskAssessment]]:
        """
        Synthesizes a remediation proposal, verifies it against deterministic policies,
        and computes operational risk.
        Returns: (proposal, policy_decision, risk_assessment)
        """
        proposal = self.proposal_engine.generate_proposal(
            incident_id=incident_id,
            diagnosis=diagnosis,
            topology_context=topology_context,
            topology_graph=topology_graph,
            blast_radius_report=blast_radius_report,
        )

        if not proposal:
            return None, None, None

        # Evaluate safety policy
        policy_decision = self.policy_engine.evaluate_proposal(
            proposal=proposal,
            topology_graph=topology_graph
        )

        # Evaluate risk
        risk_assessment = self.risk_classifier.evaluate_risk(
            proposal=proposal,
            topology_context=topology_context.model_dump() if topology_context else None,
            blast_radius_report=blast_radius_report
        )

        return proposal, policy_decision, risk_assessment


# Global singleton instance
remediation_agent = RemediationAgent()


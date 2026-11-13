"""
risk.py — Deterministic Risk Assessment Engine for Network Remediation Operations.

Calculates explainable risk scores and maps them into RiskLevel (LOW, MEDIUM, HIGH, CRITICAL).
Evaluates blast radius exposure, unreachability, alternate path redundancy, protocol tier, and reversibility.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from services.ai.schemas.contracts import RiskLevel, RemediationProposal
from .models import RemediationRiskAssessment
from .action_registry import action_registry


class RemediationRiskClassifier:
    """
    Evaluates multi-factor operational risk for a proposed remediation action.
    """

    def __init__(self) -> None:
        pass

    def evaluate_risk(
        self,
        proposal: RemediationProposal,
        topology_context: Optional[Dict[str, Any]] = None,
        blast_radius_report: Optional[Dict[str, Any]] = None,
    ) -> RemediationRiskAssessment:
        """
        Calculates deterministic risk classification and provides granular justifications.
        """
        reasons: List[str] = []
        action_def = action_registry.get(proposal.operation)
        base_risk = action_def.base_risk if action_def else RiskLevel.HIGH

        # Baseline score from action definition
        base_score_map = {
            RiskLevel.LOW: 0.20,
            RiskLevel.MEDIUM: 0.50,
            RiskLevel.HIGH: 0.75,
            RiskLevel.CRITICAL: 0.95,
        }
        score = base_score_map.get(base_risk, 0.50)
        reasons.append(f"Baseline operational risk for '{proposal.operation}' is {base_risk.value.upper()}.")

        # 1. Topology & Blast-Radius Factors
        ier = 0.0
        nur = 0.0
        affected_devices_count = 1
        has_alternates = True

        if blast_radius_report:
            target_dev = proposal.target_device or proposal.target.split(":")[0]
            dev_report = blast_radius_report.get(f"device_{target_dev}") or blast_radius_report.get(target_dev, {})
            ier = dev_report.get("impact_exposure_ratio", 0.0)
            nur = dev_report.get("network_unreachability_ratio", 0.0)
            affected_devices_count = dev_report.get("blast_radius_device_count", 1)
            lost_paths = dev_report.get("lost_paths_count", 0)
            surviving_paths = dev_report.get("surviving_alternate_paths_count", 0)

            if surviving_paths == 0 and lost_paths > 0:
                has_alternates = False
                score += 0.25
                reasons.append("Zero surviving alternate paths available: remediation risks complete traffic disruption.")
            elif surviving_paths > 0:
                score -= 0.10
                reasons.append(f"Fabric retains {surviving_paths} alternate paths, mitigating operational risk.")

            if nur > 0.10:
                score += 0.30
                reasons.append(f"High network unreachability ratio ({nur:.2f}) observed in baseline topology.")
            elif ier > 0.50:
                score += 0.15
                reasons.append(f"Broad impact exposure ratio ({ier:.2f}) across adjacent fabric.")

        # 2. Protocol Criticality
        op = proposal.operation.lower()
        if "bgp" in op:
            protocol_tier = "HIGH"
            score += 0.10
            reasons.append("BGP routing protocol modification affects core inter-pod or external routing.")
        elif "ospf" in op:
            protocol_tier = "MEDIUM"
            score += 0.05
            reasons.append("OSPF interior routing modification affects area adjacencies.")
        elif "vlan" in op or "bfd" in op:
            protocol_tier = "LOW"
            reasons.append("VLAN/BFD configuration is localized to access or link monitoring.")
        else:
            protocol_tier = "MEDIUM"

        # 3. Reversibility / Rollback
        is_rev = bool(action_def and action_def.is_reversible and proposal.rollback_plan)
        if not is_rev:
            score += 0.20
            reasons.append("Operation lacks an automated rollback plan, increasing risk.")
        else:
            score -= 0.05
            reasons.append("Verified automated rollback plan is attached.")

        # Normalize score between 0.05 and 1.0
        score = max(0.05, min(1.0, score))

        # Categorize into final RiskLevel
        if score >= 0.85:
            final_level = RiskLevel.CRITICAL
        elif score >= 0.65:
            final_level = RiskLevel.HIGH
        elif score >= 0.35:
            final_level = RiskLevel.MEDIUM
        else:
            final_level = RiskLevel.LOW

        return RemediationRiskAssessment(
            proposal_id=proposal.action_id,
            risk_level=final_level,
            risk_score=round(score, 3),
            reasons=reasons,
            affected_devices_count=affected_devices_count,
            blast_radius_ier=round(ier, 3),
            blast_radius_nur=round(nur, 3),
            has_alternate_paths=has_alternates,
            is_reversible=is_rev,
            protocol_criticality=protocol_tier,
        )


# Global singleton instance
risk_classifier = RemediationRiskClassifier()


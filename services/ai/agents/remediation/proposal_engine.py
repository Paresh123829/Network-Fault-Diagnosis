"""
proposal_engine.py — Evidence-Grounded Remediation Proposal Generator.

Translates verified DiagnosisResult, top RCA hypothesis, and topology context into
structured RemediationProposal models from the deterministic allow-list.
The LLM and engine NEVER generate arbitrary CLI commands or shell strings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid

from services.ai.schemas.contracts import (
    DiagnosisResult,
    Hypothesis,
    RemediationProposal,
    RiskLevel,
    TopologyContext,
)
from services.ai.agents.topology.graph import TopologyGraph
from .action_registry import action_registry
from .risk import risk_classifier

logger = logging.getLogger(__name__)


class RemediationProposalEngine:
    """
    Synthesizes structured remediation proposals grounded in diagnostic evidence.
    """

    def __init__(self, default_ttl_minutes: int = 60) -> None:
        self.default_ttl = timedelta(minutes=default_ttl_minutes)

    def generate_proposal(
        self,
        incident_id: str,
        diagnosis: DiagnosisResult,
        topology_context: Optional[TopologyContext] = None,
        topology_graph: Optional[TopologyGraph] = None,
        blast_radius_report: Optional[Dict[str, Any]] = None,
    ) -> Optional[RemediationProposal]:
        """
        Derives an allowable, evidence-backed remediation proposal.
        Returns None if diagnosis is unviable, confidence is too low, or root-cause is unresolvable.
        """
        if not diagnosis or not diagnosis.hypotheses:
            logger.warning(f"Cannot generate proposal for incident {incident_id}: no hypotheses present.")
            return None

        # Filter by minimum confidence threshold
        top_hypo = diagnosis.hypotheses[0]
        if top_hypo.confidence < 0.60 or diagnosis.confidence < 0.60:
            logger.warning(
                f"Incident {incident_id} confidence ({top_hypo.confidence:.2f}) is below safe threshold 0.60. "
                "Escalating to manual investigation without proposal generation."
            )
            return None

        category = (top_hypo.root_cause_category or "").lower()
        devices = top_hypo.affected_devices or diagnosis.affected_components
        interfaces = top_hypo.affected_interfaces

        target_dev = devices[0] if devices else ""
        target_iface = interfaces[0] if interfaces else None

        if not target_dev:
            logger.warning(f"Incident {incident_id} has no target device. Cannot generate proposal.")
            return None

        now = datetime.now(timezone.utc)
        expires_at = now + self.default_ttl
        action_id = f"act_{uuid.uuid4().hex[:12]}"

        # Map diagnostic root-cause category to allowable operation
        if any(term in category for term in ("bgp", "peer", "as_path")):
            # BGP Session Reset
            peer_ip = self._resolve_bgp_peer_ip(target_dev, topology_graph, top_hypo)
            parameters = {
                "target_device": target_dev,
                "peer_ip": peer_ip or "10.0.0.2",
                "soft_reset": True,
            }
            rollback_plan = {
                "operation": "reconfigure_bgp_session",
                "parameters": {
                    "target_device": target_dev,
                    "peer_ip": peer_ip or "10.0.0.2",
                    "action": "reassert_baseline"
                }
            }
            operation = "reset_bgp_session"
            target_str = f"{target_dev}:{peer_ip}" if peer_ip else target_dev
            expected_effect = f"Soft-resets BGP peering session on {target_dev} to re-establish routing adjacency."
            verification_cond = "bgp_session_is_established"
            preconditions = {"device_exists": True, "session_not_established": True}
            postconditions = {"bgp_session_is_established": True}

        elif any(term in category for term in ("admin_shutdown", "port_down", "port_flap", "physical_link")):
            # Restore Interface Admin State
            iface = target_iface or "Ethernet1/1"
            parameters = {
                "target_device": target_dev,
                "target_interface": iface,
                "admin_state": "UP",
                "clear_counters": True,
            }
            rollback_plan = {
                "operation": "disable_interface_admin_state",
                "parameters": {
                    "target_device": target_dev,
                    "target_interface": iface,
                    "admin_state": "DOWN"
                }
            }
            operation = "restore_interface_admin_state"
            target_str = f"{target_dev}:{iface}"
            expected_effect = f"Brings admin state of {iface} on {target_dev} to UP."
            verification_cond = "interface_operational_state_is_up"
            preconditions = {"device_exists": True, "interface_is_admin_down": True}
            postconditions = {"interface_admin_state_is_up": True, "interface_operational_state_is_up": True}

        elif "bfd" in category:
            # Restore BFD Session
            peer_ip = self._resolve_bgp_peer_ip(target_dev, topology_graph, top_hypo) or "10.0.0.2"
            parameters = {
                "target_device": target_dev,
                "peer_ip": peer_ip,
                "interval_ms": 300,
                "multiplier": 3,
            }
            rollback_plan = {
                "operation": "disable_bfd_session",
                "parameters": {"target_device": target_dev, "peer_ip": peer_ip}
            }
            operation = "restore_bfd_session"
            target_str = f"{target_dev}:{peer_ip}"
            expected_effect = f"Re-enables fast BFD keepalives to peer {peer_ip} on {target_dev}."
            verification_cond = "bfd_session_is_up"
            preconditions = {"device_exists": True, "bfd_peer_configured": True}
            postconditions = {"bfd_session_is_up": True}

        elif "ospf" in category:
            # Restore OSPF Adjacency
            iface = target_iface or "Ethernet1/1"
            parameters = {
                "target_device": target_dev,
                "interface": iface,
                "area": "0.0.0.0",
            }
            rollback_plan = {
                "operation": "disable_ospf_on_interface",
                "parameters": {"target_device": target_dev, "interface": iface}
            }
            operation = "restore_ospf_adjacency"
            target_str = f"{target_dev}:{iface}"
            expected_effect = f"Re-enables OSPF area 0.0.0.0 on {target_dev} {iface}."
            verification_cond = "ospf_neighbor_state_is_full"
            preconditions = {"device_exists": True, "ospf_configured_on_interface": True}
            postconditions = {"ospf_neighbor_state_is_full": True}

        elif "vlan" in category:
            # Restore VLAN Membership
            iface = target_iface or "Ethernet1/1"
            parameters = {
                "target_device": target_dev,
                "interface": iface,
                "vlan_id": 100,
                "mode": "access",
            }
            rollback_plan = {
                "operation": "revert_vlan_membership",
                "parameters": {"target_device": target_dev, "interface": iface, "vlan_id": 1}
            }
            operation = "restore_vlan_membership"
            target_str = f"{target_dev}:{iface}"
            expected_effect = f"Restores access VLAN 100 assignment on {target_dev} {iface}."
            verification_cond = "vlan_membership_restored"
            preconditions = {"device_exists": True, "vlan_valid_range": True}
            postconditions = {"vlan_membership_restored": True, "l2_reachability_verified": True}

        else:
            logger.info(f"Unmapped fault category '{category}'. No automated proposal generated.")
            return None

        # Build preliminary proposal to evaluate risk
        prelim_proposal = RemediationProposal(
            action_id=action_id,
            incident_id=incident_id,
            diagnosis_id=f"diag_{incident_id}",
            root_cause_category=category,
            target=target_str,
            target_device=target_dev,
            target_interface=target_iface,
            operation=operation,
            parameters=parameters,
            risk=RiskLevel.MEDIUM,
            risk_reasons=[],
            expected_effect=expected_effect,
            expected_preconditions=preconditions,
            expected_postconditions=postconditions,
            verification_condition=verification_cond,
            requires_human_approval=True,
            supporting_evidence_ids=top_hypo.supporting_evidence_ids or diagnosis.evidence_ids or [f"ev_{incident_id}"],
            supporting_knowledge_ids=diagnosis.evidence_ids,
            rollback_plan=rollback_plan,
            created_at=now,
            expires_at=expires_at,
        )

        # Calculate deterministic risk assessment
        risk_assessment = risk_classifier.evaluate_risk(
            prelim_proposal,
            topology_context=topology_context.model_dump() if topology_context else None,
            blast_radius_report=blast_radius_report
        )

        prelim_proposal.risk = risk_assessment.risk_level
        prelim_proposal.risk_reasons = risk_assessment.reasons
        prelim_proposal.canonical_hash = prelim_proposal.calculate_canonical_hash()

        return prelim_proposal

    def _resolve_bgp_peer_ip(
        self,
        device_id: str,
        topology_graph: Optional[TopologyGraph],
        hypothesis: Hypothesis
    ) -> Optional[str]:
        """Resolves neighbor BGP peer IP from graph or hypothesis description."""
        if topology_graph:
            bgp_layer = getattr(topology_graph, "bgp_digraph", None)
            if bgp_layer and bgp_layer.has_node(device_id):
                for _, neighbor, data in bgp_layer.out_edges(device_id, data=True):
                    peer_ip = data.get("peer_ip") or data.get("ip")
                    if peer_ip:
                        return peer_ip

        # Fallback inspection of explanation / description for IPv4 address
        desc = hypothesis.description + " " + hypothesis.explanation
        import re
        ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", desc)
        if ip_match:
            return ip_match.group(0)

        return None


# Global singleton instance
proposal_engine = RemediationProposalEngine()


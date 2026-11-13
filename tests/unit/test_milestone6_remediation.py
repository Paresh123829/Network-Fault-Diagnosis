"""
test_milestone6_remediation.py — Unit tests for Action Registry, Proposal Engine, and Risk Classifier.
"""

import pytest
from datetime import datetime, timezone, timedelta

from services.ai.schemas.contracts import (
    DiagnosisResult,
    Hypothesis,
    RemediationProposal,
    RiskLevel,
    TopologyContext,
    TopologyNode,
    TopologyLink,
)
from services.ai.agents.remediation.action_registry import ActionRegistry, action_registry
from services.ai.agents.remediation.models import ActionDefinition
from services.ai.agents.remediation.risk import RemediationRiskClassifier, risk_classifier
from services.ai.agents.remediation.proposal_engine import RemediationProposalEngine, proposal_engine
from services.ai.agents.remediation.agent import RemediationAgent, remediation_agent


class TestActionRegistry:
    def test_default_actions_registered(self):
        ops = action_registry.list_operations()
        assert "restore_interface_admin_state" in ops
        assert "reset_bgp_session" in ops
        assert "restore_bfd_session" in ops
        assert "restore_ospf_adjacency" in ops
        assert "restore_vlan_membership" in ops
        assert len(ops) >= 5

    def test_manifest_generation(self):
        manifest = action_registry.get_manifest()
        assert len(manifest) >= 5
        for m in manifest:
            assert "operation" in m
            assert "base_risk" in m
            assert "requires_human_approval" in m
            assert m["requires_human_approval"] is True

    def test_prohibited_command_rejected_in_parameters(self):
        # Shell injection attempt
        valid, errors = action_registry.validate_operation_and_parameters(
            "restore_interface_admin_state",
            {"target_device": "leaf1; reboot", "target_interface": "Ethernet1/1", "admin_state": "UP"}
        )
        assert valid is False
        assert any("prohibited shell characters" in e or "prohibited command keyword" in e for e in errors)

    def test_unexpected_parameters_rejected(self):
        valid, errors = action_registry.validate_operation_and_parameters(
            "reset_bgp_session",
            {"target_device": "leaf1", "peer_ip": "10.0.0.1", "malicious_payload": "rm -rf"}
        )
        assert valid is False
        assert any("Unexpected parameter" in e for e in errors)

    def test_missing_required_parameters_rejected(self):
        valid, errors = action_registry.validate_operation_and_parameters(
            "restore_vlan_membership",
            {"target_device": "leaf1"}  # Missing interface & vlan_id
        )
        assert valid is False
        assert any("Missing required parameter" in e for e in errors)

    def test_vlan_range_validation(self):
        # Invalid VLAN ID 5000 (valid is 1-4094)
        valid, errors = action_registry.validate_operation_and_parameters(
            "restore_vlan_membership",
            {"target_device": "leaf1", "interface": "Ethernet1/1", "vlan_id": 5000}
        )
        assert valid is False
        assert any("failed validation rule" in e for e in errors)


class TestRemediationRiskClassifier:
    def test_low_risk_action_evaluation(self):
        prop = RemediationProposal(
            action_id="act_test_1",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            target_interface="Ethernet1/1",
            operation="restore_vlan_membership",
            parameters={"target_device": "leaf1", "interface": "Ethernet1/1", "vlan_id": 100},
            risk=RiskLevel.LOW,
            expected_effect="Restores VLAN",
            verification_condition="vlan_membership_restored",
            rollback_plan={"operation": "revert_vlan_membership", "parameters": {}},
        )
        ass = risk_classifier.evaluate_risk(prop)
        assert ass.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
        assert ass.is_reversible is True
        assert len(ass.reasons) > 0

    def test_critical_risk_due_to_unreachability(self):
        prop = RemediationProposal(
            action_id="act_test_2",
            target="spine1",
            target_device="spine1",
            operation="reset_bgp_session",
            parameters={"target_device": "spine1", "peer_ip": "10.0.0.1"},
            risk=RiskLevel.HIGH,
            expected_effect="Resets BGP",
            verification_condition="bgp_session_is_established",
        )
        # Blast radius report with zero surviving paths and high NUR
        blast_rep = {
            "device_spine1": {
                "impact_exposure_ratio": 0.90,
                "network_unreachability_ratio": 0.50,
                "lost_paths_count": 10,
                "surviving_alternate_paths_count": 0,
            }
        }
        ass = risk_classifier.evaluate_risk(prop, blast_radius_report=blast_rep)
        assert ass.risk_level == RiskLevel.CRITICAL
        assert any("Zero surviving alternate paths" in r for r in ass.reasons)


class TestProposalEngine:
    def test_bgp_proposal_generation(self):
        diag = DiagnosisResult(
            hypotheses=[
                Hypothesis(
                    hypothesis_id="hypo_1",
                    description="BGP peering session down between leaf1 and spine1",
                    confidence=0.92,
                    root_cause_category="bgp_neighbor_down",
                    affected_devices=["leaf1"],
                    affected_interfaces=["Ethernet1/1"],
                    explanation="Peer 10.0.1.2 transitioned to IDLE",
                )
            ],
            probable_root_cause="BGP neighbor down",
            evidence_ids=["ev_1"],
            confidence=0.92,
            affected_components=["leaf1"],
        )
        prop = proposal_engine.generate_proposal(
            incident_id="inc_bgp_test",
            diagnosis=diag
        )
        assert prop is not None
        assert prop.operation == "reset_bgp_session"
        assert prop.target_device == "leaf1"
        assert prop.rollback_plan is not None
        assert prop.canonical_hash != ""
        assert prop.requires_human_approval is True

    def test_low_confidence_proposal_rejected(self):
        diag = DiagnosisResult(
            hypotheses=[
                Hypothesis(
                    hypothesis_id="hypo_low",
                    description="Uncertain root cause",
                    confidence=0.45,  # Below 0.60 safe threshold
                    root_cause_category="bgp_neighbor_down",
                    affected_devices=["leaf1"],
                )
            ],
            probable_root_cause="Uncertain",
            confidence=0.45,
            affected_components=["leaf1"],
        )
        prop = proposal_engine.generate_proposal(
            incident_id="inc_low_conf",
            diagnosis=diag
        )
        assert prop is None  # Must not generate proposal for low confidence


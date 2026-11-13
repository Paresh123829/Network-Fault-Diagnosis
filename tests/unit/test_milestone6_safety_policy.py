"""
test_milestone6_safety_policy.py — Mandatory negative safety tests and policy enforcement.
"""

import pytest
from datetime import datetime, timezone, timedelta

from services.ai.schemas.contracts import (
    PolicyStatus,
    RemediationProposal,
    RiskLevel,
)
from services.ai.agents.remediation.policy import RemediationPolicyEngine, remediation_policy
from services.ai.agents.oversight.kill_switch import kill_switch
from services.ai.agents.topology.graph import TopologyGraph
from services.ai.agents.topology.model import (
    NetworkDevice, DeviceType, NetworkInterface, InterfaceType, PhysicalLink, TopologyGraphModel
)


@pytest.fixture
def sample_topology():
    topo = TopologyGraphModel(
        devices={
            "leaf1": NetworkDevice(
                device_id="leaf1",
                canonical_name="leaf1",
                device_type=DeviceType.LEAF,
                interfaces={
                    "Ethernet1/1": NetworkInterface(interface_id="leaf1:Ethernet1/1", device_id="leaf1", name="Ethernet1/1"),
                    "Ethernet1/2": NetworkInterface(interface_id="leaf1:Ethernet1/2", device_id="leaf1", name="Ethernet1/2"),
                }
            ),
            "spine1": NetworkDevice(
                device_id="spine1",
                canonical_name="spine1",
                device_type=DeviceType.SPINE,
                interfaces={
                    "Ethernet1/1": NetworkInterface(interface_id="spine1:Ethernet1/1", device_id="spine1", name="Ethernet1/1"),
                }
            ),
        },
        physical_links=[
            PhysicalLink(link_id="link1", source_device="leaf1", source_interface="Ethernet1/1", target_device="spine1", target_interface="Ethernet1/1")
        ]
    )
    return TopologyGraph(topo)


class TestSafetyPolicyEngine:
    def setup_method(self):
        kill_switch.reset_all()
        remediation_policy.set_topology_graph(None)

    def teardown_method(self):
        kill_switch.reset_all()
        remediation_policy.set_topology_graph(None)

    def test_negative_unknown_operation_rejected(self):
        prop = RemediationProposal(
            action_id="act_unknown_op",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            operation="reboot_chassis",  # Not allow-listed
            parameters={"target_device": "leaf1"},
            risk=RiskLevel.CRITICAL,
            expected_effect="Dangerous operation",
            verification_condition="none",
        )
        dec = remediation_policy.evaluate_proposal(prop)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_UNKNOWN_OPERATION
        assert any("not an authorized allow-listed" in r for r in dec.reasons)

    def test_negative_shell_injection_rejected(self):
        prop = RemediationProposal(
            action_id="act_shell_inj",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            operation="restore_interface_admin_state",
            parameters={
                "target_device": "leaf1",
                "target_interface": "Ethernet1/1; rm -rf /",
                "admin_state": "UP"
            },
            risk=RiskLevel.MEDIUM,
            expected_effect="Test shell injection",
            verification_condition="none",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
        )
        dec = remediation_policy.evaluate_proposal(prop)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_INVALID_PARAMETERS
        assert any("prohibited shell characters" in r for r in dec.reasons)

    def test_negative_invalid_device_rejected(self, sample_topology):
        remediation_policy.set_topology_graph(sample_topology)
        prop = RemediationProposal(
            action_id="act_fake_dev",
            target="core99:Ethernet1/1",
            target_device="core99",  # Does not exist
            target_interface="Ethernet1/1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "core99", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Fix fake device",
            verification_condition="none",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
        )
        dec = remediation_policy.evaluate_proposal(prop, topology_graph=sample_topology)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_UNKNOWN_TARGET
        assert any("does not exist in validated network topology" in r for r in dec.reasons)

    def test_negative_invalid_interface_rejected(self, sample_topology):
        remediation_policy.set_topology_graph(sample_topology)
        prop = RemediationProposal(
            action_id="act_wrong_iface",
            target="leaf1:Ethernet99/99",  # Ethernet99/99 does not belong to leaf1
            target_device="leaf1",
            target_interface="Ethernet99/99",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet99/99", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Fix wrong iface",
            verification_condition="none",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
        )
        dec = remediation_policy.evaluate_proposal(prop, topology_graph=sample_topology)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_INVALID_TOPOLOGY
        assert any("does not belong to target device" in r for r in dec.reasons)

    def test_negative_insufficient_evidence_rejected(self):
        prop = RemediationProposal(
            action_id="act_no_evidence",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="No evidence proposal",
            verification_condition="none",
            supporting_evidence_ids=[],  # Empty evidence
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
        )
        dec = remediation_policy.evaluate_proposal(prop)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_INSUFFICIENT_EVIDENCE
        assert any("lacks supporting telemetry" in r for r in dec.reasons)

    def test_negative_expired_proposal_rejected(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=10)
        prop = RemediationProposal(
            action_id="act_expired",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Expired action",
            verification_condition="none",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
            expires_at=past,
        )
        dec = remediation_policy.evaluate_proposal(prop)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_EXPIRED_PROPOSAL
        assert any("Proposal expired" in r for r in dec.reasons)

    def test_negative_tampered_proposal_hash_rejected(self):
        prop = RemediationProposal(
            action_id="act_tampered",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Tampered action",
            verification_condition="none",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
        )
        # Deliberately falsify canonical hash
        prop.canonical_hash = "deadbeef" * 8
        dec = remediation_policy.evaluate_proposal(prop)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_UNSAFE_OPERATION
        assert any("Tampering detected" in r for r in dec.reasons)

    def test_negative_active_kill_switch_rejected(self):
        kill_switch.activate_global("Emergency maintenance freeze", actor="admin")
        prop = RemediationProposal(
            action_id="act_ks_blocked",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Action under freeze",
            verification_condition="none",
            supporting_evidence_ids=["ev_1"],
            rollback_plan={"operation": "disable_interface_admin_state", "parameters": {}},
        )
        dec = remediation_policy.evaluate_proposal(prop)
        assert dec.is_allowed is False
        assert dec.status == PolicyStatus.REJECTED_KILL_SWITCH_ACTIVE
        assert any("kill switch is ACTIVE" in r for r in dec.reasons)

    def test_positive_valid_proposal_allowed_for_review(self, sample_topology):
        remediation_policy.set_topology_graph(sample_topology)
        prop = RemediationProposal(
            action_id="act_valid_1",
            target="leaf1:Ethernet1/1",
            target_device="leaf1",
            target_interface="Ethernet1/1",
            operation="restore_interface_admin_state",
            parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "UP"},
            risk=RiskLevel.MEDIUM,
            expected_effect="Restores admin UP",
            verification_condition="interface_operational_state_is_up",
            supporting_evidence_ids=["ev_cisco_case4"],
            rollback_plan={
                "operation": "disable_interface_admin_state",
                "parameters": {"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "DOWN"}
            },
        )
        dec = remediation_policy.evaluate_proposal(prop, topology_graph=sample_topology)
        assert dec.is_allowed is True
        assert dec.status == PolicyStatus.ALLOWED_FOR_REVIEW

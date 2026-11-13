"""
Unit tests for Milestone 6.1 immutable execution snapshots.
"""

from datetime import datetime, timezone
import pytest

from services.ai.schemas.contracts import RemediationProposal, RiskLevel
from services.ai.agents.remediation.snapshot_manager import (
    SnapshotManager,
    ExecutionStateSnapshot,
    RollbackClassification,
)
from automation.simulated_executor.state_manager import NetworkSimulatorStateManager


@pytest.fixture
def test_sim():
    sim = NetworkSimulatorStateManager()
    sim.initialize_default_cisco_clos()
    return sim


@pytest.fixture
def snapshot_mgr():
    mgr = SnapshotManager()
    mgr.persistence.check_connection = lambda: False  # In-memory test isolation
    return mgr


def test_snapshot_interface_admin_state(test_sim, snapshot_mgr):
    # Set non-default interface attributes
    test_sim.set_interface_config(
        device_id="leaf1",
        interface_name="Ethernet1/1",
        admin_state="UP",
        operational_state="UP",
        speed="100G",
        vlan_id=200,
        mode="trunk",
        native_vlan=1,
        allowed_vlans=[100, 200, 300],
        mtu=9000,
    )

    prop = RemediationProposal(
        action_id="prop_iface_01",
        incident_id="inc_01",
        target="leaf1:Ethernet1/1",
        target_device="leaf1",
        target_interface="Ethernet1/1",
        operation="restore_interface_admin_state",
        parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "DOWN"},
        risk=RiskLevel.MEDIUM,
        expected_effect="Test",
        verification_condition="none",
    )

    snap = snapshot_mgr.capture_pre_execution_snapshot(test_sim, prop, "exec_01")
    assert snap.snapshot_id.startswith("snap_")
    assert snap.rollback_classification == RollbackClassification.EXACT_STATE_RESTORE
    assert snap.state_before["vlan_id"] == 200
    assert snap.state_before["mode"] == "trunk"
    assert snap.state_before["allowed_vlans"] == [100, 200, 300]
    assert snap.state_before["mtu"] == 9000
    assert snap.verify_hash() is True


def test_snapshot_bgp_compensating_classification(test_sim, snapshot_mgr):
    prop = RemediationProposal(
        action_id="prop_bgp_01",
        incident_id="inc_02",
        target="leaf5:10.0.1.2",
        target_device="leaf5",
        operation="reset_bgp_session",
        parameters={"target_device": "leaf5", "peer_ip": "10.0.1.2", "soft_reset": True},
        risk=RiskLevel.MEDIUM,
        expected_effect="Test",
        verification_condition="none",
    )

    snap = snapshot_mgr.capture_pre_execution_snapshot(test_sim, prop, "exec_02")
    assert snap.rollback_classification == RollbackClassification.COMPENSATING_RECOVERY
    assert snap.state_before["peer_ip"] == "10.0.1.2"
    assert snap.verify_hash() is True


def test_snapshot_tamper_detection(test_sim, snapshot_mgr):
    prop = RemediationProposal(
        action_id="prop_vlan_01",
        incident_id="inc_03",
        target="leaf8:Ethernet1/1",
        target_device="leaf8",
        target_interface="Ethernet1/1",
        operation="restore_vlan_membership",
        parameters={"target_device": "leaf8", "interface": "Ethernet1/1", "vlan_id": 50},
        risk=RiskLevel.LOW,
        expected_effect="Test",
        verification_condition="none",
    )

    snap = snapshot_mgr.capture_pre_execution_snapshot(test_sim, prop, "exec_03")
    assert snap.verify_hash() is True

    # Mutate snapshot payload
    snap.state_before["vlan_id"] = 999
    assert snap.verify_hash() is False, "Altered payload must invalidate snapshot_hash!"


def test_snapshot_bfd_and_ospf_capture(test_sim, snapshot_mgr):
    test_sim.set_bfd_session_config("leaf2", "10.0.2.1", interval_ms=150, multiplier=5, state="UP")
    prop_bfd = RemediationProposal(
        action_id="prop_bfd_01",
        incident_id="inc_04",
        target="leaf2:10.0.2.1",
        target_device="leaf2",
        operation="restore_bfd_session",
        parameters={"target_device": "leaf2", "peer_ip": "10.0.2.1"},
        risk=RiskLevel.LOW,
        expected_effect="Test",
        verification_condition="none",
    )
    snap_bfd = snapshot_mgr.capture_pre_execution_snapshot(test_sim, prop_bfd, "exec_04")
    assert snap_bfd.state_before["interval_ms"] == 150
    assert snap_bfd.state_before["multiplier"] == 5
    assert snap_bfd.verify_hash() is True


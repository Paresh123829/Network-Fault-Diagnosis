"""
Unit tests for Milestone 6.1 exact pre-state rollback and compensating recovery.
"""

import pytest

from services.ai.schemas.contracts import RemediationProposal, RiskLevel, RollbackStatus
from services.ai.agents.remediation.snapshot_manager import (
    SnapshotManager,
    RollbackClassification,
)
from automation.simulated_executor.state_manager import NetworkSimulatorStateManager
from automation.simulated_executor.rollback import RemediationRollbackEngine


@pytest.fixture
def sim():
    s = NetworkSimulatorStateManager()
    s.initialize_default_cisco_clos()
    return s


@pytest.fixture
def snapshot_mgr():
    mgr = SnapshotManager()
    mgr.persistence.check_connection = lambda: False
    return mgr


@pytest.fixture
def rollback_eng(sim):
    return RemediationRollbackEngine(sim=sim)


def test_exact_vlan_restoration(sim, snapshot_mgr, rollback_eng):
    # Baseline: leaf8 Ethernet1/1 is on VLAN 300 with trunk mode and allowed [100, 200, 300]
    sim.set_interface_config(
        device_id="leaf8",
        interface_name="Ethernet1/1",
        vlan_id=300,
        mode="trunk",
        allowed_vlans=[100, 200, 300],
    )
    assert sim.get_vlan("leaf8", "Ethernet1/1") == 300

    prop = RemediationProposal(
        action_id="prop_vlan_exact",
        incident_id="inc_vlan",
        target="leaf8:Ethernet1/1",
        target_device="leaf8",
        target_interface="Ethernet1/1",
        operation="restore_vlan_membership",
        parameters={"target_device": "leaf8", "interface": "Ethernet1/1", "vlan_id": 10},
        risk=RiskLevel.LOW,
        expected_effect="Move to VLAN 10",
        verification_condition="none",
        rollback_plan={"operation": "restore_vlan_membership", "parameters": {}},
    )

    # 1. Capture snapshot before change
    snap = snapshot_mgr.capture_pre_execution_snapshot(sim, prop, "exec_vlan_01")

    # 2. Mutate state (e.g. action modifies port to VLAN 10)
    sim.set_interface_config("leaf8", "Ethernet1/1", vlan_id=10, mode="access", allowed_vlans=[10])
    assert sim.get_vlan("leaf8", "Ethernet1/1") == 10

    # 3. Execute rollback using snapshot
    res = rollback_eng.execute_rollback(
        proposal=prop,
        execution_id="exec_vlan_01",
        pre_state_snapshot=snap,
        sim=sim,
    )

    assert res.status == RollbackStatus.SUCCEEDED
    assert res.is_verified is True
    # Confirm exact restoration (not defaulted to VLAN 1!)
    assert sim.get_vlan("leaf8", "Ethernet1/1") == 300
    iface_state = sim.get_interface("leaf8", "Ethernet1/1")
    assert iface_state["mode"] == "trunk"
    assert iface_state["allowed_vlans"] == [100, 200, 300]


def test_exact_bfd_interval_restoration(sim, snapshot_mgr, rollback_eng):
    sim.set_bfd_session_config("leaf2", "10.0.2.1", interval_ms=150, multiplier=5, state="UP")
    prop = RemediationProposal(
        action_id="prop_bfd_exact",
        incident_id="inc_bfd",
        target="leaf2:10.0.2.1",
        target_device="leaf2",
        operation="restore_bfd_session",
        parameters={"target_device": "leaf2", "peer_ip": "10.0.2.1", "interval_ms": 500, "multiplier": 8},
        risk=RiskLevel.LOW,
        expected_effect="Change BFD timers",
        verification_condition="none",
    )

    snap = snapshot_mgr.capture_pre_execution_snapshot(sim, prop, "exec_bfd_01")

    # Mutate to 500ms
    sim.set_bfd_session_config("leaf2", "10.0.2.1", interval_ms=500, multiplier=8)

    # Rollback
    res = rollback_eng.execute_rollback(proposal=prop, execution_id="exec_bfd_01", pre_state_snapshot=snap, sim=sim)
    assert res.status == RollbackStatus.SUCCEEDED

    bfd_state = sim.get_bfd_session("leaf2", "10.0.2.1")
    assert bfd_state["interval_ms"] == 150
    assert bfd_state["multiplier"] == 5


def test_bgp_compensating_recovery(sim, snapshot_mgr, rollback_eng):
    sim.set_bgp_session_state("leaf5", "10.0.1.2", "ESTABLISHED")
    prop = RemediationProposal(
        action_id="prop_bgp_comp",
        incident_id="inc_bgp",
        target="leaf5:10.0.1.2",
        target_device="leaf5",
        operation="reset_bgp_session",
        parameters={"target_device": "leaf5", "peer_ip": "10.0.1.2", "soft_reset": True},
        risk=RiskLevel.MEDIUM,
        expected_effect="Reset BGP",
        verification_condition="none",
    )

    snap = snapshot_mgr.capture_pre_execution_snapshot(sim, prop, "exec_bgp_01")
    assert snap.rollback_classification == RollbackClassification.COMPENSATING_RECOVERY

    # Break session
    sim.set_bgp_session_state("leaf5", "10.0.1.2", "IDLE")

    res = rollback_eng.execute_rollback(proposal=prop, execution_id="exec_bgp_01", pre_state_snapshot=snap, sim=sim)
    assert res.status == RollbackStatus.SUCCEEDED
    assert res.restored_state["classification"] == "COMPENSATING_RECOVERY"
    assert sim.get_bgp_session("leaf5", "10.0.1.2")["session_state"] == "ESTABLISHED"


def test_rollback_refuses_corrupted_snapshot(sim, snapshot_mgr, rollback_eng):
    prop = RemediationProposal(
        action_id="prop_corrupt",
        incident_id="inc_c",
        target="leaf1:Ethernet1/1",
        target_device="leaf1",
        operation="restore_interface_admin_state",
        parameters={"target_device": "leaf1", "target_interface": "Ethernet1/1", "admin_state": "DOWN"},
        risk=RiskLevel.MEDIUM,
        expected_effect="Test",
        verification_condition="none",
    )

    snap = snapshot_mgr.capture_pre_execution_snapshot(sim, prop, "exec_c_01")
    # Corrupt hash
    snap.snapshot_hash = "0" * 64

    res = rollback_eng.execute_rollback(proposal=prop, execution_id="exec_c_01", pre_state_snapshot=snap, sim=sim)
    assert res.status == RollbackStatus.MANUAL_INTERVENTION_REQUIRED
    assert "cryptographic hash mismatch" in res.failure_reason


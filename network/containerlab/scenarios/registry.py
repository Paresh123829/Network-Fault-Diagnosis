"""
registry.py — Predefined Scenario Registry for Milestone 7.

Defines the 5 core deterministic fault scenarios:
1. Scenario 1: BGP Neighbor Failure
2. Scenario 2: OSPF Adjacency Failure
3. Scenario 3: VLAN / Layer 2 Connectivity Failure
4. Scenario 4: Physical Link Failure & Interface Flapping
5. Scenario 5: BFD Session Failure
"""

from __future__ import annotations

from typing import Dict, List, Optional

from services.ai.schemas.contracts import EventType, Severity
from .models import (
    ExpectedDiagnosis,
    ExpectedSymptom,
    FaultProtocol,
    RecoveryActionDefinition,
    ScenarioDefinition,
    ScenarioPrecondition,
    VerificationCriteria,
)

# ─── Scenario 1: BGP Neighbor Failure ─────────────────────────────────────────

SCENARIO_1_BGP = ScenarioDefinition(
    scenario_id="CLAB_SCENARIO_1_BGP",
    name="BGP Neighbor Session Failure & Recovery",
    description="Clears the eBGP session between R1 and R2, verifying route withdrawal, diagnosis, and soft-reconverged recovery.",
    protocol=FaultProtocol.BGP,
    target_node="R1",
    target_component="172.16.12.2",
    preconditions=[
        ScenarioPrecondition(
            check_type="bgp_neighbor",
            target_node="R1",
            target_identifier="172.16.12.2",
            expected_value="Established",
        ),
    ],
    fault_operation="clear_bgp_session",
    fault_parameters={"target_node": "R1", "peer_ip": "172.16.12.2"},
    expected_symptoms=[
        ExpectedSymptom(
            event_type=EventType.BGP_NEIGHBOR_DOWN,
            severity=Severity.HIGH,
            description="BGP neighbor 172.16.12.2 state dropped from Established to Idle/Active",
            syslog_pattern="%ROUTING-BGP-5-ADJCHANGE: neighbor 172.16.12.2 Down",
        ),
        ExpectedSymptom(
            event_type=EventType.BGP_ANOMALY,
            severity=Severity.HIGH,
            description="Routes learned from peer 172.16.12.2 withdrawn from routing table",
            syslog_pattern=None,
        ),
    ],
    expected_diagnosis=ExpectedDiagnosis(
        expected_root_cause="BGP Neighbor Session Down / Process Reset",
        expected_device="R1",
        expected_component="172.16.12.2",
        expected_protocol="bgp",
    ),
    recovery_action=RecoveryActionDefinition(
        operation="reset_bgp_session",
        target_node="R1",
        parameters={"target_device": "R1", "peer_ip": "172.16.12.2"},
        is_compensating=True,
    ),
    verification_criteria=VerificationCriteria(
        protocol=FaultProtocol.BGP,
        target_node="R1",
        target_identifier="172.16.12.2",
        expected_state="Established",
        expected_routes=["10.0.0.2/32"],
    ),
    timeout_seconds=25.0,
)

# ─── Scenario 2: OSPF Adjacency Failure ───────────────────────────────────────

SCENARIO_2_OSPF = ScenarioDefinition(
    scenario_id="CLAB_SCENARIO_2_OSPF",
    name="OSPF Adjacency Failure & Timer Recovery",
    description="Induces OSPF adjacency loss on R2 eth1 via dead-interval mismatch, testing adjacency loss detection and parameter restoration.",
    protocol=FaultProtocol.OSPF,
    target_node="R2",
    target_component="eth1",
    preconditions=[
        ScenarioPrecondition(
            check_type="ospf_neighbor",
            target_node="R2",
            target_identifier="eth1",
            expected_value="Full",
        ),
    ],
    fault_operation="set_ospf_timer_mismatch",
    fault_parameters={"target_node": "R2", "interface": "eth1", "hello_interval": 20, "dead_interval": 80},
    expected_symptoms=[
        ExpectedSymptom(
            event_type=EventType.OSPF_ADJACENCY_FAILURE,
            severity=Severity.HIGH,
            description="OSPF neighbor adjacency to 10.0.0.1 on eth1 transitioned to Down (dead timer expired)",
            syslog_pattern="%OSPF-5-ADJCHANGE: Nbr 10.0.0.1 on eth1 Down",
        ),
        ExpectedSymptom(
            event_type=EventType.OSPF_NEIGHBOR_DOWN,
            severity=Severity.HIGH,
            description="OSPF routes via neighbor 10.0.0.1 purged from RIB",
            syslog_pattern=None,
        ),
    ],
    expected_diagnosis=ExpectedDiagnosis(
        expected_root_cause="OSPF Adjacency Loss / Timer Mismatch",
        expected_device="R2",
        expected_component="eth1",
        expected_protocol="ospf",
    ),
    recovery_action=RecoveryActionDefinition(
        operation="restore_ospf_adjacency",
        target_node="R2",
        parameters={"target_device": "R2", "interface": "eth1", "hello_interval": 5, "dead_interval": 20},
        is_compensating=False,
    ),
    verification_criteria=VerificationCriteria(
        protocol=FaultProtocol.OSPF,
        target_node="R2",
        target_identifier="eth1",
        expected_state="Full",
        expected_routes=["10.0.0.1/32"],
    ),
    timeout_seconds=25.0,
)

# ─── Scenario 3: VLAN / Layer 2 Connectivity Failure ──────────────────────────

SCENARIO_3_VLAN = ScenarioDefinition(
    scenario_id="CLAB_SCENARIO_3_VLAN",
    name="VLAN / Layer 2 Isolation & Membership Recovery",
    description="Alters the bridge port PVID on br-vlan:eth3, isolating client1 from its default gateway on R1, validating L2 diagnosis and membership restore.",
    protocol=FaultProtocol.VLAN,
    target_node="br-vlan",
    target_component="eth3",
    preconditions=[
        ScenarioPrecondition(
            check_type="vlan_membership",
            target_node="br-vlan",
            target_identifier="eth3",
            expected_value=100,
        ),
        ScenarioPrecondition(
            check_type="vlan_ping",
            target_node="client1",
            target_identifier="192.168.100.1",
            expected_value=0.0,  # 0% packet loss
        ),
    ],
    fault_operation="set_bridge_vlan_mismatch",
    fault_parameters={"target_node": "br-vlan", "interface": "eth3", "fault_vid": 200},
    expected_symptoms=[
        ExpectedSymptom(
            event_type=EventType.VLAN_FAULT,
            severity=Severity.HIGH,
            description="Bridge port eth3 assigned invalid PVID 200, isolating VLAN 100 client",
            syslog_pattern=None,
        ),
        ExpectedSymptom(
            event_type=EventType.CONNECTIVITY_FAULT,
            severity=Severity.CRITICAL,
            description="100% packet loss on client1 ping probe to gateway 192.168.100.1",
            syslog_pattern=None,
        ),
    ],
    expected_diagnosis=ExpectedDiagnosis(
        expected_root_cause="VLAN Configuration Mismatch / L2 Isolation",
        expected_device="br-vlan",
        expected_component="eth3",
        expected_protocol="vlan",
    ),
    recovery_action=RecoveryActionDefinition(
        operation="restore_vlan_membership",
        target_node="br-vlan",
        parameters={"target_device": "br-vlan", "target_interface": "eth3", "vlan_id": 100},
        is_compensating=False,
    ),
    verification_criteria=VerificationCriteria(
        protocol=FaultProtocol.VLAN,
        target_node="br-vlan",
        target_identifier="eth3",
        expected_state="vlan_100_active",
        ping_target="192.168.100.1",
        max_packet_loss_percent=0.0,
    ),
    timeout_seconds=25.0,
)

# ─── Scenario 4: Physical Link Failure & Interface Flapping ───────────────────

SCENARIO_4_LINK_FLAP = ScenarioDefinition(
    scenario_id="CLAB_SCENARIO_4_LINK_FLAP",
    name="Interface Flapping & Admin State Recovery",
    description="Executes a deterministic multi-transition flap sequence on R2 eth1, leaving the interface in admin-down state, testing flap detection and state restore.",
    protocol=FaultProtocol.INTERFACE,
    target_node="R2",
    target_component="eth1",
    preconditions=[
        ScenarioPrecondition(
            check_type="interface_state",
            target_node="R2",
            target_identifier="eth1",
            expected_value="UP",
        ),
    ],
    fault_operation="flap_interface_bounded",
    fault_parameters={"target_node": "R2", "interface": "eth1", "flap_count": 2, "interval_seconds": 1.0},
    expected_symptoms=[
        ExpectedSymptom(
            event_type=EventType.PORT_FLAP,
            severity=Severity.HIGH,
            description="Interface eth1 experienced rapid successive up/down transitions",
            syslog_pattern="%PKT_INFRA-LINK-3-UPDOWN: Interface eth1, changed state to Down",
        ),
        ExpectedSymptom(
            event_type=EventType.PORT_ADMIN_SHUTDOWN,
            severity=Severity.HIGH,
            description="Interface eth1 settled into admin-down state",
            syslog_pattern=None,
        ),
    ],
    expected_diagnosis=ExpectedDiagnosis(
        expected_root_cause="Physical Link Flapping / Admin Shutdown",
        expected_device="R2",
        expected_component="eth1",
        expected_protocol="interface",
    ),
    recovery_action=RecoveryActionDefinition(
        operation="restore_interface_admin_state",
        target_node="R2",
        parameters={"target_device": "R2", "target_interface": "eth1", "admin_state": "UP"},
        is_compensating=False,
    ),
    verification_criteria=VerificationCriteria(
        protocol=FaultProtocol.INTERFACE,
        target_node="R2",
        target_identifier="eth1",
        expected_state="UP",
        expected_routes=["172.16.12.0/30"],
    ),
    timeout_seconds=30.0,
)

# ─── Scenario 5: BFD Session Failure ──────────────────────────────────────────

SCENARIO_5_BFD = ScenarioDefinition(
    scenario_id="CLAB_SCENARIO_5_BFD",
    name="BFD Session Failure & Sub-Second Convergence Recovery",
    description="Administratively disables the BFD session on R1 to peer 172.16.12.2, testing fast failure detection and session un-shutdown recovery.",
    protocol=FaultProtocol.BFD,
    target_node="R1",
    target_component="172.16.12.2",
    preconditions=[
        ScenarioPrecondition(
            check_type="bfd_peer",
            target_node="R1",
            target_identifier="172.16.12.2",
            expected_value="Up",
        ),
    ],
    fault_operation="disable_bfd_peer",
    fault_parameters={"target_node": "R1", "peer_ip": "172.16.12.2"},
    expected_symptoms=[
        ExpectedSymptom(
            event_type=EventType.PORT_DOWN,
            severity=Severity.HIGH,
            description="BFD session to 172.16.12.2 transitioned from Up to Down / AdminDown",
            syslog_pattern="%BFD-5-STATE_CHANGE: BFD session to 172.16.12.2 Down",
        ),
    ],
    expected_diagnosis=ExpectedDiagnosis(
        expected_root_cause="BFD Session Down / Sub-Second Failure",
        expected_device="R1",
        expected_component="172.16.12.2",
        expected_protocol="bfd",
    ),
    recovery_action=RecoveryActionDefinition(
        operation="restore_bfd_session",
        target_node="R1",
        parameters={"target_device": "R1", "peer_ip": "172.16.12.2"},
        is_compensating=False,
    ),
    verification_criteria=VerificationCriteria(
        protocol=FaultProtocol.BFD,
        target_node="R1",
        target_identifier="172.16.12.2",
        expected_state="Up",
    ),
    timeout_seconds=25.0,
)

# ─── Registry Mapping ─────────────────────────────────────────────────────────

ALL_SCENARIOS: List[ScenarioDefinition] = [
    SCENARIO_1_BGP,
    SCENARIO_2_OSPF,
    SCENARIO_3_VLAN,
    SCENARIO_4_LINK_FLAP,
    SCENARIO_5_BFD,
]

SCENARIO_MAP: Dict[str, ScenarioDefinition] = {s.scenario_id: s for s in ALL_SCENARIOS}


def get_scenario(scenario_id: str) -> Optional[ScenarioDefinition]:
    return SCENARIO_MAP.get(scenario_id)


def list_scenarios() -> List[ScenarioDefinition]:
    return list(ALL_SCENARIOS)


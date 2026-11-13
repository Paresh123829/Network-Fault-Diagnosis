"""
test_milestone7_scenarios.py — Unit tests for Milestone 7 Scenario Definitions and Registry.
"""

import pytest

from network.containerlab.scenarios.models import (
    FaultProtocol,
    ScenarioDefinition,
    ScenarioPrecondition,
    ExpectedSymptom,
    RecoveryActionDefinition,
    VerificationCriteria,
)
from network.containerlab.scenarios.registry import (
    ALL_SCENARIOS,
    get_scenario,
    list_scenarios,
)
from network.containerlab.runtime.driver import VALID_LAB_NODES


def test_scenario_registry_completeness():
    scenarios = list_scenarios()
    assert len(scenarios) == 5, f"Expected 5 scenarios, found {len(scenarios)}"
    
    expected_ids = {
        "CLAB_SCENARIO_1_BGP",
        "CLAB_SCENARIO_2_OSPF",
        "CLAB_SCENARIO_3_VLAN",
        "CLAB_SCENARIO_4_LINK_FLAP",
        "CLAB_SCENARIO_5_BFD",
    }
    actual_ids = {s.scenario_id for s in scenarios}
    assert actual_ids == expected_ids


def test_scenario_target_inventory_containment():
    for sc in ALL_SCENARIOS:
        assert sc.target_node in VALID_LAB_NODES, f"Scenario {sc.scenario_id} targets unauthorized node {sc.target_node}"
        assert sc.recovery_action.target_node in VALID_LAB_NODES, f"Recovery for {sc.scenario_id} targets unauthorized node"
        assert sc.verification_criteria.target_node in VALID_LAB_NODES, f"Verification for {sc.scenario_id} targets unauthorized node"


def test_scenario_protocols_valid():
    valid_protocols = {FaultProtocol.BGP, FaultProtocol.OSPF, FaultProtocol.VLAN, FaultProtocol.INTERFACE, FaultProtocol.BFD}
    for sc in ALL_SCENARIOS:
        assert sc.protocol in valid_protocols
        assert sc.verification_criteria.protocol == sc.protocol


def test_get_scenario_valid_and_invalid():
    sc = get_scenario("CLAB_SCENARIO_1_BGP")
    assert sc is not None
    assert sc.scenario_id == "CLAB_SCENARIO_1_BGP"
    assert sc.protocol == FaultProtocol.BGP

    invalid = get_scenario("NON_EXISTENT_SCENARIO")
    assert invalid is None


"""
test_milestone7_injection.py — Unit tests for Milestone 7 Fault Injection Engine.
"""

import pytest

from network.containerlab.fault_injection.injector import FaultInjector
from network.containerlab.scenarios.registry import get_scenario
from network.containerlab.runtime.mock_provider import ContainerlabMockProvider


@pytest.fixture
def injector():
    from network.containerlab.runtime.mock_provider import mock_clab_provider
    mock_clab_provider.reset_to_baseline()
    yield FaultInjector(force_mock=True)
    mock_clab_provider.reset_to_baseline()


def test_precondition_check_healthy(injector):
    sc = get_scenario("CLAB_SCENARIO_1_BGP")
    ok, failures = injector.check_preconditions(sc)
    assert ok is True
    assert len(failures) == 0


def test_pre_state_capture(injector):
    sc = get_scenario("CLAB_SCENARIO_1_BGP")
    snapshot = injector.capture_pre_state(sc)
    assert "bgp_summary" in snapshot
    assert "172.16.12.2" in snapshot["bgp_summary"]


def test_fault_injection_success(injector):
    sc = get_scenario("CLAB_SCENARIO_1_BGP")
    res = injector.inject_fault(sc)
    assert res.success is True
    assert res.scenario_id == "CLAB_SCENARIO_1_BGP"
    assert res.target_node == "R1"
    assert not res.error


def test_unauthorized_node_rejected(injector):
    sc = get_scenario("CLAB_SCENARIO_1_BGP")
    # Clone scenario and mutate target node to production switch
    mutated = sc.model_copy(update={"target_node": "core_switch_prod_01"})
    res = injector.inject_fault(mutated)
    assert res.success is False
    assert "unauthorized node" in res.error.lower()

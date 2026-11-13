"""
test_milestone7_e2e_pipeline.py — Integration test executing the complete closed-loop diagnostic and safe remediation cycle.
"""

import pytest

from network.containerlab.scenarios.registry import ALL_SCENARIOS
from network.containerlab.experiments.runner import clab_experiment_runner


@pytest.mark.parametrize("scenario", ALL_SCENARIOS, ids=lambda s: s.scenario_id)
def test_scenario_closed_loop_e2e(scenario):
    """
    Validates end-to-end closed loop execution for each of the 5 Containerlab scenarios:
    Precondition check -> Fault injection -> Live telemetry -> LangGraph RCA ->
    Human approval -> Safe remediation -> Independent recovery verification.
    """
    result = clab_experiment_runner.execute_single_run(scenario, run_index=1)

    assert result.baseline_healthy is True, f"Baseline check failed for {scenario.scenario_id}"
    assert result.fault_injection_success is True, f"Fault injection failed for {scenario.scenario_id}"
    assert result.fault_observed is True, f"Fault observation failed for {scenario.scenario_id}"
    assert result.incident_created is True, f"Incident creation failed for {scenario.scenario_id}"
    assert result.diagnosis_produced is True, f"Diagnosis not produced for {scenario.scenario_id}"
    assert result.rca_matched is True, f"RCA failed ground-truth match for {scenario.scenario_id}"
    assert result.device_matched is True, f"Device mismatch for {scenario.scenario_id}"
    assert result.protocol_matched is True, f"Protocol mismatch for {scenario.scenario_id}"
    assert result.approval_granted is True, f"Approval gate failed for {scenario.scenario_id}"
    assert result.remediation_executed is True, f"Remediation execution failed for {scenario.scenario_id}"
    assert result.independently_verified is True, f"Verification failed for {scenario.scenario_id}"
    assert result.recovered is True, f"Independent recovery failed for {scenario.scenario_id}"


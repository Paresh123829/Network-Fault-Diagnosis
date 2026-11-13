"""
Containerlab Scenarios Package.
"""

from .models import (
    ExpectedDiagnosis,
    ExpectedSymptom,
    FaultProtocol,
    RecoveryActionDefinition,
    ScenarioDefinition,
    ScenarioPrecondition,
    ScenarioRunResult,
    VerificationCriteria,
)
from .registry import (
    ALL_SCENARIOS,
    SCENARIO_1_BGP,
    SCENARIO_2_OSPF,
    SCENARIO_3_VLAN,
    SCENARIO_4_LINK_FLAP,
    SCENARIO_5_BFD,
    SCENARIO_MAP,
    get_scenario,
    list_scenarios,
)

__all__ = [
    "ExpectedDiagnosis",
    "ExpectedSymptom",
    "FaultProtocol",
    "RecoveryActionDefinition",
    "ScenarioDefinition",
    "ScenarioPrecondition",
    "ScenarioRunResult",
    "VerificationCriteria",
    "ALL_SCENARIOS",
    "SCENARIO_1_BGP",
    "SCENARIO_2_OSPF",
    "SCENARIO_3_VLAN",
    "SCENARIO_4_LINK_FLAP",
    "SCENARIO_5_BFD",
    "SCENARIO_MAP",
    "get_scenario",
    "list_scenarios",
]


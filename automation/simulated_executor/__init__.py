"""
Forwarding package ensuring standard Python module naming for 'simulated-executor'.
"""

import sys
import os

_base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "simulated-executor"))
if _base not in sys.path:
    sys.path.insert(0, _base)

from state_manager import NetworkSimulatorStateManager, simulator_state
from operations import OPERATION_HANDLERS
from verification import PostRemediationVerifier, post_remediation_verifier
from rollback import RemediationRollbackEngine, rollback_engine
from executor import SimulatedRemediationExecutor, simulated_executor

__all__ = [
    "NetworkSimulatorStateManager",
    "simulator_state",
    "OPERATION_HANDLERS",
    "PostRemediationVerifier",
    "post_remediation_verifier",
    "RemediationRollbackEngine",
    "rollback_engine",
    "SimulatedRemediationExecutor",
    "simulated_executor",
]


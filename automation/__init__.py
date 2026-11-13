"""
Automation package initialization.
Ensures both 'automation/simulated-executor' and 'automation.simulated_executor' are directly importable.
"""

import os
import sys

_sim_exec_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "simulated-executor"))
if _sim_exec_dir not in sys.path:
    sys.path.insert(0, _sim_exec_dir)


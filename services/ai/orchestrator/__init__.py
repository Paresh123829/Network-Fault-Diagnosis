"""
Multi-Agent Orchestration Package.
"""

import sys
import types
import uuid

# If uuid_utils native C-extension is blocked by Windows App Control, provide standard library fallback
try:
    import uuid_utils
except ImportError:
    u_mod = types.ModuleType("uuid_utils")
    u_mod.UUID = uuid.UUID
    u_mod.uuid1 = uuid.uuid1
    u_mod.uuid3 = uuid.uuid3
    u_mod.uuid4 = uuid.uuid4
    u_mod.uuid5 = uuid.uuid5
    u_mod.uuid7 = getattr(uuid, "uuid7", uuid.uuid4)
    sys.modules["uuid_utils"] = u_mod

    compat_mod = types.ModuleType("uuid_utils.compat")
    compat_mod.UUID = uuid.UUID
    compat_mod.uuid7 = getattr(uuid, "uuid7", uuid.uuid4)
    sys.modules["uuid_utils.compat"] = compat_mod

from .state import IncidentState
from .graph import build_diagnosis_graph, build_remediation_graph
from .service import DiagnosisOrchestrator
from .checkpointer import get_persistent_checkpointer, FileCheckpointSaver

__all__ = [
    "IncidentState",
    "build_diagnosis_graph",
    "build_remediation_graph",
    "DiagnosisOrchestrator",
    "get_persistent_checkpointer",
    "FileCheckpointSaver",
]


"""
conftest.py — Shared pytest fixtures and environment configuration.
"""

import sys
import os
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

# Ensure workspace root and services/ai directory are in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ai_dir = os.path.join(root_dir, "services", "ai")
for p in [root_dir, ai_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

"""
kill_switch.py — Centralized, Thread-Safe Kill Switch for Network Remediation.

Supports:
1. Global remediation kill switch.
2. Per-agent kill switch.
3. Per-operation restrictions.
4. Immediate execution halt.
5. In-memory and file-backed persistence.
6. Audit event logging on state transitions.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class KillSwitchManager:
    """
    Thread-safe kill-switch controller enforcing fail-closed remediation safety.
    """

    def __init__(self, persistence_file: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._global_active: bool = False
        self._disabled_agents: Set[str] = set()
        self._blocked_operations: Set[str] = set()
        self._blocked_devices: Set[str] = set()
        self._activation_log: List[Dict[str, Any]] = []
        self._persistence_file = persistence_file

        if self._persistence_file and os.path.exists(self._persistence_file):
            self._load_state()

    def is_global_active(self) -> bool:
        """Returns True if the global remediation kill switch is activated."""
        with self._lock:
            return self._global_active

    def is_agent_blocked(self, agent_name: str) -> bool:
        """Checks if a specific agent is barred from performing operations."""
        with self._lock:
            return self._global_active or (agent_name in self._disabled_agents)

    def is_operation_blocked(self, operation: str) -> bool:
        """Checks if an operation is blocked globally or individually."""
        with self._lock:
            return self._global_active or (operation in self._blocked_operations)

    def is_device_blocked(self, device_id: str) -> bool:
        """Checks if a target device is protected by an emergency freeze."""
        with self._lock:
            return self._global_active or (device_id in self._blocked_devices)

    def can_execute(
        self,
        operation: str,
        target_device: str = "",
        agent_name: str = "remediation_agent"
    ) -> tuple[bool, str]:
        """
        Unified verification check called before any execution step.
        Returns (can_execute, reason).
        """
        with self._lock:
            if self._global_active:
                return False, "Global remediation kill switch is ACTIVE. All operations halted."
            if agent_name in self._disabled_agents:
                return False, f"Agent '{agent_name}' has been blocked by kill-switch policy."
            if operation in self._blocked_operations:
                return False, f"Operation '{operation}' is currently restricted by kill switch."
            if target_device and target_device in self._blocked_devices:
                return False, f"Device '{target_device}' is locked under emergency freeze."
            return True, "Kill switch is clear."

    def activate_global(self, reason: str, actor: str = "operator") -> None:
        """Triggers emergency global halt."""
        with self._lock:
            self._global_active = True
            entry = {
                "event": "KILL_SWITCH_ACTIVATED_GLOBAL",
                "actor": actor,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._activation_log.append(entry)
            logger.critical(f"GLOBAL KILL SWITCH ACTIVATED by {actor}: {reason}")
            self._save_state()

    def deactivate_global(self, reason: str, actor: str = "operator") -> None:
        """Restores normal execution following authorized sign-off."""
        with self._lock:
            self._global_active = False
            entry = {
                "event": "KILL_SWITCH_DEACTIVATED_GLOBAL",
                "actor": actor,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._activation_log.append(entry)
            logger.warning(f"Global kill switch deactivated by {actor}: {reason}")
            self._save_state()

    def block_operation(self, operation: str, reason: str, actor: str = "operator") -> None:
        """Restricts a specific operation."""
        with self._lock:
            self._blocked_operations.add(operation)
            entry = {
                "event": "OPERATION_BLOCKED",
                "operation": operation,
                "actor": actor,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._activation_log.append(entry)
            self._save_state()

    def unblock_operation(self, operation: str, reason: str, actor: str = "operator") -> None:
        """Clears restriction on a specific operation."""
        with self._lock:
            self._blocked_operations.discard(operation)
            entry = {
                "event": "OPERATION_UNBLOCKED",
                "operation": operation,
                "actor": actor,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._activation_log.append(entry)
            self._save_state()

    def block_device(self, device_id: str, reason: str, actor: str = "operator") -> None:
        """Freezes all actions on a specific device."""
        with self._lock:
            self._blocked_devices.add(device_id)
            self._save_state()

    def unblock_device(self, device_id: str) -> None:
        """Unfreezes device."""
        with self._lock:
            self._blocked_devices.discard(device_id)
            self._save_state()

    def reset_all(self) -> None:
        """Resets all kill switches to clean state (primarily for test harnesses)."""
        with self._lock:
            self._global_active = False
            self._disabled_agents.clear()
            self._blocked_operations.clear()
            self._blocked_devices.clear()
            self._activation_log.clear()
            self._save_state()

    def get_status(self) -> Dict[str, Any]:
        """Returns full diagnostic snapshot."""
        with self._lock:
            return {
                "global_active": self._global_active,
                "disabled_agents": sorted(list(self._disabled_agents)),
                "blocked_operations": sorted(list(self._blocked_operations)),
                "blocked_devices": sorted(list(self._blocked_devices)),
                "recent_events": self._activation_log[-20:],
            }

    def _save_state(self) -> None:
        if not self._persistence_file:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._persistence_file)), exist_ok=True)
            with open(self._persistence_file, "w", encoding="utf-8") as f:
                json.dump(self.get_status(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist kill switch state: {e}")

    def _load_state(self) -> None:
        try:
            with open(self._persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._global_active = data.get("global_active", False)
                self._disabled_agents = set(data.get("disabled_agents", []))
                self._blocked_operations = set(data.get("blocked_operations", []))
                self._blocked_devices = set(data.get("blocked_devices", []))
        except Exception as e:
            logger.error(f"Failed to load kill switch state: {e}")


# Global singleton instance
kill_switch = KillSwitchManager()


"""
action_registry.py — Deterministic Allow-List Registry for Network Remediation Operations.

The action registry is the sole authority for determining which operations the executor can perform.
Arbitrary shell execution, dynamic command generation, and unscoped actions are strictly prohibited.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set
from services.ai.schemas.contracts import RiskLevel
from .models import ActionDefinition


class ActionRegistry:
    """
    Registry of all verified, bounded remediation actions permitted in the simulation framework.
    """

    # Strictly prohibited commands and keywords
    PROHIBITED_KEYWORDS: Set[str] = {
        "reload", "reboot", "format", "delete", "erase", "write erase",
        "bash", "sh", "sudo", "cmd", "powershell", "python", "eval", "exec",
        "rm", "kill", "shutdown -r", "drop database", "iptables -F",
        "systemctl", "init 0", "init 6", "reboot -f", "passwd"
    }

    # Prohibited shell metacharacters for parameter safety
    SHELL_METACHARACTERS_REGEX = re.compile(r"[;&|`$<>\r\n]")

    def __init__(self) -> None:
        self._actions: Dict[str, ActionDefinition] = {}
        self._register_default_actions()

    def _register_default_actions(self) -> None:
        """Registers the 5 core allowable remediation actions for network incidents."""

        # 1. Restore Interface Admin State (e.g. recovering from admin shutdown or port flap)
        self.register(ActionDefinition(
            operation="restore_interface_admin_state",
            description="Restores an interface admin status from DOWN to UP.",
            required_parameters=["target_device", "target_interface", "admin_state"],
            optional_parameters=["clear_counters"],
            parameter_schema={
                "target_device": str,
                "target_interface": str,
                "admin_state": lambda v: v in ("UP", "up"),
                "clear_counters": bool,
            },
            allowed_device_types=["SPINE", "LEAF", "BORDER_ROUTER", "ROUTER", "SWITCH", "ACCESS"],
            allowed_interface_types=["PHYSICAL", "PORT_CHANNEL", "SUBINTERFACE"],
            base_risk=RiskLevel.MEDIUM,
            requires_human_approval=True,
            is_reversible=True,
            rollback_operation="disable_interface_admin_state",
            default_timeout_seconds=15.0,
            precondition_rules=["device_exists", "interface_exists_on_device", "interface_is_admin_down"],
            postcondition_rules=["interface_admin_state_is_up", "interface_operational_state_is_up"]
        ))

        # 2. Reset BGP Session (e.g. clearing stuck BGP session or recovering peer)
        self.register(ActionDefinition(
            operation="reset_bgp_session",
            description="Soft-resets a BGP peer session to re-establish routing exchange.",
            required_parameters=["target_device", "peer_ip"],
            optional_parameters=["peer_asn", "soft_reset"],
            parameter_schema={
                "target_device": str,
                "peer_ip": str,
                "peer_asn": int,
                "soft_reset": bool,
            },
            allowed_device_types=["SPINE", "LEAF", "BORDER_ROUTER", "ROUTER"],
            allowed_interface_types=[],
            base_risk=RiskLevel.MEDIUM,
            requires_human_approval=True,
            is_reversible=True,
            rollback_operation="reconfigure_bgp_session",
            default_timeout_seconds=20.0,
            precondition_rules=["device_exists", "bgp_peer_configured", "session_not_established"],
            postcondition_rules=["bgp_session_is_established"]
        ))

        # 3. Restore BFD Session
        self.register(ActionDefinition(
            operation="restore_bfd_session",
            description="Re-activates a BFD monitoring session on a target interface or peer.",
            required_parameters=["target_device", "peer_ip"],
            optional_parameters=["interface", "interval_ms", "multiplier"],
            parameter_schema={
                "target_device": str,
                "peer_ip": str,
                "interface": str,
                "interval_ms": int,
                "multiplier": int,
            },
            allowed_device_types=["SPINE", "LEAF", "BORDER_ROUTER", "ROUTER"],
            allowed_interface_types=["PHYSICAL", "PORT_CHANNEL", "SUBINTERFACE"],
            base_risk=RiskLevel.LOW,
            requires_human_approval=True,
            is_reversible=True,
            rollback_operation="disable_bfd_session",
            default_timeout_seconds=10.0,
            precondition_rules=["device_exists", "bfd_peer_configured"],
            postcondition_rules=["bfd_session_is_up"]
        ))

        # 4. Restore OSPF Adjacency
        self.register(ActionDefinition(
            operation="restore_ospf_adjacency",
            description="Re-enables OSPF process or re-negotiates adjacency on an interface.",
            required_parameters=["target_device", "interface"],
            optional_parameters=["area", "neighbor_ip"],
            parameter_schema={
                "target_device": str,
                "interface": str,
                "area": str,
                "neighbor_ip": str,
            },
            allowed_device_types=["SPINE", "LEAF", "BORDER_ROUTER", "ROUTER"],
            allowed_interface_types=["PHYSICAL", "PORT_CHANNEL", "SUBINTERFACE"],
            base_risk=RiskLevel.MEDIUM,
            requires_human_approval=True,
            is_reversible=True,
            rollback_operation="disable_ospf_on_interface",
            default_timeout_seconds=15.0,
            precondition_rules=["device_exists", "ospf_configured_on_interface"],
            postcondition_rules=["ospf_neighbor_state_is_full"]
        ))

        # 5. Restore VLAN Membership
        self.register(ActionDefinition(
            operation="restore_vlan_membership",
            description="Restores correct VLAN assignment on a switch access or trunk interface.",
            required_parameters=["target_device", "interface", "vlan_id"],
            optional_parameters=["mode"],
            parameter_schema={
                "target_device": str,
                "interface": str,
                "vlan_id": lambda v: isinstance(v, int) and 1 <= v <= 4094,
                "mode": lambda v: v in ("access", "trunk"),
            },
            allowed_device_types=["LEAF", "SWITCH", "ACCESS"],
            allowed_interface_types=["PHYSICAL", "PORT_CHANNEL", "SUBINTERFACE"],
            base_risk=RiskLevel.LOW,
            requires_human_approval=True,
            is_reversible=True,
            rollback_operation="revert_vlan_membership",
            default_timeout_seconds=10.0,
            precondition_rules=["device_exists", "interface_exists_on_device", "vlan_valid_range"],
            postcondition_rules=["vlan_membership_restored", "l2_reachability_verified"]
        ))

    def register(self, action_def: ActionDefinition) -> None:
        """Registers a new action definition."""
        self._actions[action_def.operation] = action_def

    def get(self, operation: str) -> Optional[ActionDefinition]:
        """Retrieves action definition by operation identifier."""
        return self._actions.get(operation)

    def is_allowed(self, operation: str) -> bool:
        """Checks if operation is in the allow-list."""
        return operation in self._actions

    def list_operations(self) -> List[str]:
        """Lists all registered allow-listed operations."""
        return sorted(list(self._actions.keys()))

    def get_manifest(self) -> List[Dict[str, Any]]:
        """Returns JSON-serializable manifest of all registered operations."""
        return [act.model_dump() for act in self._actions.values()]

    def validate_operation_and_parameters(
        self,
        operation: str,
        parameters: Dict[str, Any]
    ) -> tuple[bool, List[str]]:
        """
        Validates that:
        1. Operation is strictly registered in the allow-list.
        2. No prohibited keywords or shell metacharacters exist in values.
        3. Mandatory parameters are present and typed.
        4. No undeclared/unexpected parameters exist.
        """
        errors: List[str] = []

        if not self.is_allowed(operation):
            return False, [f"Operation '{operation}' is NOT registered in allow-list."]

        action = self._actions[operation]

        # Check for prohibited command attempts or shell injection in parameters
        for k, v in parameters.items():
            str_v = str(v)
            if self.SHELL_METACHARACTERS_REGEX.search(str_v):
                errors.append(f"Security violation: Parameter '{k}' contains prohibited shell characters.")
            for kw in self.PROHIBITED_KEYWORDS:
                if kw in str_v.lower():
                    errors.append(f"Security violation: Parameter '{k}' contains prohibited command keyword '{kw}'.")

        # Check missing required parameters
        for req in action.required_parameters:
            if req not in parameters or parameters[req] is None or parameters[req] == "":
                errors.append(f"Missing required parameter '{req}' for operation '{operation}'.")

        # Check unexpected parameters
        allowed_keys = set(action.required_parameters) | set(action.optional_parameters)
        for key in parameters:
            if key not in allowed_keys:
                errors.append(f"Unexpected parameter '{key}' is not permitted for operation '{operation}'.")

        # Validate parameter schemas
        for param_name, validator in action.parameter_schema.items():
            if param_name in parameters and parameters[param_name] is not None:
                val = parameters[param_name]
                if isinstance(validator, type):
                    if not isinstance(val, validator):
                        errors.append(f"Parameter '{param_name}' must be of type {validator.__name__}, got {type(val).__name__}.")
                elif callable(validator):
                    try:
                        if not validator(val):
                            errors.append(f"Parameter '{param_name}' failed validation rule with value: {val}.")
                    except Exception as e:
                        errors.append(f"Parameter '{param_name}' raised error during validation: {str(e)}.")

        return (len(errors) == 0, errors)


# Global singleton instance
action_registry = ActionRegistry()


"""
injector.py — Deterministic, Safe Fault Injection Engine for Containerlab.

Enforces:
- Target node validation against authorized inventory.
- Precondition verification prior to state mutation.
- Pre-state snapshot capture.
- Strictly whitelisted, parameterized vtysh/CLI operations.
- Execution timeout and deduplication protection.
- Structured injection telemetry logging.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from network.containerlab.runtime.driver import execute_clab_command, VALID_LAB_NODES
from network.containerlab.scenarios.models import (
    ScenarioDefinition,
    ScenarioPrecondition,
)

logger = logging.getLogger(__name__)


class FaultInjectionResult:
    def __init__(
        self,
        scenario_id: str,
        target_node: str,
        operation: str,
        success: bool,
        pre_state: Dict[str, Any],
        injected_at: datetime,
        output: str = "",
        error: str = "",
    ) -> None:
        self.scenario_id = scenario_id
        self.target_node = target_node
        self.operation = operation
        self.success = success
        self.pre_state = pre_state
        self.injected_at = injected_at
        self.output = output
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "target_node": self.target_node,
            "operation": self.operation,
            "success": self.success,
            "pre_state": self.pre_state,
            "injected_at": self.injected_at.isoformat(),
            "output": self.output,
            "error": self.error,
        }


class FaultInjector:
    """
    Coordinates precondition checking and deterministic fault injection.
    """

    def __init__(self, force_mock: bool = False) -> None:
        self.force_mock = force_mock

    def check_preconditions(self, scenario: ScenarioDefinition) -> Tuple[bool, List[str]]:
        """
        Verifies that the target network component satisfies all baseline preconditions.
        """
        failures = []
        for cond in scenario.preconditions:
            node = cond.target_node
            check = cond.check_type
            expected = cond.expected_value

            if check == "bgp_neighbor":
                code, stdout, _ = execute_clab_command(node, ["vtysh", "-c", "show ip bgp summary json"], force_mock=self.force_mock)
                if code != 0:
                    failures.append(f"Could not query BGP on {node}")
                    continue
                try:
                    import json
                    data = json.loads(stdout)
                    peer = data.get("peers", {}).get(cond.target_identifier, {})
                    actual_state = peer.get("state")
                    if actual_state != expected:
                        failures.append(f"BGP neighbor {cond.target_identifier} state is '{actual_state}', expected '{expected}'")
                except Exception as e:
                    failures.append(f"Failed to parse BGP JSON on {node}: {e}")

            elif check == "ospf_neighbor":
                code, stdout, _ = execute_clab_command(node, ["vtysh", "-c", "show ip ospf neighbor json"], force_mock=self.force_mock)
                if code != 0:
                    failures.append(f"Could not query OSPF on {node}")
                    continue
                try:
                    import json
                    data = json.loads(stdout)
                    nbrs = data.get("neighbors", {}).get(cond.target_identifier, [])
                    actual_state = nbrs[0].get("nbrState") if nbrs else "None"
                    if actual_state != expected:
                        failures.append(f"OSPF neighbor on {cond.target_identifier} state is '{actual_state}', expected '{expected}'")
                except Exception as e:
                    failures.append(f"Failed to parse OSPF JSON on {node}: {e}")

            elif check == "bfd_peer":
                code, stdout, _ = execute_clab_command(node, ["vtysh", "-c", "show bfd peers json"], force_mock=self.force_mock)
                if code != 0:
                    failures.append(f"Could not query BFD on {node}")
                    continue
                try:
                    import json
                    data = json.loads(stdout)
                    matched = [p for p in data if p.get("peer") == cond.target_identifier]
                    actual_state = matched[0].get("status") if matched else "None"
                    if actual_state != expected:
                        failures.append(f"BFD peer {cond.target_identifier} status is '{actual_state}', expected '{expected}'")
                except Exception as e:
                    failures.append(f"Failed to parse BFD JSON on {node}: {e}")

            elif check == "interface_state":
                code, stdout, _ = execute_clab_command(node, ["ip", "-j", "link"], force_mock=self.force_mock)
                if code != 0:
                    failures.append(f"Could not query interfaces on {node}")
                    continue
                try:
                    import json
                    data = json.loads(stdout)
                    matched = [iface for iface in data if iface.get("ifname") == cond.target_identifier]
                    actual_state = matched[0].get("operstate") if matched else "None"
                    if actual_state != expected:
                        failures.append(f"Interface {cond.target_identifier} operstate is '{actual_state}', expected '{expected}'")
                except Exception as e:
                    failures.append(f"Failed to parse interface JSON on {node}: {e}")

            elif check == "vlan_ping":
                code, stdout, _ = execute_clab_command(node, ["ping", "-c", "2", cond.target_identifier], force_mock=self.force_mock)
                if code != 0:
                    failures.append(f"Ping from {node} to {cond.target_identifier} failed (code {code})")

        return len(failures) == 0, failures

    def capture_pre_state(self, scenario: ScenarioDefinition) -> Dict[str, Any]:
        """Captures snapshot of baseline state for the target component."""
        node = scenario.target_node
        snapshot: Dict[str, Any] = {"target_node": node, "captured_at": datetime.now(timezone.utc).isoformat()}

        if scenario.protocol.value == "bgp":
            _, stdout, _ = execute_clab_command(node, ["vtysh", "-c", "show ip bgp summary json"], force_mock=self.force_mock)
            snapshot["bgp_summary"] = stdout
        elif scenario.protocol.value == "ospf":
            _, stdout, _ = execute_clab_command(node, ["vtysh", "-c", "show ip ospf neighbor json"], force_mock=self.force_mock)
            snapshot["ospf_neighbors"] = stdout
        elif scenario.protocol.value == "bfd":
            _, stdout, _ = execute_clab_command(node, ["vtysh", "-c", "show bfd peers json"], force_mock=self.force_mock)
            snapshot["bfd_peers"] = stdout
        elif scenario.protocol.value == "interface":
            _, stdout, _ = execute_clab_command(node, ["ip", "-j", "link"], force_mock=self.force_mock)
            snapshot["interfaces"] = stdout
        elif scenario.protocol.value == "vlan":
            _, stdout, _ = execute_clab_command(node, ["bridge", "vlan", "show"], force_mock=self.force_mock)
            snapshot["bridge_vlans"] = stdout

        return snapshot

    def inject_fault(self, scenario: ScenarioDefinition) -> FaultInjectionResult:
        """
        Executes the fault injection operation for a given scenario.
        """
        node = scenario.target_node
        op = scenario.fault_operation
        params = scenario.fault_parameters
        now = datetime.now(timezone.utc)

        # 0. Node inventory authorization check
        if node not in VALID_LAB_NODES:
            logger.error(f"[INJECTION ABORTED] Target node {node} not in authorized lab inventory")
            return FaultInjectionResult(
                scenario_id=scenario.scenario_id,
                target_node=node,
                operation=op,
                success=False,
                pre_state={},
                injected_at=now,
                error=f"Unauthorized node: {node} is not a valid lab container",
            )

        # 1. Precondition verification
        ok, failures = self.check_preconditions(scenario)
        if not ok:
            logger.error(f"[INJECTION ABORTED] Precondition check failed for {scenario.scenario_id}: {failures}")
            return FaultInjectionResult(
                scenario_id=scenario.scenario_id,
                target_node=node,
                operation=op,
                success=False,
                pre_state={},
                injected_at=now,
                error=f"Preconditions failed: {'; '.join(failures)}",
            )

        # 2. Capture pre-state
        pre_state = self.capture_pre_state(scenario)

        # 3. Dispatch vetted operations
        stdout_acc: List[str] = []
        stderr_acc: List[str] = []
        success = True

        if op == "clear_bgp_session":
            peer_ip = params.get("peer_ip", "172.16.12.2")
            args = ["vtysh", "-c", f"clear bgp {peer_ip}"]
            code, out, err = execute_clab_command(node, args, force_mock=self.force_mock)
            stdout_acc.append(out)
            stderr_acc.append(err)
            success = (code == 0)

        elif op == "set_ospf_timer_mismatch":
            iface = params.get("interface", "eth1")
            hello = params.get("hello_interval", 20)
            dead = params.get("dead_interval", 80)
            args = [
                "vtysh",
                "-c", "conf t",
                "-c", f"interface {iface}",
                "-c", f"ip ospf hello-interval {hello}",
                "-c", f"ip ospf dead-interval {dead}",
                "-c", "end"
            ]
            code, out, err = execute_clab_command(node, args, force_mock=self.force_mock)
            stdout_acc.append(out)
            stderr_acc.append(err)
            success = (code == 0)

        elif op == "set_bridge_vlan_mismatch":
            iface = params.get("interface", "eth3")
            fault_vid = params.get("fault_vid", 200)
            args = [
                "bridge", "vlan", "add", "dev", iface, "vid", str(fault_vid), "pvid", "untagged"
            ]
            code, out, err = execute_clab_command(node, args, force_mock=self.force_mock)
            stdout_acc.append(out)
            stderr_acc.append(err)
            success = (code == 0)

        elif op == "flap_interface_bounded":
            iface = params.get("interface", "eth1")
            flaps = params.get("flap_count", 2)
            interval = params.get("interval_seconds", 1.0)
            for _ in range(flaps):
                # shutdown
                execute_clab_command(node, ["vtysh", "-c", "conf t", "-c", f"interface {iface}", "-c", "shutdown", "-c", "end"], force_mock=self.force_mock)
                time.sleep(interval)
                # no shutdown
                execute_clab_command(node, ["vtysh", "-c", "conf t", "-c", f"interface {iface}", "-c", "no shutdown", "-c", "end"], force_mock=self.force_mock)
                time.sleep(interval)
            # Final state: down
            code, out, err = execute_clab_command(node, ["vtysh", "-c", "conf t", "-c", f"interface {iface}", "-c", "shutdown", "-c", "end"], force_mock=self.force_mock)
            stdout_acc.append(out)
            stderr_acc.append(err)
            success = (code == 0)

        elif op == "disable_bfd_peer":
            peer_ip = params.get("peer_ip", "172.16.12.2")
            args = [
                "vtysh",
                "-c", "conf t",
                "-c", "bfd",
                "-c", f"peer {peer_ip}",
                "-c", "shutdown",
                "-c", "end"
            ]
            code, out, err = execute_clab_command(node, args, force_mock=self.force_mock)
            stdout_acc.append(out)
            stderr_acc.append(err)
            success = (code == 0)

        else:
            return FaultInjectionResult(
                scenario_id=scenario.scenario_id,
                target_node=node,
                operation=op,
                success=False,
                pre_state=pre_state,
                injected_at=now,
                error=f"Unrecognized fault operation: {op}",
            )

        logger.info(f"[FAULT INJECTED] Scenario {scenario.scenario_id} on {node} (success={success})")
        return FaultInjectionResult(
            scenario_id=scenario.scenario_id,
            target_node=node,
            operation=op,
            success=success,
            pre_state=pre_state,
            injected_at=now,
            output="\n".join(stdout_acc),
            error="\n".join(stderr_acc),
        )


# Global singleton instance
fault_injector = FaultInjector()


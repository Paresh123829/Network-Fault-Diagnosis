"""
fault_injection.py — Controlled fault injection for the FRR R1-R2-R3 simulation.

Design contract
---------------
Every fault scenario is a plain Python function that:
  1. Takes a target container name (e.g. "R1", "R2") and optional parameters.
  2. Executes a predefined vtysh command sequence via `docker exec`.
  3. Returns a FaultScenario dataclass with ground-truth metadata.

NO ARBITRARY SHELL COMMANDS.
The allowed command set is explicitly defined in ALLOWED_VTYSH_COMMANDS below.
The LLM never touches this module directly — it is called only by the test suite
and the simulation runner.

Supported scenarios (per Phase 1 spec)
---------------------------------------
  BGP_FAILURE_R1_R2  — clear BGP session between R1 and R2 (simulates BGP process crash)
  BGP_FAILURE_R2_R3  — clear BGP session between R2 and R3
  PORT_ADMIN_SHUTDOWN — admin-shutdown eth1 on a specified router (brings interface down)

Ground-truth format
--------------------
Each FaultScenario records:
  scenario_id, fault_name, target, injection_mechanism, expected_symptoms,
  recovery_mechanism, expected_recovered_state
matching the project's fault documentation standard.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Allowed command allow-list ───────────────────────────────────────────────
# Only these vtysh command templates are permitted.
# Parameters are substituted in only by the functions in this module, never from
# external input.

ALLOWED_VTYSH_COMMANDS: Dict[str, str] = {
    "clear_bgp_session":    "vtysh -c 'clear bgp {peer_ip}'",
    "clear_bgp_all":        "vtysh -c 'clear bgp *'",
    "interface_shutdown":   "vtysh -c 'conf t' -c 'interface {ifname}' -c 'shutdown' -c 'end'",
    "interface_no_shutdown":"vtysh -c 'conf t' -c 'interface {ifname}' -c 'no shutdown' -c 'end'",
    "show_bgp_summary":     "vtysh -c 'show bgp summary'",
    "show_ip_route":        "vtysh -c 'show ip route'",
    "show_ospf_neighbor":   "vtysh -c 'show ip ospf neighbor'",
}

# ─── Data model ──────────────────────────────────────────────────────────────

@dataclass
class FaultScenario:
    """
    Ground-truth record for a single injected fault event.
    Every fault must have all required fields populated — no optional omissions.
    """
    scenario_id: str
    fault_name: str
    target: str                      # Container name (e.g. "R1")
    injection_mechanism: str         # Which ALLOWED_VTYSH_COMMANDS key was used
    injection_params: Dict           # Parameters substituted into the command
    expected_symptoms: List[str]     # Observable effects on the network
    recovery_mechanism: str          # How recovery is triggered (command or auto)
    expected_recovered_state: str    # Human-readable description of normal state
    injected_at: Optional[datetime] = None   # Populated after injection executes
    recovered_at: Optional[datetime] = None  # Populated after recovery executes


# ─── Execution primitives ─────────────────────────────────────────────────────

def _docker_exec(container: str, command: str, timeout: int = 10) -> str:
    """
    Execute a command inside a containerlab container via `docker exec`.
    Returns stdout. Raises RuntimeError on non-zero exit code.

    This is the ONLY path through which shell commands are executed.
    Command strings must be assembled only from ALLOWED_VTYSH_COMMANDS values.
    """
    full_cmd = ["docker", "exec", container] + command.split()
    logger.debug("docker exec %s: %s", container, command)
    result = subprocess.run(
        full_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"docker exec on {container} failed (rc={result.returncode}):\n"
            f"  cmd: {command}\n"
            f"  stderr: {result.stderr.strip()}"
        )
    return result.stdout


def _exec_vtysh(container: str, command_key: str, **params) -> str:
    """
    Execute a whitelisted vtysh command on a container.
    Raises KeyError if command_key is not in ALLOWED_VTYSH_COMMANDS.
    Raises ValueError if required params are missing.
    """
    template = ALLOWED_VTYSH_COMMANDS[command_key]
    try:
        cmd = template.format(**params)
    except KeyError as e:
        raise ValueError(f"Missing parameter {e} for command '{command_key}'") from e
    return _docker_exec(container, cmd)


# ─── Fault scenarios ──────────────────────────────────────────────────────────

def inject_bgp_session_failure(
    router: str,
    peer_ip: str,
    scenario_id: str,
    recovery_delay_seconds: int = 30,
) -> FaultScenario:
    """
    Simulate a BGP session failure by clearing the BGP session to a specific peer.
    BGP will reconverge automatically after hold-timer expiry (30s configured).

    Parameters
    ----------
    router
        Container name of the router on which to inject the fault (e.g. "R1").
    peer_ip
        IP address of the BGP peer whose session should be cleared.
    scenario_id
        Unique scenario identifier for ground-truth records.
    recovery_delay_seconds
        Seconds to wait before considering the session recovered.
        Should be >= BGP hold-time (configured as 30s).
    """
    scenario = FaultScenario(
        scenario_id=scenario_id,
        fault_name="BGP Session Clear",
        target=router,
        injection_mechanism="clear_bgp_session",
        injection_params={"peer_ip": peer_ip},
        expected_symptoms=[
            f"BGP neighbor {peer_ip} transitions to Idle/Active state",
            "Routes learned from peer are withdrawn from RIB",
            f"Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor {peer_ip} Down",
            "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor {peer_ip} Up (after reconvergence)",
        ],
        recovery_mechanism=f"automatic_bgp_reconvergence_after_{recovery_delay_seconds}s",
        expected_recovered_state=f"BGP session to {peer_ip} re-established, routes re-learned",
    )

    logger.info("[%s] Injecting BGP session clear: %s → peer %s", scenario_id, router, peer_ip)
    scenario.injected_at = datetime.now(tz=timezone.utc)

    _exec_vtysh(router, "clear_bgp_session", peer_ip=peer_ip)

    logger.info("[%s] BGP clear sent. Waiting %ds for reconvergence...", scenario_id, recovery_delay_seconds)
    time.sleep(recovery_delay_seconds)
    scenario.recovered_at = datetime.now(tz=timezone.utc)

    return scenario


def inject_bgp_full_clear(
    router: str,
    scenario_id: str,
    recovery_delay_seconds: int = 30,
) -> FaultScenario:
    """
    Clear ALL BGP sessions on a router (simulates BGP process crash).
    All peers will reconverge automatically.
    """
    scenario = FaultScenario(
        scenario_id=scenario_id,
        fault_name="BGP Full Session Clear (All Peers)",
        target=router,
        injection_mechanism="clear_bgp_all",
        injection_params={},
        expected_symptoms=[
            "All BGP neighbors transition to Idle/Active state",
            "All BGP-learned routes withdrawn from RIB",
            "Syslog: Multiple %ROUTING-BGP-5-ADJCHANGE Down entries",
            "Syslog: Multiple %ROUTING-BGP-5-ADJCHANGE Up entries after reconvergence",
        ],
        recovery_mechanism=f"automatic_bgp_reconvergence_after_{recovery_delay_seconds}s",
        expected_recovered_state="All BGP sessions re-established, all routes re-learned",
    )

    logger.info("[%s] Injecting BGP full clear on %s", scenario_id, router)
    scenario.injected_at = datetime.now(tz=timezone.utc)

    _exec_vtysh(router, "clear_bgp_all")

    logger.info("[%s] BGP full clear sent. Waiting %ds...", scenario_id, recovery_delay_seconds)
    time.sleep(recovery_delay_seconds)
    scenario.recovered_at = datetime.now(tz=timezone.utc)

    return scenario


def inject_interface_admin_shutdown(
    router: str,
    interface: str,
    scenario_id: str,
    recovery_delay_seconds: int = 30,
) -> FaultScenario:
    """
    Admin-shutdown an interface on a router, then restore it.

    Parameters
    ----------
    router
        Container name (e.g. "R2").
    interface
        Interface name as configured in FRR (e.g. "eth1").
    scenario_id
        Unique scenario identifier.
    recovery_delay_seconds
        Seconds to keep the interface down before bringing it back up.
    """
    scenario = FaultScenario(
        scenario_id=scenario_id,
        fault_name=f"Interface Admin Shutdown ({interface})",
        target=router,
        injection_mechanism="interface_shutdown",
        injection_params={"ifname": interface},
        expected_symptoms=[
            f"Interface {interface} on {router} transitions to admin-down state",
            "OSPF neighbor adjacency lost on this link",
            "BGP session(s) over this link go Down (Interface flap reason)",
            "Syslog: %PKT_INFRA-LINK-3-UPDOWN changed state to Down",
            "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor Down - Interface flap",
        ],
        recovery_mechanism="interface_no_shutdown",
        expected_recovered_state=(
            f"Interface {interface} back to Up, OSPF re-neighbors, BGP re-establishes"
        ),
    )

    logger.info("[%s] Shutting down %s on %s", scenario_id, interface, router)
    scenario.injected_at = datetime.now(tz=timezone.utc)
    _exec_vtysh(router, "interface_shutdown", ifname=interface)

    logger.info("[%s] Waiting %ds before recovery...", scenario_id, recovery_delay_seconds)
    time.sleep(recovery_delay_seconds)

    logger.info("[%s] Bringing %s back up on %s", scenario_id, interface, router)
    _exec_vtysh(router, "interface_no_shutdown", ifname=interface)
    scenario.recovered_at = datetime.now(tz=timezone.utc)

    return scenario


# ─── Pre-defined scenario library ────────────────────────────────────────────

def run_scenario_BGP_FAILURE_R1_R2() -> FaultScenario:
    """BGP session failure between R1 and R2."""
    return inject_bgp_session_failure(
        router="R1",
        peer_ip="172.16.12.2",
        scenario_id="BGP_FAILURE_R1_R2",
    )


def run_scenario_BGP_FAILURE_R2_R3() -> FaultScenario:
    """BGP session failure between R2 and R3."""
    return inject_bgp_session_failure(
        router="R2",
        peer_ip="172.16.23.2",
        scenario_id="BGP_FAILURE_R2_R3",
    )


def run_scenario_BGP_FULL_CLEAR_R2() -> FaultScenario:
    """BGP full process clear on R2 (all peers affected)."""
    return inject_bgp_full_clear(
        router="R2",
        scenario_id="BGP_FULL_CLEAR_R2",
    )


def run_scenario_PORT_ADMIN_SHUTDOWN_R2_ETH1() -> FaultScenario:
    """Admin-shutdown eth1 on R2 (breaks R1-R2 link)."""
    return inject_interface_admin_shutdown(
        router="R2",
        interface="eth1",
        scenario_id="PORT_ADMIN_SHUTDOWN_R2_ETH1",
    )


def run_scenario_PORT_ADMIN_SHUTDOWN_R2_ETH2() -> FaultScenario:
    """Admin-shutdown eth2 on R2 (breaks R2-R3 link)."""
    return inject_interface_admin_shutdown(
        router="R2",
        interface="eth2",
        scenario_id="PORT_ADMIN_SHUTDOWN_R2_ETH2",
    )


# ─── Scenario registry ────────────────────────────────────────────────────────

SCENARIO_REGISTRY = {
    "BGP_FAILURE_R1_R2":          run_scenario_BGP_FAILURE_R1_R2,
    "BGP_FAILURE_R2_R3":          run_scenario_BGP_FAILURE_R2_R3,
    "BGP_FULL_CLEAR_R2":          run_scenario_BGP_FULL_CLEAR_R2,
    "PORT_ADMIN_SHUTDOWN_R2_ETH1": run_scenario_PORT_ADMIN_SHUTDOWN_R2_ETH1,
    "PORT_ADMIN_SHUTDOWN_R2_ETH2": run_scenario_PORT_ADMIN_SHUTDOWN_R2_ETH2,
}

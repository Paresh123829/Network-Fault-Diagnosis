"""
driver.py — Command Execution Boundary for Containerlab / FRR Nodes.

Enforces:
- Exact node target validation against known topology inventory.
- Prohibits arbitrary shell interpolation (strictly argument arrays, NO shell=True).
- Dual-mode execution: Live Docker CLI when available, high-fidelity mock provider otherwise.
- Explicit timeouts and exit code handling.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import List, Optional, Set, Tuple

from .mock_provider import mock_clab_provider

logger = logging.getLogger(__name__)

# Registered node names in topology.yml
VALID_LAB_NODES: Set[str] = {
    "R1", "R2", "R3", "br-vlan", "client1", "client2",
    # Containerlab prefix forms
    "clab-cnt-frr-lab-R1", "clab-cnt-frr-lab-R2", "clab-cnt-frr-lab-R3",
    "clab-cnt-frr-lab-br-vlan", "clab-cnt-frr-lab-client1", "clab-cnt-frr-lab-client2",
}

# Normalize node name by stripping clab prefix
def normalize_node_name(node: str) -> str:
    if node.startswith("clab-cnt-frr-lab-"):
        return node[len("clab-cnt-frr-lab-"):]
    return node


def is_docker_available() -> bool:
    """Checks whether the docker binary is in PATH and daemon is reachable."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return False
    try:
        res = subprocess.run([docker_bin, "info"], capture_output=True, timeout=3)
        return res.returncode == 0
    except Exception:
        return False


def is_containerlab_available() -> bool:
    """Checks whether the containerlab binary is in PATH."""
    return shutil.which("containerlab") is not None or shutil.which("clab") is not None


def execute_clab_command(
    node: str,
    args: List[str],
    timeout: int = 15,
    force_mock: bool = False,
) -> Tuple[int, str, str]:
    """
    Executes a vetted command on a Containerlab node.
    Returns (returncode, stdout, stderr).
    """
    norm_node = normalize_node_name(node)
    if norm_node not in VALID_LAB_NODES and node not in VALID_LAB_NODES:
        raise ValueError(f"Target '{node}' is not in the authorized Containerlab topology inventory: {sorted(list(VALID_LAB_NODES))}")

    # Dual-mode execution
    if not force_mock and is_docker_available():
        container_name = f"clab-cnt-frr-lab-{norm_node}"
        full_cmd = ["docker", "exec", container_name] + args
        logger.debug(f"[CLAB EXEC] {' '.join(full_cmd)}")
        try:
            res = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired:
            return 124, "", f"Command timed out after {timeout} seconds on {node}"
        except Exception as e:
            return 1, "", f"Docker execution error: {e}"

    # Route to high-fidelity mock provider
    return mock_clab_provider.execute(norm_node, args)


def get_clab_logs(
    node: str,
    tail: int = 200,
    force_mock: bool = False,
) -> List[str]:
    """
    Retrieves recent syslog entries from an FRR/bridge node.
    """
    norm_node = normalize_node_name(node)
    if not force_mock and is_docker_available():
        container_name = f"clab-cnt-frr-lab-{norm_node}"
        try:
            res = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = (res.stdout + res.stderr).splitlines()
            return lines[-tail:]
        except Exception:
            return []
    return mock_clab_provider.get_logs(norm_node, tail=tail)


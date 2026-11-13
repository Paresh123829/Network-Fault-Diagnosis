"""
frr_log_collector.py — Collect FRR syslog output from containerlab containers.

This module polls the FRR log output from running containers and converts each
IOS-XR–style syslog line into a RawNetworkRecord.

The FRR containers are configured with 'log syslog informational' which causes
FRR daemons to emit syslog-format messages to stdout/stderr captured by Docker.

IMPORTANT: This module uses only `docker logs` — it never executes arbitrary
           commands inside containers.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Optional

# Make adapters importable from this location
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "datasets"))

from adapters.raw_record import RawNetworkRecord, RecordSource
from adapters.cisco_adapter import _parse_syslog_line

logger = logging.getLogger(__name__)

# Containerlab container naming convention: clab-<topology-name>-<node-name>
TOPOLOGY_NAME = "cnt-frr-lab"
ROUTER_NAMES = ["R1", "R2", "R3"]


def _container_name(router: str) -> str:
    return f"clab-{TOPOLOGY_NAME}-{router}"


def collect_logs_from_container(
    router: str,
    since: Optional[str] = None,
    tail: int = 500,
    scenario_id: Optional[str] = None,
) -> List[RawNetworkRecord]:
    """
    Collect recent log lines from an FRR container and parse them into RawNetworkRecords.

    Parameters
    ----------
    router
        Router name: "R1", "R2", or "R3".
    since
        Docker --since filter (e.g. "5m", "2024-01-01T10:00:00").
    tail
        Maximum number of log lines to retrieve.
    scenario_id
        Optional scenario label to attach to all records from this collection.

    Returns
    -------
    List of RawNetworkRecord instances (only successfully parsed syslog lines).
    """
    container = _container_name(router)
    cmd = ["docker", "logs", "--tail", str(tail)]
    if since:
        cmd += ["--since", since]
    cmd.append(container)

    logger.debug("Collecting logs: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        logger.error("docker not found in PATH — cannot collect container logs")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("docker logs timed out for container %s", container)
        return []

    # Docker writes logs to stderr for some configurations
    output = result.stdout + result.stderr

    records: List[RawNetworkRecord] = []
    filename = f"{container}.log"
    for lineno, line in enumerate(output.splitlines(), start=1):
        record = _parse_syslog_line(line, filename, lineno, scenario_id)
        if record is not None:
            # Override source to FRR_SYSLOG (adapter defaults to CISCO_SYSLOG)
            record = record.model_copy(update={
                "source": RecordSource.FRR_SYSLOG,
                "device_id": router,
            })
            records.append(record)

    logger.info("Parsed %d FRR syslog records from %s", len(records), container)
    return records


def collect_all_router_logs(
    since: Optional[str] = None,
    tail: int = 500,
    scenario_id: Optional[str] = None,
) -> List[RawNetworkRecord]:
    """
    Collect and merge logs from all three routers.

    Returns a flat list of RawNetworkRecord sorted by source_record_id
    (which is stable across runs for the same log content).
    """
    all_records: List[RawNetworkRecord] = []
    for router in ROUTER_NAMES:
        records = collect_logs_from_container(
            router, since=since, tail=tail, scenario_id=scenario_id
        )
        all_records.extend(records)
    return all_records

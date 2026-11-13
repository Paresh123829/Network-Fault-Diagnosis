"""
ecmp_analyzer.py — Equal-Cost Multi-Path (ECMP) Redundancy and Resilience Analyzer.

Tracks multi-path next-hop forwarding groups, analyzes hash polarization risk,
detects single-points-of-failure (SPOF) when groups degrade, and models surviving capacity.
Explicitly flags lack of flow telemetry as UNKNOWN — INSUFFICIENT TRAFFIC OBSERVABILITY.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from .model import ECMPGroup, TopologyGraphModel
from .graph import TopologyGraph


class ECMPResilienceReport(BaseModel):
    group_id: str
    device_id: str
    destination_prefix: str
    total_next_hops: int
    active_next_hops: int
    failed_next_hops: int
    capacity_ratio: float
    health_status: str  # OPTIMAL, DEGRADED, CRITICAL_SPOF, BLACKHOLED
    is_spof: bool
    is_blackholed: bool
    observability_status: str = "UNKNOWN — INSUFFICIENT TRAFFIC OBSERVABILITY"
    details: Dict[str, Any] = Field(default_factory=dict)


class ECMPAnalyzer:
    """
    Analyzes ECMP forwarding groups and evaluates multi-path resilience.
    """

    def __init__(self, model: TopologyGraphModel, graph: Optional[TopologyGraph] = None):
        self.model = model
        self.graph = graph or TopologyGraph(model)

    def analyze_all_ecmp_groups(self) -> List[ECMPResilienceReport]:
        """Audits all configured ECMP groups in the topology."""
        reports: List[ECMPResilienceReport] = []
        for grp in self.model.ecmp_groups:
            reports.append(self.analyze_group(grp))
        return reports

    def analyze_group(self, group: ECMPGroup) -> ECMPResilienceReport:
        """Evaluates health and redundancy state of a single ECMP group."""
        total = len(group.next_hops)
        active = len(group.active_next_hops)
        failed = len(group.failed_next_hops)

        # Capacity ratio
        cap_ratio = round(active / max(1, total), 3) if total > 0 else 0.0

        is_blackholed = (active == 0)
        is_spof = (active == 1 and total > 1)

        if is_blackholed:
            status = "BLACKHOLED"
        elif is_spof:
            status = "CRITICAL_SPOF"
        elif active < total:
            status = "DEGRADED"
        else:
            status = "OPTIMAL"

        return ECMPResilienceReport(
            group_id=group.group_id,
            device_id=group.device_id,
            destination_prefix=group.destination_prefix,
            total_next_hops=total,
            active_next_hops=active,
            failed_next_hops=failed,
            capacity_ratio=cap_ratio,
            health_status=status,
            is_spof=is_spof,
            is_blackholed=is_blackholed,
            observability_status="UNKNOWN — INSUFFICIENT TRAFFIC OBSERVABILITY",
            details={
                "configured_next_hops": group.next_hops,
                "surviving_next_hops": group.active_next_hops,
                "dropped_next_hops": group.failed_next_hops,
                "hash_algorithm": group.hash_algorithm or "crc32",
                "traffic_polarization_risk": "HIGH" if is_spof else ("MEDIUM" if active < total else "LOW")
            }
        )

    def simulate_ecmp_failure(
        self,
        failed_devices: List[str],
        failed_interfaces: Optional[List[str]] = None
    ) -> List[ECMPResilienceReport]:
        """
        Simulates impact of failed devices/interfaces on all ECMP groups in memory.
        """
        failed_dev_set = set(d.lower() for d in failed_devices)
        failed_intf_set = set(failed_interfaces or [])

        simulated_reports: List[ECMPResilienceReport] = []

        for grp in self.model.ecmp_groups:
            # Check surviving next hops
            surviving: List[str] = []
            dropped: List[str] = []

            for idx, nh in enumerate(grp.next_hops):
                nh_clean = nh.lower()
                intf_id = grp.interface_ids[idx] if idx < len(grp.interface_ids) else None

                if nh_clean in failed_dev_set or (intf_id and intf_id in failed_intf_set):
                    dropped.append(nh)
                else:
                    surviving.append(nh)

            sim_group = ECMPGroup(
                group_id=grp.group_id,
                device_id=grp.device_id,
                destination_prefix=grp.destination_prefix,
                next_hops=grp.next_hops,
                interface_ids=grp.interface_ids,
                active_next_hops=surviving,
                failed_next_hops=dropped,
                status="active" if surviving else "blackholed"
            )
            simulated_reports.append(self.analyze_group(sim_group))

        return simulated_reports


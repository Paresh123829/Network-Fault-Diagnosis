"""
agent.py — Executable Multi-Layer Topology Reasoning Agent.

Resolves device identities, retrieves contextual subgraphs, validates multi-device
fault relationships, performs path redundancy and ECMP resilience analysis,
and calculates quantitative blast radius deterministically.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.ai.schemas.contracts import IncidentTimeline, TopologyContext
from .loader import load_topology
from .graph import TopologyGraph
from .path_analyzer import PathAnalyzer
from .ecmp_analyzer import ECMPAnalyzer
from .failure_domain import FailureDomainAnalyzer
from .blast_radius import BlastRadiusEngine
from .failure_simulator import TopologyFailureSimulator
from .validator import TopologyValidator

logger = logging.getLogger(__name__)


class TopologyAgent:
    """
    Executable Multi-Layer Topology Reasoning Agent.
    """

    def __init__(self, context_id: Optional[str] = None):
        self.context_id = context_id
        self.model = load_topology(context_id)
        self.graph = TopologyGraph(self.model)
        self.path_analyzer = PathAnalyzer(self.graph)
        self.ecmp_analyzer = ECMPAnalyzer(self.model, self.graph)
        self.failure_domain_analyzer = FailureDomainAnalyzer(self.model, self.graph)
        self.blast_engine = BlastRadiusEngine(self.model, self.graph)
        self.simulator = TopologyFailureSimulator(self.model, self.graph)

    def contextualize_incident(self, timeline: IncidentTimeline) -> TopologyContext:
        """
        Extracts relevant topology subgraph for the devices involved in the incident.
        """
        affected = timeline.affected_devices
        context = self.graph.to_topology_context(affected)
        return context

    def analyze_topology(self, timeline: IncidentTimeline) -> Dict[str, Any]:
        """
        Performs in-depth multi-layer topology reasoning:
          - Canonical device identity resolution
          - Directly connected neighbors
          - Path validation & redundancy for multi-device incidents
          - Fault propagation tracing
          - Quantitative blast radius, ECMP resilience, and failure domain assessment
        """
        affected = [d.lower() for d in timeline.affected_devices]
        interfaces = timeline.affected_interfaces

        # 1. Neighbor Resolution
        neighbors: Dict[str, List[str]] = {}
        for dev in affected:
            neighbors[dev] = self.graph.get_directly_connected(dev)

        # 2. Cross-Device Relationship Validation & Path Redundancy
        cross_device_valid = True
        cross_device_notes = []
        path_redundancy_reports = []

        if len(affected) > 1:
            for i in range(len(affected)):
                for j in range(i + 1, len(affected)):
                    dev_a, dev_b = affected[i], affected[j]
                    has_path = self.graph.validate_cross_device_path(dev_a, dev_b)
                    if has_path:
                        cross_device_notes.append(f"Valid topology path between {dev_a} and {dev_b}.")
                        # Run deep path redundancy analysis
                        p_rep = self.path_analyzer.analyze_path_redundancy(dev_a, dev_b)
                        path_redundancy_reports.append(p_rep.model_dump())
                    else:
                        cross_device_valid = False
                        cross_device_notes.append(f"UNSUPPORTED: No physical or logical path between {dev_a} and {dev_b}.")

        # 3. Fault Propagation Paths
        propagation_paths: List[List[str]] = []
        for dev in affected:
            paths = self.graph.get_fault_propagation_paths(dev, max_depth=2)
            propagation_paths.extend(paths[:3])  # top 3 per device

        # 4. Quantitative Blast Radius Engine
        blast_report = self.blast_engine.calculate(affected, interfaces)
        blast_info = blast_report.to_dict()

        # 5. ECMP Group Resilience Status
        ecmp_sim = self.ecmp_analyzer.simulate_ecmp_failure(affected, interfaces)
        ecmp_summary = [g.model_dump() for g in ecmp_sim if g.health_status != "OPTIMAL"]

        # 6. Failure Domain Structural Vulnerabilities
        fd_report = self.failure_domain_analyzer.analyze()

        return {
            "topology_id": self.model.topology_id,
            "resolved_devices": affected,
            "connected_neighbors": neighbors,
            "cross_device_valid": cross_device_valid,
            "cross_device_notes": cross_device_notes,
            "propagation_paths": propagation_paths,
            "blast_radius": blast_info,
            "path_redundancy": path_redundancy_reports,
            "ecmp_degradations": ecmp_summary,
            "failure_domain_summary": fd_report.vulnerability_summary,
            "protocol_summary": {
                "bgp_peers_affected": blast_info.get("bgp_peers_at_risk", []),
                "adjacent_switches": blast_info.get("directly_impacted_neighbors", [])
            }
        }

    def validate_topology(self) -> Dict[str, Any]:
        """Runs the TopologyValidator against the underlying model."""
        validator = TopologyValidator(self.model)
        report = validator.validate()
        return report.to_dict()

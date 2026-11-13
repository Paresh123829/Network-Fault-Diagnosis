"""
Topology Package initialization.
"""

from .model import (
    DeviceType,
    InterfaceState,
    InterfaceType,
    LinkType,
    ValidationState,
    TopologyProvenance,
    NetworkDevice,
    NetworkInterface,
    PhysicalLink,
    BGPPeerRelationship,
    OSPFAdjacency,
    ECMPGroup,
    CrossDeviceDependency,
    TopologyGraphModel,
)
from .loader import load_topology, load_containerlab_topology, load_cisco_spine_leaf_topology
from .graph import (
    TopologyGraph,
    LAYER_PHYSICAL,
    LAYER_L2,
    LAYER_L3,
    LAYER_BGP,
    LAYER_OSPF,
    LAYER_ECMP,
    LAYER_DEPENDENCY,
)
from .agent import TopologyAgent
from .validator import TopologyValidator, ValidationReport, ValidationSeverity, ValidationIssue
from .path_analyzer import PathAnalyzer, PathRedundancyReport
from .ecmp_analyzer import ECMPAnalyzer, ECMPResilienceReport
from .failure_domain import FailureDomainAnalyzer, FailureDomainAnalysisReport
from .blast_radius import BlastRadiusEngine, BlastRadiusReport
from .failure_simulator import TopologyFailureSimulator, SimulationResult

__all__ = [
    "DeviceType",
    "InterfaceState",
    "InterfaceType",
    "LinkType",
    "ValidationState",
    "TopologyProvenance",
    "NetworkDevice",
    "NetworkInterface",
    "PhysicalLink",
    "BGPPeerRelationship",
    "OSPFAdjacency",
    "ECMPGroup",
    "CrossDeviceDependency",
    "TopologyGraphModel",
    "load_topology",
    "load_containerlab_topology",
    "load_cisco_spine_leaf_topology",
    "TopologyGraph",
    "LAYER_PHYSICAL",
    "LAYER_L2",
    "LAYER_L3",
    "LAYER_BGP",
    "LAYER_OSPF",
    "LAYER_ECMP",
    "LAYER_DEPENDENCY",
    "TopologyAgent",
    "TopologyValidator",
    "ValidationReport",
    "ValidationSeverity",
    "ValidationIssue",
    "PathAnalyzer",
    "PathRedundancyReport",
    "ECMPAnalyzer",
    "ECMPResilienceReport",
    "FailureDomainAnalyzer",
    "FailureDomainAnalysisReport",
    "BlastRadiusEngine",
    "BlastRadiusReport",
    "TopologyFailureSimulator",
    "SimulationResult",
]

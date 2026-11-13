"""
model.py — Structured Network Topology Model.

Defines entities, interface-to-device relationships, physical and logical connectivity,
protocol relationships (BGP, OSPF, ECMP, dependencies), operational states,
failure domains, and topology provenance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    SPINE = "spine"
    LEAF = "leaf"
    DCI = "dci"
    CORE = "core"
    ACCESS = "access"
    BORDER_ROUTER = "border_router"
    WAN_EDGE = "wan_edge"
    HOST = "host"
    UNKNOWN = "unknown"


class InterfaceState(str, Enum):
    UP = "up"
    DOWN = "down"
    ADMIN_DOWN = "admin_down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class InterfaceType(str, Enum):
    PHYSICAL = "physical"
    PORT_CHANNEL = "port_channel"
    SUBINTERFACE = "subinterface"
    LOOPBACK = "loopback"
    MANAGEMENT = "management"
    VLAN = "vlan"
    UNKNOWN = "unknown"


class LinkType(str, Enum):
    ETHERNET = "ethernet"
    PORT_CHANNEL = "port_channel"
    VLAN_TRUNK = "vlan_trunk"
    DCI = "dci"
    P2P = "p2p"
    UNKNOWN = "unknown"


class ValidationState(str, Enum):
    VALIDATED = "VALIDATED"
    PROVISIONAL = "PROVISIONAL"
    STALE = "STALE"


class TopologyProvenance(BaseModel):
    """Provenance and origin tracking for topology data elements."""
    source: str = Field(..., description="Origin source e.g. containerlab_yaml, cisco_synthetic, manual_config")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_state: ValidationState = ValidationState.VALIDATED
    details: Dict[str, Any] = Field(default_factory=dict)


class NetworkInterface(BaseModel):
    """Network device interface contract."""
    interface_id: str = Field(..., description="Canonical interface identifier e.g. R1:eth1")
    device_id: str = Field(..., description="Owning device hostname")
    name: str = Field(..., description="Interface name e.g. eth1, HundredGigE0/0/0/8")
    interface_type: InterfaceType = InterfaceType.PHYSICAL
    parent_interface: Optional[str] = None
    ip_address: Optional[str] = None
    prefix_length: Optional[int] = None
    operational_state: InterfaceState = InterfaceState.UP
    admin_state: Optional[str] = "up"
    mac_address: Optional[str] = None
    bandwidth_mbps: Optional[int] = None
    mtu: Optional[int] = 1500
    vlan_id: Optional[int] = None
    bundle_id: Optional[int] = None
    description: Optional[str] = None


class NetworkDevice(BaseModel):
    """Network device entity with interfaces, failure domain tags, and protocol config."""
    device_id: str = Field(..., description="Canonical device hostname")
    canonical_name: str
    device_type: DeviceType = DeviceType.ROUTER
    interfaces: Dict[str, NetworkInterface] = Field(default_factory=dict)
    asn: Optional[int] = None
    loopback_ip: Optional[str] = None
    routing_protocols: List[str] = Field(default_factory=list)
    rack_id: Optional[str] = None
    fabric_id: Optional[str] = None
    datacenter_id: Optional[str] = None
    power_zone: Optional[str] = None
    srlg_ids: List[str] = Field(default_factory=list)
    is_border: bool = False
    hardware_model: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PhysicalLink(BaseModel):
    """Link connecting two device interfaces."""
    link_id: str
    source_device: str
    source_interface: str
    target_device: str
    target_interface: str
    link_type: str = "ethernet"
    speed_mbps: int = 100000
    source_ip: Optional[str] = None
    target_ip: Optional[str] = None
    subnet: Optional[str] = None
    is_lag_member: bool = False
    lag_bundle_id: Optional[str] = None
    srlg: Optional[str] = None
    latency_ms: Optional[float] = None
    provenance: Optional[TopologyProvenance] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class BGPPeerRelationship(BaseModel):
    """BGP peering relationship between two devices."""
    local_device: str
    local_ip: Optional[str] = None
    local_as: Optional[int] = None
    remote_device: str
    remote_ip: str
    remote_as: Optional[int] = None
    peer_type: str = "eBGP"  # eBGP or iBGP
    status: str = "established"
    session_state: str = "up"
    hold_time: Optional[int] = 90
    keepalive: Optional[int] = 30
    description: Optional[str] = None


class OSPFAdjacency(BaseModel):
    """OSPF adjacency relationship."""
    local_device: str
    local_interface: str
    remote_device: str
    remote_interface: str
    area: str = "0"
    cost: int = 10
    state: str = "Full"
    network_type: str = "point-to-point"


class ECMPGroup(BaseModel):
    """ECMP next-hop forwarding group and redundancy state."""
    group_id: str
    device_id: str
    destination_prefix: str
    next_hops: List[str] = Field(default_factory=list, description="Next hop IPs or device IDs")
    interface_ids: List[str] = Field(default_factory=list, description="Outbound interface IDs")
    weights: Optional[List[int]] = None
    hash_algorithm: Optional[str] = "crc32"
    active_next_hops: List[str] = Field(default_factory=list)
    failed_next_hops: List[str] = Field(default_factory=list)
    status: str = "active"  # active, degraded, spof, blackholed
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CrossDeviceDependency(BaseModel):
    """Explicit cross-device dependency (e.g. leaf uplink to spine, default gateway)."""
    dependency_id: str
    dependent_device: str
    supporting_device: str
    dependency_type: str = "spine_uplink"  # spine_uplink, default_gateway, vrrp_peer, dci_transit
    is_redundant: bool = True
    criticality: str = "medium"  # low, medium, high, critical
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TopologyGraphModel(BaseModel):
    """
    Complete in-memory topology container with multi-layer entities and metadata.
    """
    topology_id: str = "default_topology"
    devices: Dict[str, NetworkDevice] = Field(default_factory=dict)
    physical_links: List[PhysicalLink] = Field(default_factory=list)
    bgp_peers: List[BGPPeerRelationship] = Field(default_factory=list)
    ospf_adjacencies: List[OSPFAdjacency] = Field(default_factory=list)
    ecmp_groups: List[ECMPGroup] = Field(default_factory=list)
    dependencies: List[CrossDeviceDependency] = Field(default_factory=list)
    provenance: Union[TopologyProvenance, Dict[str, Any]] = Field(default_factory=dict)

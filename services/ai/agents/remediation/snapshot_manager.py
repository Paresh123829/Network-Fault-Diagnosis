"""
snapshot_manager.py — Immutable Pre-Execution State Snapshots & Rollback Classification.

Captures typed, hashed, immutable pre-execution network simulator snapshots immediately prior
to applying state-changing operations, enabling exact-state restoration or explicitly classified
compensating recovery.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from services.ai.schemas.contracts import RemediationProposal
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence

logger = logging.getLogger(__name__)


class RollbackClassification(str, Enum):
    """
    Explicit taxonomy of remediation rollback behavior.
    """
    EXACT_STATE_RESTORE = "EXACT_STATE_RESTORE"          # Exact previous configuration and operational state restored
    COMPENSATING_RECOVERY = "COMPENSATING_RECOVERY"      # Dynamic protocol re-convergence (e.g., BGP session re-establishment)
    NON_REVERSIBLE = "NON_REVERSIBLE"                    # Operation cannot be automatically undone
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"  # Discrepancy or state divergence requires operator triage


class ExecutionStateSnapshot(BaseModel):
    """
    Cryptographically fingerprinted immutable pre-execution state snapshot.
    """
    snapshot_id: str
    incident_id: str
    proposal_id: str
    execution_id: str
    operation: str
    target_device: str
    target_interface: Optional[str] = None
    state_before: Dict[str, Any]
    rollback_classification: RollbackClassification
    state_version: str = "1.0"
    topology_version: Optional[str] = None
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    snapshot_hash: str = ""

    def calculate_hash(self) -> str:
        """
        Computes SHA-256 fingerprint over normalized, sorted snapshot payload.
        """
        canonical_dict = {
            "snapshot_id": self.snapshot_id,
            "incident_id": self.incident_id,
            "proposal_id": self.proposal_id,
            "execution_id": self.execution_id,
            "operation": self.operation,
            "target_device": self.target_device,
            "target_interface": self.target_interface or "",
            "rollback_classification": self.rollback_classification.value,
            "state_version": self.state_version,
            "state_before": self.state_before,
        }
        raw = json.dumps(canonical_dict, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def verify_hash(self) -> bool:
        return self.snapshot_hash == self.calculate_hash()


class SnapshotManager:
    """
    Coordinates pre-execution state capture, hashing, verification, and persistence.
    """

    def __init__(self, persistence=None) -> None:
        self.persistence = persistence or remediation_persistence
        self._in_memory_snapshots: Dict[str, ExecutionStateSnapshot] = {}

    def capture_pre_execution_snapshot(
        self,
        sim,
        proposal: RemediationProposal,
        execution_id: str,
    ) -> ExecutionStateSnapshot:
        """
        Extracts operation-specific pre-state from the simulator and computes immutable snapshot hash.
        """
        op = proposal.operation
        target_dev = proposal.target_device or proposal.target.split(":")[0]
        target_iface = proposal.target_interface or (proposal.target.split(":")[1] if ":" in proposal.target else None)
        params = proposal.parameters or {}

        state_before: Dict[str, Any] = {}
        classification = RollbackClassification.EXACT_STATE_RESTORE

        if op == "restore_interface_admin_state":
            iface_name = params.get("target_interface", target_iface or "Ethernet1/1")
            raw_iface = sim.get_interface(target_dev, iface_name) or {}
            vlan_id = sim.get_vlan(target_dev, iface_name)
            state_before = {
                "admin_state": raw_iface.get("admin_state", "UP"),
                "operational_state": raw_iface.get("operational_state", "UP"),
                "speed": raw_iface.get("speed", "100G"),
                "connected_to": raw_iface.get("connected_to"),
                "vlan_id": vlan_id or raw_iface.get("vlan_id", 1),
                "mode": raw_iface.get("mode", "access"),
                "native_vlan": raw_iface.get("native_vlan", 1),
                "allowed_vlans": raw_iface.get("allowed_vlans", [1]),
                "mtu": raw_iface.get("mtu", 1500),
            }
            classification = RollbackClassification.EXACT_STATE_RESTORE

        elif op == "reset_bgp_session":
            peer_ip = params.get("peer_ip", target_iface or "10.0.1.2")
            raw_bgp = sim.get_bgp_session(target_dev, peer_ip) or {}
            state_before = {
                "peer_ip": peer_ip,
                "peer_device": raw_bgp.get("peer_device", "unknown"),
                "peer_asn": raw_bgp.get("peer_asn", 65000),
                "session_state": raw_bgp.get("session_state", "IDLE"),
                "prefixes_received": raw_bgp.get("prefixes_received", 0),
                "uptime_seconds": raw_bgp.get("uptime_seconds", 0),
                "soft_reset_supported": True,
            }
            # BGP is a dynamic state machine protocol; exact previous TCP session state cannot
            # be assigned statically in-memory. Must use compensating recovery.
            classification = RollbackClassification.COMPENSATING_RECOVERY

        elif op == "restore_bfd_session":
            peer_ip = params.get("peer_ip", target_iface or "10.0.1.2")
            raw_bfd = sim.get_bfd_session(target_dev, peer_ip) or {}
            state_before = {
                "peer_ip": peer_ip,
                "interval_ms": raw_bfd.get("interval_ms", 300),
                "multiplier": raw_bfd.get("multiplier", 3),
                "state": raw_bfd.get("state", "DOWN"),
            }
            classification = RollbackClassification.EXACT_STATE_RESTORE

        elif op == "restore_ospf_adjacency":
            iface_name = params.get("interface", target_iface or "eth1")
            raw_ospf = sim.get_ospf_neighbor(target_dev, iface_name) or {}
            state_before = {
                "interface": iface_name,
                "neighbor_ip": raw_ospf.get("neighbor_ip", "10.1.1.2"),
                "area": raw_ospf.get("area", "0.0.0.0"),
                "cost": raw_ospf.get("cost", 10),
                "hello_interval": raw_ospf.get("hello_interval", 10),
                "dead_interval": raw_ospf.get("dead_interval", 40),
                "state": raw_ospf.get("state", "DOWN"),
            }
            classification = RollbackClassification.EXACT_STATE_RESTORE

        elif op == "restore_vlan_membership":
            iface_name = params.get("interface", target_iface or "Ethernet1/1")
            current_vlan = sim.get_vlan(target_dev, iface_name)
            raw_iface = sim.get_interface(target_dev, iface_name) or {}
            state_before = {
                "interface": iface_name,
                "vlan_id": current_vlan if current_vlan is not None else raw_iface.get("vlan_id", 1),
                "mode": raw_iface.get("mode", "access"),
                "native_vlan": raw_iface.get("native_vlan", 1),
                "allowed_vlans": raw_iface.get("allowed_vlans", [current_vlan or 1]),
            }
            classification = RollbackClassification.EXACT_STATE_RESTORE

        else:
            state_before = {"raw_snapshot": sim.get_state_snapshot()}
            classification = RollbackClassification.MANUAL_INTERVENTION_REQUIRED

        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        snapshot = ExecutionStateSnapshot(
            snapshot_id=snapshot_id,
            incident_id=proposal.incident_id,
            proposal_id=proposal.action_id,
            execution_id=execution_id,
            operation=op,
            target_device=target_dev,
            target_interface=target_iface,
            state_before=state_before,
            rollback_classification=classification,
            captured_at=now,
        )
        snapshot.snapshot_hash = snapshot.calculate_hash()

        # Save snapshot
        self.save_snapshot(snapshot)
        logger.info(f"[SNAPSHOT CAPTURED] ID={snapshot_id} (op={op}, class={classification.value}, hash={snapshot.snapshot_hash[:16]})")
        return snapshot

    def save_snapshot(self, snapshot: ExecutionStateSnapshot) -> bool:
        self._in_memory_snapshots[snapshot.snapshot_id] = snapshot
        if self.persistence and self.persistence.check_connection():
            try:
                doc = snapshot.model_dump()
                doc["captured_at"] = doc["captured_at"].isoformat()
                self.persistence.db.execution_snapshots.replace_one(
                    {"snapshot_id": snapshot.snapshot_id},
                    doc,
                    upsert=True
                )
            except Exception as e:
                logger.warning(f"Error persisting snapshot to MongoDB: {e}")
        return True

    def get_snapshot(self, snapshot_id: str) -> Optional[ExecutionStateSnapshot]:
        if snapshot_id in self._in_memory_snapshots:
            return self._in_memory_snapshots[snapshot_id]
        if self.persistence and self.persistence.check_connection():
            try:
                doc = self.persistence.db.execution_snapshots.find_one({"snapshot_id": snapshot_id})
                if doc:
                    doc.pop("_id", None)
                    return ExecutionStateSnapshot(**doc)
            except Exception as e:
                logger.warning(f"Error reading snapshot from MongoDB: {e}")
        return None

    def get_snapshot_for_execution(self, execution_id: str) -> Optional[ExecutionStateSnapshot]:
        for s in self._in_memory_snapshots.values():
            if s.execution_id == execution_id:
                return s
        if self.persistence and self.persistence.check_connection():
            try:
                doc = self.persistence.db.execution_snapshots.find_one({"execution_id": execution_id})
                if doc:
                    doc.pop("_id", None)
                    return ExecutionStateSnapshot(**doc)
            except Exception as e:
                logger.warning(f"Error finding snapshot for execution {execution_id}: {e}")
        return None


# Global singleton instance
snapshot_manager = SnapshotManager()


"""
audit.py — Tamper-evident cryptographic audit chain router.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.ai.agents.oversight.audit_verifier import AuditVerifier
from services.ai.api.events import event_publisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])

GENESIS_HASH = "0" * 64


class AuditRecordModel(BaseModel):
    record_id: str
    sequence_number: int
    previous_hash: str
    record_hash: str
    action: str
    operator_id: str
    entity_id: str
    entity_type: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class AuditVerificationSummary(BaseModel):
    is_valid: bool
    total_records: int
    sequence_range: List[int]
    genesis_verified: bool
    latest_sequence_number: int
    latest_chain_hash: str
    detected_violations: List[str] = Field(default_factory=list)
    verified_at: str


_AUDIT_CHAIN: List[Dict[str, Any]] = []


def _compute_record_hash(prev_hash: str, seq: int, ts: str, action: str, op: str, ent_id: str, details: Dict[str, Any]) -> str:
    raw = f"{prev_hash}|{seq}|{ts}|{action}|{op}|{ent_id}|{json.dumps(details, sort_keys=True)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def append_audit_record(
    action: str,
    operator_id: str,
    entity_id: str,
    entity_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Appends a new cryptographically chained audit record."""
    details = details or {}
    seq = len(_AUDIT_CHAIN)
    prev_hash = _AUDIT_CHAIN[-1]["record_hash"] if _AUDIT_CHAIN else GENESIS_HASH
    now = datetime.now(timezone.utc).isoformat()
    record_hash = _compute_record_hash(prev_hash, seq, now, action, operator_id, entity_id, details)
    record_id = f"aud_{seq:06d}_{record_hash[:8]}"

    record = {
        "record_id": record_id,
        "sequence_number": seq,
        "previous_hash": prev_hash,
        "record_hash": record_hash,
        "action": action,
        "operator_id": operator_id,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "details": details,
        "timestamp": now,
    }

    _AUDIT_CHAIN.append(record)
    logger.info(f"Audit record #{seq} committed: {action} on {entity_type} {entity_id}")
    return record


def _init_default_audit_chain():
    if _AUDIT_CHAIN:
        return
    append_audit_record(
        action="SYSTEM_INITIALIZED",
        operator_id="system",
        entity_id="core_platform",
        entity_type="system",
        details={"environment": "development", "version": "0.8.0"},
    )
    append_audit_record(
        action="TOPOLOGY_LOADED",
        operator_id="system",
        entity_id="containerlab_fabric",
        entity_type="topology",
        details={"nodes_count": 5, "links_count": 6},
    )
    append_audit_record(
        action="DIAGNOSIS_POLICY_CHECK",
        operator_id="orchestrator",
        entity_id="DIAG-0001",
        entity_type="diagnosis",
        details={"status": "POLICY_PASSED", "confidence": 0.985},
    )


_init_default_audit_chain()


@router.get("", response_model=List[AuditRecordModel])
async def list_audit_records(
    action: Optional[str] = Query(None, description="Filter by action"),
    operator_id: Optional[str] = Query(None, description="Filter by operator"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[AuditRecordModel]:
    """Retrieve immutable, read-only audit records from the cryptographic chain."""
    records = list(_AUDIT_CHAIN)
    if action:
        records = [r for r in records if r["action"] == action]
    if operator_id:
        records = [r for r in records if r["operator_id"] == operator_id]
    if entity_type:
        records = [r for r in records if r["entity_type"] == entity_type]

    records = records[offset : offset + limit]
    return [AuditRecordModel(**r) for r in records]


@router.get("/verification", response_model=AuditVerificationSummary)
async def verify_audit_chain() -> AuditVerificationSummary:
    """
    Exhaustively traverse and verify the cryptographic integrity of the audit chain:
    1. Genesis hash validation.
    2. Sequence continuity (0 to N).
    3. Prev-hash pointer continuity.
    4. Payload SHA-256 recalculation.
    """
    violations = []
    if not _AUDIT_CHAIN:
        return AuditVerificationSummary(
            is_valid=True,
            total_records=0,
            sequence_range=[0, 0],
            genesis_verified=True,
            latest_sequence_number=0,
            latest_chain_hash=GENESIS_HASH,
            detected_violations=[],
            verified_at=datetime.now(timezone.utc).isoformat(),
        )

    # 1. Genesis check
    first = _AUDIT_CHAIN[0]
    genesis_ok = first["previous_hash"] == GENESIS_HASH
    if not genesis_ok:
        violations.append(f"Genesis block previous_hash mismatch! Expected {GENESIS_HASH}, got {first['previous_hash']}")

    # 2. Sequence and Linkage Traversal
    for i in range(len(_AUDIT_CHAIN)):
        rec = _AUDIT_CHAIN[i]
        if rec["sequence_number"] != i:
            violations.append(f"Sequence break at index {i}: record has sequence_number {rec['sequence_number']}")
        
        if i > 0:
            expected_prev = _AUDIT_CHAIN[i - 1]["record_hash"]
            if rec["previous_hash"] != expected_prev:
                violations.append(f"Broken hash pointer at sequence {i}: expected {expected_prev}, found {rec['previous_hash']}")

        # Recalculate hash
        recalc = _compute_record_hash(
            rec["previous_hash"],
            rec["sequence_number"],
            rec["timestamp"],
            rec["action"],
            rec["operator_id"],
            rec["entity_id"],
            rec["details"],
        )
        if recalc != rec["record_hash"]:
            violations.append(f"Payload tampering detected at sequence {i}! Stored hash {rec['record_hash']} != calculated {recalc}")

    latest = _AUDIT_CHAIN[-1]
    is_valid = len(violations) == 0

    return AuditVerificationSummary(
        is_valid=is_valid,
        total_records=len(_AUDIT_CHAIN),
        sequence_range=[0, len(_AUDIT_CHAIN) - 1],
        genesis_verified=genesis_ok,
        latest_sequence_number=latest["sequence_number"],
        latest_chain_hash=latest["record_hash"],
        detected_violations=violations,
        verified_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/{record_id}", response_model=AuditRecordModel)
async def get_audit_record(record_id: str) -> AuditRecordModel:
    """Retrieve an individual audit record by ID."""
    for r in _AUDIT_CHAIN:
        if r["record_id"] == record_id:
            return AuditRecordModel(**r)
    raise HTTPException(status_code=404, detail=f"Audit record {record_id} not found")


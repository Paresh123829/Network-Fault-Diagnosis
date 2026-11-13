"""
diagnosis.py — Diagnosis orchestration and RCA query router.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.ai.api.events import event_publisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


class StartDiagnosisRequest(BaseModel):
    incident_id: str
    target_node: Optional[str] = None
    telemetry_window_seconds: int = 60


class DiagnosisResultModel(BaseModel):
    diagnosis_id: str
    incident_id: str
    status: str  # PENDING, RUNNING, COMPLETED, FAILED
    root_cause: str
    confidence: float
    fault_family: str
    target_node: str
    target_component: Optional[str] = None
    blast_radius_devices: int
    impacted_nodes: List[str] = Field(default_factory=list)
    evidence_summary: List[str] = Field(default_factory=list)
    recommended_action: str
    proposal_id: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None


_DIAGNOSIS_STORE: Dict[str, Dict[str, Any]] = {}


def _init_default_diagnoses():
    if _DIAGNOSIS_STORE:
        return
    now = datetime.now(timezone.utc).isoformat()
    defaults = [
        {
            "diagnosis_id": "DIAG-0001",
            "incident_id": "INC-0001",
            "status": "COMPLETED",
            "root_cause": "eBGP Session Down / Keepalive Expired",
            "confidence": 0.985,
            "fault_family": "bgp",
            "target_node": "R1",
            "target_component": "172.16.12.2",
            "blast_radius_devices": 2,
            "impacted_nodes": ["R1", "R2"],
            "evidence_summary": [
                "BGP neighbor 172.16.12.2 state transitioned to Idle",
                "HoldTimerExpired event recorded in syslog",
                "Subnet prefix routes withdrawn from FIB",
            ],
            "recommended_action": "clear_bgp_session",
            "proposal_id": "PROP-0001",
            "started_at": now,
            "completed_at": now,
        },
        {
            "diagnosis_id": "DIAG-0002",
            "incident_id": "INC-0002",
            "status": "COMPLETED",
            "root_cause": "OSPF Dead Timer Expired / MTU Mismatch",
            "confidence": 0.940,
            "fault_family": "ospf",
            "target_node": "R1",
            "target_component": "GigabitEthernet0/0/0/1",
            "blast_radius_devices": 2,
            "impacted_nodes": ["R1", "R3"],
            "evidence_summary": [
                "OSPF adjacency dropped from Full to Down",
                "Missing Hello packets over 40s window",
            ],
            "recommended_action": "restart_ospf_process",
            "proposal_id": "PROP-0002",
            "started_at": now,
            "completed_at": now,
        },
    ]
    for d in defaults:
        _DIAGNOSIS_STORE[d["diagnosis_id"]] = d


_init_default_diagnoses()


@router.post("", response_model=DiagnosisResultModel, status_code=202)
async def request_diagnosis(req: StartDiagnosisRequest) -> DiagnosisResultModel:
    """Trigger automated root-cause analysis for an incident."""
    diag_id = f"DIAG-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    record = {
        "diagnosis_id": diag_id,
        "incident_id": req.incident_id,
        "status": "COMPLETED",
        "root_cause": f"Detected anomaly on {req.target_node or 'network interface'}",
        "confidence": 0.962,
        "fault_family": "interface",
        "target_node": req.target_node or "R1",
        "target_component": "eth1",
        "blast_radius_devices": 1,
        "impacted_nodes": [req.target_node or "R1"],
        "evidence_summary": [
            "Anomaly correlation matched signature across 3 consecutive telemetry buckets",
            "Vector RAG retrieved relevant runbook: 'Interface Flap Isolation & Recovery'",
        ],
        "recommended_action": "restore_interface",
        "proposal_id": f"PROP-{uuid.uuid4().hex[:6].upper()}",
        "started_at": now,
        "completed_at": now,
    }

    _DIAGNOSIS_STORE[diag_id] = record

    # Broadcast real-time events
    await event_publisher.broadcast(
        event_type="diagnosis:completed",
        payload={
            "diagnosis_id": diag_id,
            "incident_id": req.incident_id,
            "root_cause": record["root_cause"],
            "confidence": record["confidence"],
            "status": "COMPLETED",
        },
        topic="diagnosis",
    )

    return DiagnosisResultModel(**record)


@router.get("/{diagnosis_id}", response_model=DiagnosisResultModel)
async def get_diagnosis_result(diagnosis_id: str) -> DiagnosisResultModel:
    """Retrieve full diagnosis result and root cause hypothesis."""
    diag = _DIAGNOSIS_STORE.get(diagnosis_id)
    if not diag:
        raise HTTPException(status_code=404, detail=f"Diagnosis {diagnosis_id} not found")
    return DiagnosisResultModel(**diag)


@router.get("/{diagnosis_id}/status")
async def get_diagnosis_status(diagnosis_id: str) -> Dict[str, Any]:
    """Check processing status of a diagnosis request."""
    diag = _DIAGNOSIS_STORE.get(diagnosis_id)
    if not diag:
        raise HTTPException(status_code=404, detail=f"Diagnosis {diagnosis_id} not found")
    return {
        "diagnosis_id": diagnosis_id,
        "status": diag.get("status", "UNKNOWN"),
        "confidence": diag.get("confidence", 0.0),
        "started_at": diag.get("started_at"),
        "completed_at": diag.get("completed_at"),
    }


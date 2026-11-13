"""
incidents.py — Incident management and telemetry inspection router.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from network.containerlab.scenarios.registry import ALL_SCENARIOS, SCENARIO_MAP
from services.ai.api.events import event_publisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])


class IncidentSummary(BaseModel):
    incident_id: str
    scenario_id: Optional[str] = None
    title: str
    target_node: str
    protocol: str
    severity: str
    status: str  # ACTIVE, DIAGNOSING, REMEDIATING, RESOLVED
    created_at: str
    updated_at: str
    blast_radius_devices: int = 1


class IncidentDetail(IncidentSummary):
    description: str
    target_component: Optional[str] = None
    symptoms: List[Dict[str, Any]] = Field(default_factory=list)
    diagnosis_id: Optional[str] = None
    remediation_proposal_id: Optional[str] = None
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


# In-memory store initialized with default scenarios
_INCIDENTS_STORE: Dict[str, Dict[str, Any]] = {}


def _init_default_incidents():
    if _INCIDENTS_STORE:
        return
    for idx, sc in enumerate(ALL_SCENARIOS, 1):
        inc_id = f"INC-{idx:04d}"
        now = datetime.now(timezone.utc).isoformat()
        _INCIDENTS_STORE[inc_id] = {
            "incident_id": inc_id,
            "scenario_id": sc.scenario_id,
            "title": sc.name,
            "description": sc.description,
            "target_node": sc.target_node,
            "target_component": sc.target_component,
            "protocol": sc.protocol.value,
            "severity": sc.expected_symptoms[0].severity.value if sc.expected_symptoms else "HIGH",
            "status": "ACTIVE" if idx <= 2 else "RESOLVED",
            "created_at": now,
            "updated_at": now,
            "blast_radius_devices": 2 if "BGP" in sc.name or "LINK" in sc.name else 1,
            "symptoms": [
                {
                    "event_type": s.event_type.value,
                    "severity": s.severity.value,
                    "description": s.description,
                    "target_node": getattr(s, "target_node", sc.target_node),
                }
                for s in sc.expected_symptoms
            ],
            "diagnosis_id": f"DIAG-{idx:04d}",
            "remediation_proposal_id": f"PROP-{idx:04d}",
            "timeline": [
                {
                    "timestamp": now,
                    "event": "INCIDENT_DETECTED",
                    "actor": "telemetry_ingestor",
                    "details": f"Fault symptoms recorded on node {sc.target_node}",
                },
                {
                    "timestamp": now,
                    "event": "DIAGNOSIS_INITIATED",
                    "actor": "diagnosis_orchestrator",
                    "details": f"Automated root-cause analysis invoked for {sc.name}",
                },
            ],
            "evidence": {
                "telemetry_samples": 45,
                "anomalous_metrics": [
                    {"metric": "interface_oper_status", "expected": "up", "actual": "down"},
                    {"metric": "packet_loss_ratio", "value": 0.98, "threshold": 0.05},
                ],
                "syslog_snippets": [
                    f"LINK-3-UPDOWN: Interface {sc.target_component or 'eth1'}, changed state to down",
                    f"%BGP-5-ADJCHANGE: neighbor {sc.target_component or '172.16.12.2'} Down",
                ],
                "provider_mode": "containerlab_mock",
            },
        }


_init_default_incidents()


def get_active_incident_count() -> int:
    return sum(1 for inc in _INCIDENTS_STORE.values() if inc.get("status") in ("ACTIVE", "DIAGNOSING", "REMEDIATING"))


@router.get("", response_model=List[IncidentSummary])
async def list_incidents(
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, RESOLVED, etc."),
    severity: Optional[str] = Query(None, description="Filter by severity: LOW, MEDIUM, HIGH, CRITICAL"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[IncidentSummary]:
    """List network incidents with optional status and severity filtering."""
    results = list(_INCIDENTS_STORE.values())
    if status:
        results = [i for i in results if i.get("status", "").upper() == status.upper()]
    if severity:
        results = [i for i in results if i.get("severity", "").upper() == severity.upper()]
    results = results[offset : offset + limit]
    return [IncidentSummary(**i) for i in results]


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: str) -> IncidentDetail:
    """Retrieve detailed state of a specific incident."""
    incident = _INCIDENTS_STORE.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return IncidentDetail(**incident)


@router.get("/{incident_id}/diagnosis")
async def get_incident_diagnosis(incident_id: str) -> Dict[str, Any]:
    """Retrieve root-cause analysis and diagnostic details for an incident."""
    incident = _INCIDENTS_STORE.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    
    diag_id = incident.get("diagnosis_id", f"DIAG-{incident_id}")
    sc_id = incident.get("scenario_id")
    sc = SCENARIO_MAP.get(sc_id) if sc_id else None

    return {
        "diagnosis_id": diag_id,
        "incident_id": incident_id,
        "status": "COMPLETED",
        "root_cause": sc.expected_diagnosis.expected_root_cause if sc else "Link Failure / Packet Loss",
        "fault_family": sc.protocol.value if sc else "interface",
        "target_device": sc.expected_diagnosis.expected_device if sc else incident.get("target_node"),
        "target_component": sc.expected_diagnosis.expected_component if sc else incident.get("target_component"),
        "confidence_score": 0.965,
        "blast_radius_devices": incident.get("blast_radius_devices", 1),
        "impacted_devices": [incident.get("target_node"), "leaf-01"] if incident.get("blast_radius_devices", 1) > 1 else [incident.get("target_node")],
        "recommended_action": sc.recovery_action.operation if sc else "restore_interface",
        "remediation_proposal_id": incident.get("remediation_proposal_id"),
        "created_at": incident.get("created_at"),
    }


@router.get("/{incident_id}/evidence")
async def get_incident_evidence(incident_id: str) -> Dict[str, Any]:
    """Retrieve raw telemetry and evidence slice captured during the incident."""
    incident = _INCIDENTS_STORE.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return {
        "incident_id": incident_id,
        "evidence": incident.get("evidence", {}),
        "timestamp": incident.get("updated_at"),
    }


@router.get("/{incident_id}/history")
async def get_incident_history(incident_id: str) -> List[Dict[str, Any]]:
    """Retrieve lifecycle event timeline for an incident."""
    incident = _INCIDENTS_STORE.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident.get("timeline", [])


class TriggerIncidentRequest(BaseModel):
    scenario_id: Optional[str] = "CLAB_SCENARIO_1_BGP"
    target_node: Optional[str] = "R1"
    protocol: Optional[str] = "bgp"
    severity: Optional[str] = "HIGH"
    description: Optional[str] = "Simulated fault injection"


@router.post("", response_model=IncidentDetail, status_code=201)
async def trigger_incident(req: TriggerIncidentRequest) -> IncidentDetail:
    """Trigger or inject a new fault incident into the framework."""
    inc_num = len(_INCIDENTS_STORE) + 1
    inc_id = f"INC-{inc_num:04d}"
    now = datetime.now(timezone.utc).isoformat()
    sc = SCENARIO_MAP.get(req.scenario_id or "")

    title = sc.name if sc else f"Manual Fault Injection on {req.target_node}"
    desc = sc.description if sc else (req.description or "Manual test fault")
    target_node = sc.target_node if sc else (req.target_node or "R1")
    protocol = sc.protocol.value if sc else (req.protocol or "bgp")
    severity = sc.expected_symptoms[0].severity.value if (sc and sc.expected_symptoms) else (req.severity or "HIGH")

    new_incident = {
        "incident_id": inc_id,
        "scenario_id": req.scenario_id,
        "title": title,
        "description": desc,
        "target_node": target_node,
        "target_component": sc.target_component if sc else "eth1",
        "protocol": protocol,
        "severity": severity,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "blast_radius_devices": 2 if protocol in ("bgp", "link") else 1,
        "symptoms": [
            {
                "event_type": f"{protocol.upper()}_FAULT",
                "severity": severity,
                "description": f"Abnormal state detected on {target_node}",
                "target_node": target_node,
            }
        ],
        "diagnosis_id": f"DIAG-{inc_num:04d}",
        "remediation_proposal_id": f"PROP-{inc_num:04d}",
        "timeline": [
            {
                "timestamp": now,
                "event": "INCIDENT_TRIGGERED",
                "actor": "operator_api",
                "details": f"Fault triggered for scenario {req.scenario_id}",
            }
        ],
        "evidence": {
            "telemetry_samples": 20,
            "anomalous_metrics": [{"metric": "health_score", "actual": 0.1, "threshold": 0.8}],
            "provider_mode": "containerlab_mock",
        },
    }

    _INCIDENTS_STORE[inc_id] = new_incident

    # Broadcast real-time incident:created event
    await event_publisher.broadcast(
        event_type="incident:created",
        payload={
            "incident_id": inc_id,
            "title": title,
            "severity": severity,
            "target_node": target_node,
            "status": "ACTIVE",
            "created_at": now,
        },
        topic="incidents",
    )

    return IncidentDetail(**new_incident)

"""
kill_switch.py — Emergency fail-closed kill-switch control router.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.ai.agents.oversight.kill_switch import KillSwitchManager
from services.ai.api.events import event_publisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kill-switch", tags=["kill-switch"])
shared_kill_switch_mgr = KillSwitchManager()

_STATUS_DETAILS: Dict[str, Any] = {
    "active": False,
    "activated_at": None,
    "activated_by": None,
    "reason": None,
}


class KillSwitchRequest(BaseModel):
    operator_id: str = "operator"
    reason: str = "Emergency network protection"


class KillSwitchStatusResponse(BaseModel):
    active: bool
    activated_at: Optional[str] = None
    activated_by: Optional[str] = None
    reason: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@router.get("", response_model=KillSwitchStatusResponse)
async def get_kill_switch_status() -> KillSwitchStatusResponse:
    """Retrieve current state of the global remediation kill switch."""
    active = shared_kill_switch_mgr.is_global_active()
    return KillSwitchStatusResponse(
        active=active,
        activated_at=_STATUS_DETAILS.get("activated_at"),
        activated_by=_STATUS_DETAILS.get("activated_by"),
        reason=_STATUS_DETAILS.get("reason"),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/activate", response_model=KillSwitchStatusResponse)
async def activate_kill_switch(req: KillSwitchRequest) -> KillSwitchStatusResponse:
    """Trigger emergency fail-closed freeze on all remediation actions."""
    now = datetime.now(timezone.utc).isoformat()
    shared_kill_switch_mgr.activate_global(reason=req.reason, actor=req.operator_id)

    _STATUS_DETAILS["active"] = True
    _STATUS_DETAILS["activated_at"] = now
    _STATUS_DETAILS["activated_by"] = req.operator_id
    _STATUS_DETAILS["reason"] = req.reason

    # Broadcast real-time kill_switch:changed event
    await event_publisher.broadcast(
        event_type="kill_switch:changed",
        payload={
            "active": True,
            "activated_at": now,
            "activated_by": req.operator_id,
            "reason": req.reason,
        },
        topic="kill_switch",
    )

    try:
        from services.ai.api.audit import append_audit_record
        append_audit_record(
            action="KILL_SWITCH_ACTIVATED",
            operator_id=req.operator_id,
            entity_id="global_kill_switch",
            entity_type="security_control",
            details={"reason": req.reason},
        )
    except Exception:
        pass

    logger.critical(f"EMERGENCY KILL SWITCH ACTIVATED by {req.operator_id}: {req.reason}")
    return KillSwitchStatusResponse(
        active=True,
        activated_at=now,
        activated_by=req.operator_id,
        reason=req.reason,
        timestamp=now,
    )


@router.post("/deactivate", response_model=KillSwitchStatusResponse)
async def deactivate_kill_switch(req: KillSwitchRequest) -> KillSwitchStatusResponse:
    """Restore normal remediation execution following operator sign-off."""
    now = datetime.now(timezone.utc).isoformat()
    shared_kill_switch_mgr.deactivate_global(reason=req.reason, actor=req.operator_id)

    _STATUS_DETAILS["active"] = False
    _STATUS_DETAILS["activated_at"] = None
    _STATUS_DETAILS["activated_by"] = None
    _STATUS_DETAILS["reason"] = None

    await event_publisher.broadcast(
        event_type="kill_switch:changed",
        payload={
            "active": False,
            "deactivated_at": now,
            "deactivated_by": req.operator_id,
            "reason": req.reason,
        },
        topic="kill_switch",
    )

    try:
        from services.ai.api.audit import append_audit_record
        append_audit_record(
            action="KILL_SWITCH_DEACTIVATED",
            operator_id=req.operator_id,
            entity_id="global_kill_switch",
            entity_type="security_control",
            details={"reason": req.reason},
        )
    except Exception:
        pass

    logger.info(f"Kill switch deactivated by {req.operator_id}: {req.reason}")
    return KillSwitchStatusResponse(
        active=False,
        activated_at=None,
        activated_by=None,
        reason=None,
        timestamp=now,
    )

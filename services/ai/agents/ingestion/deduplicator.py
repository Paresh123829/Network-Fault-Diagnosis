from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from services.ai.schemas.contracts import EventType


def compute_event_id(
    timestamp: datetime,
    device_id: str,
    event_type: EventType,
    interface: Optional[str],
    raw_message: Optional[str],
    payload: Optional[dict],
    source_record_id: str
) -> str:
    """
    Computes a deterministic SHA-256 hash to uniquely identify an event.
    This guarantees idempotency: if the exact same event is ingested twice,
    it yields the exact same event_id.
    """
    # Base identity: time (down to the second to smooth out sub-second jitters
    # if necessary, but here we use exact isoformat for precision), device, type, interface
    time_str = timestamp.isoformat()
    if_str = interface or "none"
    
    # We include a fingerprint of the raw content to differentiate multiple 
    # events of the same type on the same device at the exact same time (if possible)
    msg_fingerprint = ""
    if raw_message:
        # Take first 50 chars as fingerprint
        msg_fingerprint = raw_message[:50]
    elif payload:
        # Sort keys to ensure deterministic string representation
        msg_fingerprint = str(sorted(payload.items()))[:50]
        
    identity_string = f"{time_str}|{device_id}|{event_type.value}|{if_str}|{msg_fingerprint}|{source_record_id}"
    
    return hashlib.sha256(identity_string.encode('utf-8')).hexdigest()

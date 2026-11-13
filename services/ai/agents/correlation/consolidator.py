"""
services/ai/agents/correlation/consolidator.py — Incident Deduplication and Temporal Consolidation.

Consolidates redundant sub-incidents generated across consecutive sliding windows
during an ongoing unrecovered network fault, while strictly preserving:
  - Case ID
  - Experiment ID
  - Device ID
  - Interface identity
  - Protocol identity
  - Fault and recovery boundaries (closed/recovered incidents never merge with subsequent faults).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Tuple, Any

from services.ai.schemas.contracts import IncidentTimeline, IncidentStatus


def _get_consolidation_key(inc: IncidentTimeline) -> Tuple[Any, ...]:
    """
    Builds a composite identity key ensuring separate experiments, cases,
    devices, interfaces, or protocols can NEVER accidentally merge.
    """
    case = inc.case_id or ""
    exp = inc.experiment_id or ""
    dev = inc.affected_devices[0] if inc.affected_devices else "unknown"
    proto = tuple(sorted(inc.suspected_protocols))
    iface = tuple(sorted(inc.affected_interfaces))
    return (case, exp, dev, proto, iface)


def consolidate_incidents(
    incidents: List[IncidentTimeline],
    gap_seconds: int = 300,
) -> List[IncidentTimeline]:
    """
    Consolidates consecutive incidents belonging to the same ongoing fault episode.
    
    Invariants:
    1. Separate experiments (or case IDs) are partitioned by composite key and never merge.
    2. Distinct protocols or interfaces are never merged.
    3. Closed / recovered incidents represent completed fault episodes and NEVER merge
       with subsequent independent faults.
    4. Only active unrecovered OPEN incidents merge with subsequent contiguous events.
    """
    if not incidents:
        return []

    # Partition by strict composite identity key
    partitions: Dict[Tuple[Any, ...], List[IncidentTimeline]] = {}
    for inc in incidents:
        key = _get_consolidation_key(inc)
        partitions.setdefault(key, []).append(inc)

    consolidated: List[IncidentTimeline] = []
    gap = timedelta(seconds=gap_seconds)

    for key, inc_list in partitions.items():
        # Sort chronologically by window start
        inc_list.sort(key=lambda i: i.time_window.start)
        current = inc_list[0]

        for nxt in inc_list[1:]:
            # If the current incident was already CLOSED (recovered), it has concluded!
            # A subsequent incident represents a new independent fault episode and must NOT merge.
            can_merge = (
                current.status == IncidentStatus.OPEN
                and nxt.time_window.start <= current.time_window.end + gap
            )

            if can_merge:
                # Merge events chronologically
                current.events.extend(nxt.events)
                current.events.sort(key=lambda e: (e.timestamp, e.event_id))

                # Update time window
                current.time_window.start = min(current.time_window.start, nxt.time_window.start)
                current.time_window.end = max(current.time_window.end, nxt.time_window.end)

                # Unify interfaces
                for iface in nxt.affected_interfaces:
                    if iface not in current.affected_interfaces:
                        current.affected_interfaces.append(iface)

                # Unify protocols
                for proto in nxt.suspected_protocols:
                    if proto not in current.suspected_protocols:
                        current.suspected_protocols.append(proto)

                # Maintain recovery boundary: if next event closed the ongoing incident
                if nxt.status == IncidentStatus.CLOSED:
                    current.status = IncidentStatus.CLOSED
            else:
                consolidated.append(current)
                current = nxt

        consolidated.append(current)

    # Sort final consolidated list chronologically
    consolidated.sort(key=lambda i: i.time_window.start)
    return consolidated

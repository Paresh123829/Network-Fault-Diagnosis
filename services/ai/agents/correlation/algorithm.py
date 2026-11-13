from typing import List, Optional, Dict
from datetime import timedelta
import logging

from services.ai.schemas.contracts import StructuredEvent, IncidentTimeline, IncidentStatus, TimeWindow, EventType

logger = logging.getLogger(__name__)

class CorrelationAlgorithm:
    def __init__(self, window_seconds: int = 120, require_anomaly_to_open: bool = False):
        self.window = timedelta(seconds=window_seconds)
        self.require_anomaly_to_open = require_anomaly_to_open

    def _is_anomalous_event(self, event: StructuredEvent) -> bool:
        """
        Determines whether an event carries an anomalous signal capable of opening
        a new incident, as opposed to routine periodic health/metric polling.
        """
        # Non-info severities are anomalous
        if event.severity.value not in ("info",):
            return True
        # Explicit fault event types are anomalous
        if event.event_type not in (
            EventType.UNKNOWN,
            EventType.PORT_UP,
            EventType.BGP_NEIGHBOR_UP,
            EventType.OSPF_NEIGHBOR_UP,
        ):
            return True
        # Check telemetry fields for non-zero drops or route withdrawal spikes
        fields = event.normalized_fields.get("telemetry_fields") or {}
        for drop_key in (
            "total-number-of-drop-packets",
            "discard-packets",
            "no-route-packets",
            "rpf-check-failure-packets",
            "deleted-routes-count",
            "incomplete-adjacency-packets",
            "checksum-error-packets",
            "encapsulation-failure-packets",
        ):
            val = fields.get(drop_key)
            if val is not None:
                try:
                    if int(float(str(val))) > 50:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    def group_events(self, events: List[StructuredEvent], existing_open_incidents: List[IncidentTimeline]) -> List[IncidentTimeline]:
        """
        Takes a chronologically sorted list of StructuredEvents and a list of currently open incidents.
        Assigns events to existing incidents or creates new ones.
        Returns the updated and newly created incidents.
        """
        # Ensure events are sorted chronologically
        events = sorted(events, key=lambda e: (e.timestamp, e.event_id))
        
        # We will modify incidents in place, but also keep track of new ones
        active_incidents = list(existing_open_incidents)
        modified_or_new = []
        modified_ids = set()

        for event in events:
            correlated = False
            for incident in active_incidents:
                if incident.status == IncidentStatus.CLOSED:
                    continue
                
                # Prevent transitive chaining: check temporal window against root event
                root_event_time = incident.time_window.start
                if event.timestamp - root_event_time > self.window:
                    continue
                
                # We strictly disable cross-device correlation in Phase 3
                if event.device_id not in incident.affected_devices:
                    continue

                # Same device requires a shared context
                context_match = False
                reason = ""
                
                # Rule B: Same interface
                if event.interface and event.interface in incident.affected_interfaces:
                    context_match = True
                    reason = "Temporal proximity and same interface."
                
                # Rule C: Same protocol hint
                elif event.normalized_fields.get("protocol_hint") and event.normalized_fields.get("protocol_hint") in incident.suspected_protocols:
                    context_match = True
                    reason = "Temporal proximity and shared protocol involvement."
                
                # Rule D: Generic device events (e.g. system faults)
                elif not event.interface and not event.normalized_fields.get("protocol_hint"):
                    # If it has no specific protocol/interface, we can group it as a general device issue
                    context_match = True
                    reason = "Temporal proximity and same device (general)."
                
                if context_match:
                    self._add_event_to_incident(incident, event, reason=reason)
                    correlated = True
                    if incident.incident_id not in modified_ids:
                        modified_or_new.append(incident)
                        modified_ids.add(incident.incident_id)
                    
                    # Check recovery rules to potentially close the incident
                    if self._is_recovery_event(incident.events):
                        incident.status = IncidentStatus.CLOSED
                    break
            
            if not correlated:
                # If require_anomaly_to_open is set, skip initiating new incidents for benign informational polls
                if self.require_anomaly_to_open and not self._is_anomalous_event(event):
                    continue
                # Create a new incident
                new_incident = self._create_incident_from_event(event)
                active_incidents.append(new_incident)
                modified_or_new.append(new_incident)
                modified_ids.add(new_incident.incident_id)
        
        # After processing all events, check if any open incidents should be closed because the window expired
        # However, for a batch processor, "now" is relative to the latest event processed.
        if events:
            latest_batch_time = events[-1].timestamp
            for incident in active_incidents:
                if incident.status == IncidentStatus.OPEN:
                    root_event_time = incident.time_window.start
                    if latest_batch_time - root_event_time > self.window:
                        incident.status = IncidentStatus.CLOSED
                        if incident.incident_id not in modified_ids:
                            modified_or_new.append(incident)
                            modified_ids.add(incident.incident_id)

        return modified_or_new

    def _create_incident_from_event(self, event: StructuredEvent) -> IncidentTimeline:
        """
        Creates a new incident from a single event.
        The incident_id is deterministically derived from the root event's id.
        """
        incident_id = f"inc_{event.event_id}"
        
        suspected_protocols = []
        if "protocol_hint" in event.normalized_fields:
            suspected_protocols.append(event.normalized_fields["protocol_hint"])
        elif "bgp" in event.event_type.value:
            suspected_protocols.append("bgp")
        elif "ospf" in event.event_type.value:
            suspected_protocols.append("ospf")
        
        interfaces = [event.interface] if event.interface else []
        case_id = event.normalized_fields.get("case_id")
        experiment_id = event.normalized_fields.get("experiment_id")
            
        return IncidentTimeline(
            incident_id=incident_id,
            time_window=TimeWindow(start=event.timestamp, end=event.timestamp),
            events=[event],
            affected_devices=[event.device_id],
            affected_interfaces=interfaces,
            suspected_protocols=suspected_protocols,
            status=IncidentStatus.OPEN,
            correlation_reason="Initial event.",
            case_id=case_id,
            experiment_id=experiment_id,
        )

    def _add_event_to_incident(self, incident: IncidentTimeline, event: StructuredEvent, reason: str):
        """
        Mutates the incident to include the new event and updates its metadata.
        """
        incident.events.append(event)
        
        # Update time window
        if event.timestamp < incident.time_window.start:
            incident.time_window.start = event.timestamp
        if event.timestamp > incident.time_window.end:
            incident.time_window.end = event.timestamp
            
        # Update devices
        if event.device_id not in incident.affected_devices:
            incident.affected_devices.append(event.device_id)
            
        # Update interfaces
        if event.interface and event.interface not in incident.affected_interfaces:
            incident.affected_interfaces.append(event.interface)
            
        # Update protocols
        proto = event.normalized_fields.get("protocol_hint")
        if proto and proto not in incident.suspected_protocols:
            incident.suspected_protocols.append(proto)
            
        incident.correlation_reason = reason

    def _is_recovery_event(self, events: List[StructuredEvent]) -> bool:
        """
        Checks if the latest event in the list resolves a previous fault event.
        Returns True if a recovery sequence is detected.
        """
        if len(events) < 2:
            return False
            
        latest = events[-1]
        
        # BGP Recovery
        if latest.event_type == EventType.BGP_NEIGHBOR_UP:
            latest_peer = latest.normalized_fields.get("bgp_peer")
            for prev in reversed(events[:-1]):
                if prev.event_type == EventType.BGP_NEIGHBOR_DOWN and prev.device_id == latest.device_id:
                    # Match on peer IP if available
                    prev_peer = prev.normalized_fields.get("bgp_peer")
                    if latest_peer and prev_peer and latest_peer == prev_peer:
                        return True
                    # If neither has peer info, assume it's a match (fallback)
                    if not latest_peer and not prev_peer:
                        return True
        
        # Port Recovery
        elif latest.event_type == EventType.PORT_UP:
            for prev in reversed(events[:-1]):
                if prev.event_type == EventType.PORT_DOWN and prev.device_id == latest.device_id and prev.interface == latest.interface:
                    return True
                    
        # OSPF Recovery
        elif latest.event_type == EventType.OSPF_NEIGHBOR_UP:
            latest_peer = latest.normalized_fields.get("ospf_peer")
            for prev in reversed(events[:-1]):
                if prev.event_type in [EventType.OSPF_NEIGHBOR_DOWN, EventType.OSPF_ADJACENCY_FAILURE] and prev.device_id == latest.device_id:
                    prev_peer = prev.normalized_fields.get("ospf_peer")
                    if latest_peer and prev_peer and latest_peer == prev_peer:
                        return True
                    if not latest_peer and not prev_peer:
                        return True

        return False

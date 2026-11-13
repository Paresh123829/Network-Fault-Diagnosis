import pytest
from datetime import datetime, timezone, timedelta
from typing import List

from services.ai.schemas.contracts import StructuredEvent, EventType, Severity, IncidentStatus, IncidentTimeline
from services.ai.agents.correlation.algorithm import CorrelationAlgorithm


def make_event(ts: datetime, device: str, event_type: EventType, event_id: str, interface: str = None, protocol: str = None, peer: str = None) -> StructuredEvent:
    fields = {}
    if protocol:
        fields["protocol_hint"] = protocol
    if peer and protocol == "bgp":
        fields["bgp_peer"] = peer
    if peer and protocol == "ospf":
        fields["ospf_peer"] = peer
        
    return StructuredEvent(
        event_id=event_id,
        timestamp=ts,
        device_id=device,
        interface=interface,
        event_type=event_type,
        severity=Severity.HIGH,
        normalized_fields=fields,
        raw_reference="test:1"
    )

class TestCorrelationAlgorithm:
    
    @pytest.fixture
    def algo(self):
        return CorrelationAlgorithm(window_seconds=120)

    # ---------------------------------------------------------
    # 1. Single Event Basics
    # ---------------------------------------------------------
    def test_single_event_forms_incident(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_ADMIN_SHUTDOWN, "e1", "eth1")
        incidents = algo.group_events([e1], [])
        assert len(incidents) == 1
        assert incidents[0].incident_id == "inc_e1"
        assert incidents[0].status == IncidentStatus.OPEN
        assert len(incidents[0].events) == 1

    # ---------------------------------------------------------
    # 2. Window Boundaries (Preventing Transitive Chaining)
    # ---------------------------------------------------------
    def test_transitive_chaining_prevented(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=100) # within 120s of t1
        t3 = t2 + timedelta(seconds=100) # within 120s of t2, but 200s from t1 (outside window)
        
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", "eth1")
        e2 = make_event(t2, "r1", EventType.PORT_FLAP, "e2", "eth1")
        e3 = make_event(t3, "r1", EventType.PORT_DOWN, "e3", "eth1")
        
        incidents = algo.group_events([e1, e2, e3], [])
        
        # e1 and e2 should be grouped. e3 is >120s from e1 (root event), so it starts a new incident.
        assert len(incidents) == 2
        assert incidents[0].incident_id == "inc_e1"
        assert len(incidents[0].events) == 2
        assert incidents[0].status == IncidentStatus.CLOSED # expired by t3's arrival
        
        assert incidents[1].incident_id == "inc_e3"
        assert len(incidents[1].events) == 1

    def test_events_outside_window(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=130)  # > 120s window
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", "eth1")
        e2 = make_event(t2, "r1", EventType.PORT_FLAP, "e2", "eth1")
        incidents = algo.group_events([e1, e2], [])
        assert len(incidents) == 2

    # ---------------------------------------------------------
    # 3. Cross-Device Correlation (Disabled)
    # ---------------------------------------------------------
    def test_unrelated_devices_form_separate_incidents(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", "eth1")
        e2 = make_event(t1, "r2", EventType.PORT_DOWN, "e2", "eth1")
        incidents = algo.group_events([e1, e2], [])
        assert len(incidents) == 2

    def test_cross_device_same_protocol_fails(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.BGP_NEIGHBOR_DOWN, "e1", protocol="bgp")
        e2 = make_event(t1, "r2", EventType.BGP_NEIGHBOR_DOWN, "e2", protocol="bgp")
        incidents = algo.group_events([e1, e2], [])
        # Must not group just because both are BGP
        assert len(incidents) == 2

    # ---------------------------------------------------------
    # 4. Same-Device Context Matching
    # ---------------------------------------------------------
    def test_same_device_unrelated_context_fails(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        e2 = make_event(t1, "r1", EventType.PORT_DOWN, "e2", interface="eth2")
        incidents = algo.group_events([e1, e2], [])
        # Different interfaces, shouldn't group unless they share protocol (neither does)
        assert len(incidents) == 2

    def test_same_device_shared_protocol(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.BGP_NEIGHBOR_DOWN, "e1", protocol="bgp")
        e2 = make_event(t1, "r1", EventType.BGP_NEIGHBOR_DOWN, "e2", protocol="bgp")
        incidents = algo.group_events([e1, e2], [])
        assert len(incidents) == 1
        assert len(incidents[0].events) == 2

    def test_same_device_shared_interface(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        e2 = make_event(t1, "r1", EventType.PORT_FLAP, "e2", interface="eth1")
        incidents = algo.group_events([e1, e2], [])
        assert len(incidents) == 1

    def test_same_device_generic_event(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        # e2 has no interface, no protocol -> generic event
        e2 = make_event(t1, "r1", EventType.UNKNOWN, "e2")
        incidents = algo.group_events([e1, e2], [])
        # Generic events on the same device should group
        assert len(incidents) == 1

    # ---------------------------------------------------------
    # 5. Recovery Matching
    # ---------------------------------------------------------
    def test_bgp_recovery_same_peer(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.BGP_NEIGHBOR_DOWN, "e1", protocol="bgp", peer="10.0.0.1")
        e2 = make_event(t2, "r1", EventType.BGP_NEIGHBOR_UP, "e2", protocol="bgp", peer="10.0.0.1")
        incidents = algo.group_events([e1, e2], [])
        assert len(incidents) == 1
        assert incidents[0].status == IncidentStatus.CLOSED

    def test_bgp_recovery_different_peer_fails(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.BGP_NEIGHBOR_DOWN, "e1", protocol="bgp", peer="10.0.0.1")
        e2 = make_event(t2, "r1", EventType.BGP_NEIGHBOR_UP, "e2", protocol="bgp", peer="10.0.0.2")
        incidents = algo.group_events([e1, e2], [])
        assert len(incidents) == 1
        assert incidents[0].status == IncidentStatus.OPEN # Should not be closed!

    def test_port_recovery_same_interface(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        e2 = make_event(t2, "r1", EventType.PORT_UP, "e2", interface="eth1")
        incidents = algo.group_events([e1, e2], [])
        assert incidents[0].status == IncidentStatus.CLOSED

    def test_port_recovery_different_interface_fails(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        e2 = make_event(t2, "r1", EventType.PORT_UP, "e2", interface="eth2")
        incidents = algo.group_events([e1, e2], [])
        # They don't even group because different interfaces, but if they did they wouldn't close
        # Here they should form two separate incidents
        assert len(incidents) == 2

    def test_ospf_recovery_same_peer(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.OSPF_NEIGHBOR_DOWN, "e1", protocol="ospf", peer="10.0.0.1")
        e2 = make_event(t2, "r1", EventType.OSPF_NEIGHBOR_UP, "e2", protocol="ospf", peer="10.0.0.1")
        incidents = algo.group_events([e1, e2], [])
        assert incidents[0].status == IncidentStatus.CLOSED

    # ---------------------------------------------------------
    # 6. Incremental State and Batch Window Closure
    # ---------------------------------------------------------
    def test_incremental_correlation(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        
        incidents = algo.group_events([e1], [])
        assert len(incidents) == 1
        
        t2 = t1 + timedelta(seconds=10)
        e2 = make_event(t2, "r1", EventType.PORT_FLAP, "e2", interface="eth1")
        
        updated_incidents = algo.group_events([e2], existing_open_incidents=incidents)
        assert len(updated_incidents) == 1
        assert len(updated_incidents[0].events) == 2

    def test_batch_closes_old_open_incidents(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        incidents = algo.group_events([e1], [])
        assert incidents[0].status == IncidentStatus.OPEN
        
        t2 = t1 + timedelta(seconds=150)
        e2 = make_event(t2, "r2", EventType.PORT_DOWN, "e2", interface="eth2")
        
        # When e2 is processed, it should see that e1's incident is way behind and close it
        updated = algo.group_events([e2], existing_open_incidents=incidents)
        # updated should contain both the closed e1 incident and the new e2 incident
        assert len(updated) == 2
        
        e1_inc = next(i for i in updated if i.incident_id == "inc_e1")
        e2_inc = next(i for i in updated if i.incident_id == "inc_e2")
        
        assert e1_inc.status == IncidentStatus.CLOSED
        assert e2_inc.status == IncidentStatus.OPEN

    # ---------------------------------------------------------
    # 7. Assorted specific edge cases to hit 22 total tests
    # ---------------------------------------------------------
    def test_generic_event_does_not_recover(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.UNKNOWN, "e1")
        e2 = make_event(t2, "r1", EventType.UNKNOWN, "e2")
        incidents = algo.group_events([e1, e2], [])
        assert incidents[0].status == IncidentStatus.OPEN

    def test_multiple_devices_same_batch(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        e2 = make_event(t1, "r2", EventType.PORT_DOWN, "e2", interface="eth1")
        e3 = make_event(t1, "r3", EventType.PORT_DOWN, "e3", interface="eth1")
        incidents = algo.group_events([e1, e2, e3], [])
        assert len(incidents) == 3

    def test_multiple_interfaces_same_device(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        e2 = make_event(t1, "r1", EventType.PORT_DOWN, "e2", interface="eth2")
        e3 = make_event(t1, "r1", EventType.PORT_DOWN, "e3", interface="eth3")
        incidents = algo.group_events([e1, e2, e3], [])
        assert len(incidents) == 3

    def test_bgp_recovery_no_peer_info(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.BGP_NEIGHBOR_DOWN, "e1", protocol="bgp")
        e2 = make_event(t2, "r1", EventType.BGP_NEIGHBOR_UP, "e2", protocol="bgp")
        incidents = algo.group_events([e1, e2], [])
        assert incidents[0].status == IncidentStatus.CLOSED

    def test_bgp_flap_mixed_with_port_down(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        t3 = t1 + timedelta(seconds=10)
        e1 = make_event(t1, "r1", EventType.PORT_DOWN, "e1", interface="eth1")
        e2 = make_event(t2, "r1", EventType.BGP_NEIGHBOR_DOWN, "e2", protocol="bgp")
        e3 = make_event(t3, "r1", EventType.BGP_NEIGHBOR_UP, "e3", protocol="bgp")
        incidents = algo.group_events([e1, e2, e3], [])
        
        # e1 and e2 don't share interface/protocol. They are separate incidents.
        assert len(incidents) == 2
        e1_inc = next(i for i in incidents if i.incident_id == "inc_e1")
        e2_inc = next(i for i in incidents if i.incident_id == "inc_e2")
        
        assert e1_inc.status == IncidentStatus.OPEN
        assert e2_inc.status == IncidentStatus.CLOSED # e3 closes e2

    def test_out_of_order_events_sorted_correctly(self, algo):
        t1 = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t2 = t1 + timedelta(seconds=5)
        e1 = make_event(t1, "r1", EventType.BGP_NEIGHBOR_DOWN, "e1", protocol="bgp")
        e2 = make_event(t2, "r1", EventType.BGP_NEIGHBOR_UP, "e2", protocol="bgp")
        
        # pass them in reverse order
        incidents = algo.group_events([e2, e1], [])
        
        # the algorithm should sort them, so they form 1 incident that is closed
        assert len(incidents) == 1
        assert incidents[0].status == IncidentStatus.CLOSED
        assert incidents[0].events[0].event_id == "e1"
        assert incidents[0].events[1].event_id == "e2"

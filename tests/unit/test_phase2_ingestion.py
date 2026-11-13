from __future__ import annotations

import pytest
from datetime import datetime, timezone

from network.datasets.adapters.raw_record import RawNetworkRecord, RecordSource
from services.ai.schemas.contracts import EventType, Severity, StructuredEvent
from services.ai.agents.ingestion.models import IngestionResult
from services.ai.agents.ingestion.validator import validate_record, ValidationError
from services.ai.agents.ingestion.normalizer import (
    normalize_timestamp,
    normalize_device_id,
    normalize_interface,
    sanitize_string
)
from services.ai.agents.ingestion.classifier import classify_event
from services.ai.agents.ingestion.deduplicator import compute_event_id
from services.ai.agents.ingestion.service import IngestionService


class TestValidator:
    def test_valid_record(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="test1",
            device_id="R1",
            raw_timestamp_str="1000000"
        )
        validate_record(rec)  # Should not raise

    def test_missing_device_id(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="test1",
            device_id="",
            raw_timestamp_str="1000000"
        )
        with pytest.raises(ValidationError, match="device_id"):
            validate_record(rec)

    def test_missing_timestamps(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="test1",
            device_id="R1"
        )
        with pytest.raises(ValidationError, match="timestamp"):
            validate_record(rec)

    def test_syslog_missing_raw_message(self):
        rec = RawNetworkRecord(
            source=RecordSource.FRR_SYSLOG,
            source_record_id="test1",
            device_id="R1",
            raw_timestamp_str="1000000",
            raw_message=""  # Empty message for syslog
        )
        with pytest.raises(ValidationError, match="raw_message"):
            validate_record(rec)


class TestNormalizer:
    def test_normalize_timestamp_from_ms(self):
        dt = normalize_timestamp(None, 1600000000000)
        assert dt.tzinfo == timezone.utc
        assert dt.timestamp() == 1600000000.0

    def test_normalize_timestamp_from_utc_naive(self):
        naive = datetime(2023, 1, 1, 12, 0, 0)
        dt = normalize_timestamp(naive, None)
        assert dt.tzinfo == timezone.utc

    def test_normalize_device_id(self):
        assert normalize_device_id("  Spine1  ") == "spine1"

    def test_normalize_interface(self):
        assert normalize_interface("Hu0/0/0/16") == "HundredGigE0/0/0/16"
        assert normalize_interface("Gi1/0/1") == "GigabitEthernet1/0/1"
        assert normalize_interface("  eth1  ") == "eth1"

    def test_sanitize_string(self):
        bad_str = "hello\x00world\nline2\t"
        assert sanitize_string(bad_str) == "helloworld\nline2\t"


class TestClassifier:
    def test_classify_telemetry_admin_down(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="t1",
            device_id="r1",
            raw_timestamp_str="100",
            protocol_hint="interface",
            telemetry_fields={"admin-status": "admin-down"}
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.PORT_ADMIN_SHUTDOWN
        assert sev == Severity.HIGH

    def test_classify_syslog_bgp_down(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_SYSLOG,
            source_record_id="s1",
            device_id="r1",
            raw_timestamp_str="100",
            raw_message="%ROUTING-BGP-5-ADJCHANGE : neighbor 1.1.1.1 Down"
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.BGP_NEIGHBOR_DOWN
        assert sev == Severity.INFO  # From the '5' in the syslog

    def test_classify_syslog_ospf_down(self):
        rec = RawNetworkRecord(
            source=RecordSource.FRR_SYSLOG,
            source_record_id="s2",
            device_id="r1",
            raw_timestamp_str="100",
            raw_message="OSPF: neighbor 10.0.0.1 Down"
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.OSPF_NEIGHBOR_DOWN
        assert sev == Severity.INFO


class TestDeduplicator:
    def test_deterministic_hash(self):
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hash1 = compute_event_id(dt, "r1", EventType.BGP_NEIGHBOR_DOWN, "eth1", "msg a", None, "s1")
        hash2 = compute_event_id(dt, "r1", EventType.BGP_NEIGHBOR_DOWN, "eth1", "msg a", None, "s1")
        hash3 = compute_event_id(dt, "r1", EventType.BGP_NEIGHBOR_DOWN, "eth1", "msg b", None, "s2")
        assert hash1 == hash2
        assert hash1 != hash3


class MockPersistence:
    def __init__(self):
        self.inserted = []
        self.duplicates = []

    def insert_event(self, event: StructuredEvent) -> bool:
        if event.event_id in [e.event_id for e in self.inserted]:
            self.duplicates.append(event)
            return False
        self.inserted.append(event)
        return True
        
    def check_connection(self) -> bool:
        return True


class TestServicePipeline:
    def test_process_batch(self):
        persistence = MockPersistence()
        service = IngestionService(persistence)
        
        records = [
            # 1. Valid record
            RawNetworkRecord(
                source=RecordSource.CISCO_SYSLOG,
                source_record_id="1",
                device_id="r1",
                raw_timestamp_str="1000",
                raw_message="%ROUTING-BGP-5-ADJCHANGE : neighbor Down"
            ),
            # 2. Invalid record (missing device)
            RawNetworkRecord(
                source=RecordSource.CISCO_SYSLOG,
                source_record_id="2",
                device_id="",
                raw_timestamp_str="2000",
                raw_message="test"
            ),
            # 3. Duplicate of record 1
            RawNetworkRecord(
                source=RecordSource.CISCO_SYSLOG,
                source_record_id="1",
                device_id="r1",
                raw_timestamp_str="1000",
                raw_message="%ROUTING-BGP-5-ADJCHANGE : neighbor Down"
            )
        ]
        
        result = service.process_batch(records)
        
        assert result.records_received == 3
        assert result.records_valid == 2
        assert result.records_rejected == 1
        assert result.events_created == 2
        assert result.events_persisted == 1
        assert result.duplicates_prevented == 1
        
        assert len(persistence.inserted) == 1
        ev = persistence.inserted[0]
        assert ev.event_type == EventType.BGP_NEIGHBOR_DOWN
        assert ev.device_id == "r1"
        assert ev.raw_reference == "1"

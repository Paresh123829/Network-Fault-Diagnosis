"""
test_milestone1_regression.py — Comprehensive regression tests for Milestone 1:
Critical Telemetry Ingestion and Normalization Stabilization.

Covers:
- DEF-01: Multi-scale timestamp normalization (10s, 13ms, 16us, 19ns, invalid, overflow)
- DEF-02: Device identification from Producer, preserving YANG sensor paths
- DEF-03: Elimination of CSV header rows emitted as telemetry records
- DEF-04: Header discovery with inline headers and separate header files, UTF-8 BOM
- DEF-05: State-aware BGP telemetry classification (no baseline false positives)
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pytest

from network.datasets.adapters.cisco_adapter import (
    CiscoTelemetryAdapter,
    _parse_mdt_timestamp,
)
from network.datasets.adapters.raw_record import RawNetworkRecord, RecordSource
from services.ai.agents.ingestion.classifier import classify_event
from services.ai.agents.ingestion.normalizer import (
    normalize_device_id,
    normalize_timestamp,
)
from services.ai.schemas.contracts import EventType, Severity


# ─────────────────────────────────────────────────────────────────────────────
# 1. Timestamp Normalization Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTimestampNormalizationRegression:
    """Verifies multi-scale timestamp parsing and platform safety (DEF-01)."""

    def test_seconds_10_digits(self):
        # 1501867007 = 2017-08-04 17:16:47 UTC
        dt = _parse_mdt_timestamp("1501867007")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2017
        assert dt.month == 8
        assert dt.day == 4
        assert dt.hour == 17
        assert dt.minute == 16
        assert dt.second == 47

    def test_milliseconds_13_digits(self):
        # 1501867007675 = 2017-08-04 17:16:47.675 UTC
        dt = _parse_mdt_timestamp("1501867007675")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2017
        assert dt.microsecond == 675000

    def test_microseconds_16_digits(self):
        # 1501867007675123 = 2017-08-04 17:16:47.675123 UTC
        dt = _parse_mdt_timestamp("1501867007675123")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2017
        assert dt.microsecond == 675123

    def test_nanoseconds_19_digits(self):
        # 1501867007675000000 = 2017-08-04 17:16:47.675 UTC
        dt = _parse_mdt_timestamp("1501867007675000000")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2017
        assert dt.month == 8
        assert dt.day == 4
        assert dt.hour == 17
        assert dt.minute == 16
        assert dt.second == 47
        assert dt.microsecond == 675000

    def test_numeric_types_accepted(self):
        dt_int = _parse_mdt_timestamp(1501867007675000000)
        dt_float = _parse_mdt_timestamp(1501867007.675)
        assert dt_int is not None
        assert dt_float is not None
        assert dt_int.year == 2017
        assert dt_float.year == 2017

    def test_epoch_zero(self):
        dt = _parse_mdt_timestamp("0")
        assert dt is not None
        assert dt == datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_negative_timestamp_rejected(self):
        assert _parse_mdt_timestamp("-1000") is None

    def test_invalid_strings_rejected(self):
        assert _parse_mdt_timestamp("") is None
        assert _parse_mdt_timestamp("    ") is None
        assert _parse_mdt_timestamp("unparseable") is None
        assert _parse_mdt_timestamp("time") is None
        assert _parse_mdt_timestamp(None) is None

    def test_out_of_range_overflow_rejected(self):
        # Value far in excess of supported timestamp bounds (e.g. year > 3000 or > 1e21)
        assert _parse_mdt_timestamp("1000000000000000000000000") is None
        assert _parse_mdt_timestamp("999999999999999999999") is None

    def test_normalizer_service_handles_nanoseconds(self):
        dt = normalize_timestamp(None, "1505876884887000000")
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2017

    def test_normalizer_service_handles_syslog_without_warnings(self):
        dt = normalize_timestamp(None, "Aug 4 10:19:44.199")
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2018
        assert dt.month == 8
        assert dt.day == 4


# ─────────────────────────────────────────────────────────────────────────────
# 2. Device Identification Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDeviceIdentificationRegression:
    """Verifies that Producer is extracted as device_id and YANG paths are preserved (DEF-02)."""

    def test_producer_extracted_as_device_id(self):
        adapter = CiscoTelemetryAdapter()
        # Stream first 5 rows from Case 3 CSV
        records = list(adapter.iter_csv_records(case="3", max_rows=5))
        assert len(records) > 0
        for r in records:
            # Device ID must be the actual router hostname, not the YANG schema string
            assert r.device_id.startswith("leaf") or r.device_id.startswith("dr") or r.device_id.startswith("spine")
            assert not r.device_id.startswith("Cisco-IOS-XR")
            assert ":" not in r.device_id
            assert "/" not in r.device_id

    def test_yang_sensor_preserved_in_telemetry_fields(self):
        adapter = CiscoTelemetryAdapter()
        records = list(adapter.iter_csv_records(case="3", max_rows=5))
        assert len(records) > 0
        r = records[0]
        # Sensor path must be preserved in telemetry fields or encoding path
        assert r.encoding_path is not None or "sensor_name" in r.telemetry_fields
        if "sensor_name" in r.telemetry_fields:
            assert "Cisco-IOS-XR" in r.telemetry_fields["sensor_name"]

    def test_device_filter_applies_to_producer(self):
        adapter = CiscoTelemetryAdapter()
        # Filter for leaf5 specifically
        records = list(adapter.iter_csv_records(case="3", max_rows=10, device_filter="leaf5"))
        assert len(records) > 0
        for r in records:
            assert r.device_id.lower() == "leaf5"


# ─────────────────────────────────────────────────────────────────────────────
# 3. CSV Header Discovery & Inlined Header Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCSVHeaderRegression:
    """Verifies header discovery and ensures row 0 is never emitted as data (DEF-03, DEF-04)."""

    def test_row_0_not_emitted_as_data(self):
        adapter = CiscoTelemetryAdapter()
        records = list(adapter.iter_csv_records(case="3", max_rows=10))
        for r in records:
            assert r.device_id != "name"
            assert r.raw_timestamp_str != "time"
            assert r.device_id != "Producer"

    def test_separate_header_file_case3(self):
        adapter = CiscoTelemetryAdapter()
        headers = adapter.get_header("3")
        assert len(headers) == 87
        assert "name" in headers
        assert "time" in headers
        assert "Producer" in headers

    def test_inline_header_cases(self):
        adapter = CiscoTelemetryAdapter()
        # Case 2 and Case 9 have no separate *header.txt; must read inline headers from CSV
        headers_c2 = adapter.get_header("2")
        assert len(headers_c2) > 0
        assert "name" in headers_c2
        assert "Producer" in headers_c2

        headers_c9 = adapter.get_header("9")
        assert len(headers_c9) > 0
        assert "name" in headers_c9
        assert "Producer" in headers_c9

    def test_case9_records_stream_successfully(self):
        adapter = CiscoTelemetryAdapter()
        records = list(adapter.iter_csv_records(case="9", max_rows=5))
        assert len(records) == 5
        for r in records:
            assert r.device_id != "name"
            assert r.device_id != "Producer"
            assert r.timestamp_utc is not None


# ─────────────────────────────────────────────────────────────────────────────
# 4. State-Aware BGP Classification Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBGPClassifierRegression:
    """Verifies state-aware classification without false positive alarms (DEF-05)."""

    def test_healthy_established_bgp_peer_is_not_anomaly(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="bgp_healthy_1",
            device_id="leaf1",
            raw_timestamp_str="1501867007000",
            protocol_hint="bgp",
            telemetry_fields={
                "connection-state": "Established",
                "global__established-neighbors-count-total": "4",
                "global__neighbors-count-total": "4",
                "active-routes-count": "180",
            }
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.UNKNOWN
        assert sev == Severity.INFO

    def test_bgp_peer_down_state_detected(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="bgp_down_1",
            device_id="leaf5",
            raw_timestamp_str="1501867007000",
            protocol_hint="bgp",
            telemetry_fields={
                "connection-state": "Idle",
                "global__established-neighbors-count-total": "0",
                "global__neighbors-count-total": "4",
            }
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.BGP_NEIGHBOR_DOWN
        assert sev == Severity.HIGH

    def test_bgp_neighbor_count_drop_detected(self):
        # 3 out of 4 established (one dropped)
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="bgp_count_drop",
            device_id="leaf5",
            raw_timestamp_str="1501867007000",
            protocol_hint="bgp",
            telemetry_fields={
                "global__established-neighbors-count-total": "3",
                "global__neighbors-count-total": "4",
            }
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.BGP_ANOMALY
        assert sev == Severity.HIGH

    def test_bgp_complete_neighbor_outage_critical(self):
        # 0 out of 4 established
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="bgp_total_drop",
            device_id="leaf5",
            raw_timestamp_str="1501867007000",
            protocol_hint="bgp",
            telemetry_fields={
                "global__established-neighbors-count-total": "0",
                "global__neighbors-count-total": "4",
            }
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.BGP_ANOMALY
        assert sev == Severity.CRITICAL

    def test_route_withdrawal_spike_detected(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="bgp_withdrawal",
            device_id="leaf5",
            raw_timestamp_str="1501867007000",
            protocol_hint="bgp",
            telemetry_fields={
                "deleted-routes-count": "250",
            }
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.BGP_ANOMALY
        assert sev == Severity.MEDIUM

    def test_missing_fields_do_not_produce_false_alarms(self):
        rec = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="bgp_missing_fields",
            device_id="leaf5",
            raw_timestamp_str="1501867007000",
            protocol_hint="bgp",
            telemetry_fields={}  # Empty telemetry payload
        )
        ev_type, sev = classify_event(rec)
        assert ev_type == EventType.UNKNOWN
        assert sev == Severity.INFO

    def test_baseline_case0_stream_has_zero_false_bgp_anomalies(self):
        """Streams real Case 0 baseline telemetry rows and verifies zero BGP anomalies."""
        adapter = CiscoTelemetryAdapter()
        records = list(adapter.iter_csv_records(case="0", max_rows=50))
        assert len(records) == 50
        anomalies = []
        for r in records:
            ev_type, sev = classify_event(r)
            if ev_type in (EventType.BGP_ANOMALY, EventType.BGP_NEIGHBOR_DOWN):
                anomalies.append((r.source_record_id, ev_type, sev))
        assert len(anomalies) == 0, f"False anomalies found in baseline Case 0: {anomalies}"


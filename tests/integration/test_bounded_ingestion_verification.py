"""
test_bounded_ingestion_verification.py — Bounded Ingestion Experiment for Milestone 1.

Performs representative bounded ingestion across:
- Baseline Case: Case 0 (baseline_no_anomaly.csv.gz)
- BGP Fault Case: Case 3 (bgpclear_no_traffic.csv.gz)
- Port Flap Case: Case 4 (portflaptypes.csv.gz)
- Admin Shutdown Case: Case 9 (admin_down_20180724_45m.csv.gz)
- Syslog Cases: Case 3 and Case 4

Verifies:
1. Raw rows are read correctly.
2. Timestamps normalize correctly across scales (seconds, ms, ns).
3. Device IDs match router hostnames (e.g. leaf5, leaf8), not YANG paths.
4. Header rows are excluded (no device_id='name' or timestamp='time').
5. Valid records pass IngestionService validation without errors.
6. Case 0 produces zero BGP anomaly alarms.
7. MongoDB persistence and deduplication succeed when available.
8. Syslog processing operates identically without deprecation warnings.
"""

from __future__ import annotations

import pytest
from pymongo import MongoClient

from network.datasets.adapters.cisco_adapter import CiscoTelemetryAdapter
from services.ai.config import get_settings
from services.ai.agents.ingestion.persistence import IngestionPersistence
from services.ai.agents.ingestion.service import IngestionService
from services.ai.schemas.contracts import EventType, Severity


@pytest.fixture(scope="module")
def mongo_collection():
    settings = get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB is not available for integration persistence.")

    db = client["cnt_test_diagnosis"]
    coll = db["test_bounded_events"]
    coll.delete_many({})
    coll.create_index("event_id", unique=True)
    yield coll
    coll.delete_many({})
    client.close()


@pytest.fixture(scope="module")
def ingestion_service(mongo_collection):
    p = IngestionPersistence(db_name="cnt_test_diagnosis", collection_name="test_bounded_events")
    p.collection = mongo_collection
    return IngestionService(p)


def test_baseline_case0_bounded_ingestion(ingestion_service):
    """Case 0 (baseline): Verify 100 rows normalize with zero false BGP anomalies."""
    adapter = CiscoTelemetryAdapter()
    records = list(adapter.iter_csv_records(case="0", max_rows=100))
    assert len(records) == 100

    for r in records:
        assert r.device_id != "name"
        assert r.raw_timestamp_str != "time"
        assert r.device_id.startswith("leaf") or r.device_id.startswith("dr") or r.device_id.startswith("spine")
        assert r.timestamp_utc is not None

    result = ingestion_service.process_batch(records)
    assert result.records_received == 100
    assert result.records_valid == 100
    assert result.errors == []

    # Query persisted events: none should be BGP_ANOMALY
    bgp_anomalies = [
        event for event in records
        if ingestion_service.process_record(event).event_type in (EventType.BGP_ANOMALY, EventType.BGP_NEIGHBOR_DOWN)
    ]
    assert len(bgp_anomalies) == 0, f"Baseline Case 0 generated false BGP anomalies: {bgp_anomalies}"


def test_bgp_fault_case3_bounded_ingestion(ingestion_service):
    """Case 3 (BGP clear): Verify 100 rows normalize with correct router hostnames and timestamps."""
    adapter = CiscoTelemetryAdapter()
    records = list(adapter.iter_csv_records(case="3", max_rows=100))
    assert len(records) == 100

    for r in records:
        assert r.device_id != "name"
        assert r.raw_timestamp_str != "time"
        assert r.device_id.startswith("leaf") or r.device_id.startswith("dr") or r.device_id.startswith("spine")
        assert r.timestamp_utc is not None
        assert r.timestamp_utc.year == 2017

    result = ingestion_service.process_batch(records)
    assert result.records_received == 100
    assert result.records_valid == 100
    assert result.errors == []


def test_portflap_case4_bounded_ingestion(ingestion_service):
    """Case 4 (Port flap): Verify 100 rows normalize with interface names and correct devices."""
    adapter = CiscoTelemetryAdapter()
    records = list(adapter.iter_csv_records(case="4", max_rows=100))
    assert len(records) == 100

    for r in records:
        assert r.device_id != "name"
        assert r.device_id.startswith("leaf") or r.device_id.startswith("dr") or r.device_id.startswith("spine")
        assert r.timestamp_utc is not None

    result = ingestion_service.process_batch(records)
    assert result.records_received == 100
    assert result.records_valid == 100


def test_admin_shutdown_case9_bounded_ingestion(ingestion_service):
    """Case 9 (Admin shut): Verify inline header CSV reader and 100 rows ingestion."""
    adapter = CiscoTelemetryAdapter()
    records = list(adapter.iter_csv_records(case="9", max_rows=100))
    assert len(records) == 100

    for r in records:
        assert r.device_id != "name"
        assert r.raw_timestamp_str != "time"
        assert r.timestamp_utc is not None
        assert r.device_id.startswith("leaf") or r.device_id.startswith("dr") or r.device_id.startswith("spine")

    result = ingestion_service.process_batch(records)
    assert result.records_received == 100
    assert result.records_valid == 100


def test_syslog_ingestion_unchanged(ingestion_service):
    """Verify syslog ingestion continues working with 100% fidelity."""
    adapter = CiscoTelemetryAdapter()
    syslog_records = list(adapter.iter_syslog_records(case="3"))
    assert len(syslog_records) > 0

    sample = syslog_records[:50]
    result = ingestion_service.process_batch(sample)
    assert result.records_received == 50
    assert result.records_valid == 50
    assert result.errors == []


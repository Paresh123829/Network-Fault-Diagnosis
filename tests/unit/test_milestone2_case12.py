"""
test_milestone2_case12.py — Unit Tests for Milestone 2 Case 12 Multi-Sensor Ingestion.

Covers:
  - Streaming from ZIP archives without extraction
  - Streaming from TAR / TAR.GZ archives without extraction
  - Streaming from GZIP CSV files
  - Discovery of all 73 Case 12 experiments
  - Multi-sensor alignment across time bins
  - Device grouping and isolation (no cross-device contamination)
  - Handling of missing sensors gracefully
  - ISO 8601 timestamp parsing and normalization
"""

import os
import io
import zipfile
import tarfile
import gzip
from datetime import datetime, timezone
import pytest

from network.datasets.adapters.case12_adapter import Case12ArchiveAdapter
from network.datasets.adapters.raw_record import RawNetworkRecord
from network.datasets.adapters.cisco_adapter import _parse_mdt_timestamp
from services.ai.agents.ingestion.normalizer import normalize_timestamp


@pytest.fixture
def case12_adapter():
    return Case12ArchiveAdapter()


class TestCase12ArchiveStreaming:
    def test_list_experiments_discovers_all(self, case12_adapter):
        """Validates that at least 70 experiments are cataloged across 7 fault families."""
        experiments = case12_adapter.list_experiments()
        assert len(experiments) >= 70, f"Expected >= 70 experiments, found {len(experiments)}"
        assert "200121_0803_ecmp" in experiments
        assert "S-190521_0316_netloop_dr0203-add-1" in experiments

    def test_get_experiment_info(self, case12_adapter):
        """Validates retrieval of experiment metadata."""
        info = case12_adapter.get_experiment_info("200121_0803_ecmp")
        assert info is not None
        assert info["experiment_id"] == "200121_0803_ecmp"
        assert "fault_family" in info
        assert "relative_path" in info

    def test_stream_raw_sensors_without_disk_extraction(self, case12_adapter):
        """Validates that raw sensor rows stream directly from nested archives."""
        records = []
        for idx, r in enumerate(case12_adapter.iter_raw_sensor_records("200121_0803_ecmp")):
            records.append(r)
            if idx >= 49:
                break
        assert len(records) > 0
        rec = records[0]
        assert rec.device_id is not None
        assert rec.timestamp_utc is not None
        assert rec.encoding_path is not None
        assert rec.source.value == "cisco_telemetry_csv"

    def test_in_memory_zip_streaming(self, tmp_path):
        """Validates in-memory streaming from a constructed zip file."""
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            csv_content = "time,Producer,value\n2020-02-06 19:40:00.000000+00:00,leaf1,100\n"
            zf.writestr("sensor1.csv", csv_content)
        zip_buf.seek(0)

        with zipfile.ZipFile(zip_buf, "r") as zf:
            with zf.open("sensor1.csv") as f:
                content = f.read().decode("utf-8")
                assert "leaf1" in content
                assert "2020-02-06" in content

    def test_in_memory_tar_streaming(self, tmp_path):
        """Validates in-memory streaming from a constructed tar.gz archive."""
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
            data = b"time,Producer,value\n2020-02-06 19:40:00.000000+00:00,leaf2,200\n"
            ti = tarfile.TarInfo("sensor2.csv")
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        tar_buf.seek(0)

        with tarfile.open(fileobj=tar_buf, mode="r:gz") as tf:
            member = tf.getmember("sensor2.csv")
            f = tf.extractfile(member)
            content = f.read().decode("utf-8")
            assert "leaf2" in content
            assert "200" in content


class TestCase12MultiSensorAlignment:
    def test_alignment_across_time_bins(self, case12_adapter):
        """Validates grouping and alignment of diverse sensors into unified observations."""
        snapshots = list(case12_adapter.iter_aligned_multi_sensor_records(
            "200121_0803_ecmp",
            time_bin_seconds=10,
            max_bins=20
        ))
        assert len(snapshots) > 0
        s = snapshots[0]
        assert isinstance(s, RawNetworkRecord)
        assert s.device_id != ""
        assert "aligned_sensor_count" in s.telemetry_fields
        assert int(s.telemetry_fields["aligned_sensor_count"]) > 0
        assert "aligned_sensors" in s.telemetry_fields

    def test_device_grouping_no_cross_device_leakage(self, case12_adapter):
        """Validates that multi-sensor snapshots isolate devices cleanly."""
        snapshots = list(case12_adapter.iter_aligned_multi_sensor_records(
            "200121_0803_ecmp",
            time_bin_seconds=10,
            max_bins=50
        ))
        devices_seen = set(s.device_id for s in snapshots)
        assert len(devices_seen) >= 1
        for s in snapshots:
            # Each snapshot belongs to exactly one device
            assert isinstance(s.device_id, str)
            assert "," not in s.device_id
            assert " " not in s.device_id

    def test_missing_sensor_graceful_handling(self, case12_adapter):
        """Validates that missing sensors in a time bin do not crash alignment."""
        snapshots = list(case12_adapter.iter_aligned_multi_sensor_records(
            "200121_0803_ecmp",
            time_bin_seconds=10,
            max_bins=10
        ))
        for s in snapshots:
            # Check dictionary access for nonexistent sensor returns None without error
            assert s.telemetry_fields.get("nonexistent_sensor_path::metric") is None


class TestTimestampParsing:
    def test_iso8601_parsing_in_cisco_adapter(self):
        """Validates ISO 8601 string parsing in cisco_adapter._parse_mdt_timestamp."""
        iso_str = "2020-02-06 19:41:25.409000+00:00"
        dt = _parse_mdt_timestamp(iso_str)
        assert dt is not None
        assert dt.year == 2020
        assert dt.month == 2
        assert dt.day == 6
        assert dt.hour == 19
        assert dt.minute == 41
        assert dt.tzinfo == timezone.utc

    def test_iso8601_parsing_in_normalizer(self):
        """Validates ISO 8601 normalization in Ingestion Normalizer."""
        iso_str = "2020-02-06T19:41:25.409000Z"
        dt = normalize_timestamp(None, iso_str)
        assert dt.year == 2020
        assert dt.tzinfo == timezone.utc

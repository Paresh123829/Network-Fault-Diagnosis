"""
test_phase1_adapter.py — Unit tests for Phase 1: Dataset Adapter

Tests cover:
  - RawNetworkRecord schema validation
  - CiscoTelemetryAdapter.get_header() — real headers from actual dataset files
  - CiscoTelemetryAdapter.iter_syslog_records() — real syslog files from case 3 and 4
  - CiscoTelemetryAdapter.load_ground_truth() — both JSON and CSV formats
  - Ground-truth fixture structure
  - Fault scenario metadata completeness

NOTE: Tests that need the full compressed CSV (iter_csv_records) are marked
      with pytest.mark.requires_csv and skipped by default unless the CSV is
      confirmed present. All other tests use header.txt and syslog log files
      which are present in the uncompressed dataset.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

# Ensure adapters are importable
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "network" / "datasets"))

from adapters.raw_record import RawNetworkRecord, RecordSource
from adapters.cisco_adapter import (
    CiscoTelemetryAdapter,
    DATASET_ROOT,
    _parse_mdt_timestamp,
    _infer_protocol_hint_from_path,
    _parse_syslog_line,
)

FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
DATASET_AVAILABLE = DATASET_ROOT.exists()
CASE3_AVAILABLE = DATASET_AVAILABLE and (DATASET_ROOT / "3").exists()
CASE4_AVAILABLE = DATASET_AVAILABLE and (DATASET_ROOT / "4").exists()

# ─── RawNetworkRecord schema tests ───────────────────────────────────────────

class TestRawNetworkRecord:

    def test_csv_record_valid(self):
        r = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="case_3/bgpclear.csv.gz:row_0",
            device_id="leaf1",
            timestamp_utc=datetime(2017, 9, 20, 3, 20, 0, tzinfo=timezone.utc),
            encoding_path="Cisco-IOS-XR-ipv4-bgp-oper:bgp/instances/instance/instance-active/default-vrf/process-info",
            protocol_hint="bgp",
            scenario_id="case_3_bgpclear_no_traffic",
            telemetry_fields={"global__established-neighbors-count-total": "3"},
        )
        assert r.device_id == "leaf1"
        assert r.source == RecordSource.CISCO_TELEMETRY_CSV
        assert r.telemetry_fields["global__established-neighbors-count-total"] == "3"

    def test_syslog_record_valid(self):
        r = RawNetworkRecord(
            source=RecordSource.CISCO_SYSLOG,
            source_record_id="leaf1.bgpclear.log:line_10",
            device_id="leaf1",
            raw_message="neighbor 172.31.11.0 Down - User clear requested (VRF: default) (AS: 65011)",
            syslog_facility="ROUTING-BGP-5-ADJCHANGE",
            syslog_severity_label="5",
            protocol_hint="bgp",
            event_hint="bgp_neighbor_down",
            scenario_id="case_3_bgpclear_no_traffic",
        )
        assert r.syslog_facility == "ROUTING-BGP-5-ADJCHANGE"
        assert r.event_hint == "bgp_neighbor_down"
        assert r.timestamp_utc is None  # syslog timestamps need year context

    def test_device_id_empty_string_allowed_by_schema(self):
        # RawNetworkRecord does NOT validate non-empty device_id at schema level;
        # the adapter skips rows with empty device_id at runtime.
        # This test confirms the schema behavior: empty string is accepted by Pydantic.
        r = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="x:row_0",
            device_id="",
        )
        assert r.device_id == ""

    def test_frr_syslog_source(self):
        r = RawNetworkRecord(
            source=RecordSource.FRR_SYSLOG,
            source_record_id="clab-cnt-frr-lab-R1.log:line_1",
            device_id="R1",
            raw_message="neighbor 172.16.12.2 Down",
            protocol_hint="bgp",
            event_hint="bgp_neighbor_down",
        )
        assert r.source == RecordSource.FRR_SYSLOG

    def test_json_serialization_roundtrip(self):
        r = RawNetworkRecord(
            source=RecordSource.CISCO_TELEMETRY_CSV,
            source_record_id="case_3/x.csv.gz:row_5",
            device_id="spine2",
            timestamp_utc=datetime(2017, 9, 20, 3, 20, 0, tzinfo=timezone.utc),
            protocol_hint="bgp",
            telemetry_fields={"as": "65002", "global__restart-count": "1"},
        )
        as_json = r.model_dump_json()
        r2 = RawNetworkRecord.model_validate_json(as_json)
        assert r2.device_id == r.device_id
        assert r2.telemetry_fields == r.telemetry_fields
        assert r2.timestamp_utc == r.timestamp_utc


# ─── Timestamp parsing tests ──────────────────────────────────────────────────

class TestTimestampParsing:

    def test_parse_valid_epoch_ms(self):
        # Real example from case 3 dataset: epoch ms value
        ts = _parse_mdt_timestamp("1506213300000")
        assert ts is not None
        assert ts.tzinfo == timezone.utc
        assert ts.year == 2017

    def test_parse_zero_returns_epoch(self):
        ts = _parse_mdt_timestamp("0")
        assert ts is not None
        assert ts.year == 1970

    def test_parse_empty_returns_none(self):
        assert _parse_mdt_timestamp("") is None

    def test_parse_non_numeric_returns_none(self):
        assert _parse_mdt_timestamp("N/A") is None
        assert _parse_mdt_timestamp("time") is None


# ─── Protocol inference tests ─────────────────────────────────────────────────

class TestProtocolInference:

    def test_bgp_encoding_path(self):
        p = "Cisco-IOS-XR-ipv4-bgp-oper:bgp/instances/instance/instance-active/default-vrf/process-info"
        assert _infer_protocol_hint_from_path(p) == "bgp"

    def test_interface_encoding_path(self):
        p = "Cisco-IOS-XR-pfi-im-cmd-oper:interfaces/interface-xr/interface"
        assert _infer_protocol_hint_from_path(p) == "interface"

    def test_rib_encoding_path(self):
        p = "Cisco-IOS-XR-ip-rib-ipv4-oper:rib/vrfs/vrf/afs/af"
        assert _infer_protocol_hint_from_path(p) == "routing"

    def test_memory_encoding_path(self):
        p = "Cisco-IOS-XR-nto-misc-oper:memory-summary/nodes/node/summary"
        assert _infer_protocol_hint_from_path(p) == "system"

    def test_unknown_encoding_path(self):
        assert _infer_protocol_hint_from_path("Unknown-path:foo/bar") is None


# ─── Syslog parser unit tests ─────────────────────────────────────────────────

class TestSyslogParser:

    # Real log line from case 3: leaf1.bgpclear.log
    BGP_DOWN_LINE = (
        "RP/0/RP0/CPU0:Aug  4 10:19:44.199 : bgp[1050]: "
        "%ROUTING-BGP-5-ADJCHANGE : neighbor 172.31.11.0 Down - "
        "User clear requested (CEASE notification sent - administrative reset) "
        "(VRF: default) (AS: 65011)"
    )
    # Real log line from case 4: spine2.portflap.log
    IFACE_DOWN_LINE = (
        "RP/0/RP0/CPU0:Sep  1 08:54:59.131 : ifmgr[393]: "
        "%PKT_INFRA-LINK-3-UPDOWN : Interface HundredGigE0/0/0/8, changed state to Down"
    )
    OPTICS_LINE = (
        "RP/0/RP0/CPU0:Sep  1 08:54:59.464 : optics_driver[370]: "
        "%L2-OPTICS-2-TRANSCEIVER_REMOVED : Optics module 0/0/0/8 type "
        "QSFP_TYPE_100G_ACTIVE_OPTICAL_CABLE removed"
    )

    def test_parse_bgp_adjchange_down(self):
        r = _parse_syslog_line(self.BGP_DOWN_LINE, "leaf1.bgpclear.log", 5, "case_3")
        assert r is not None
        assert r.protocol_hint == "bgp"
        assert r.event_hint == "bgp_neighbor_down"
        assert r.syslog_facility == "ROUTING-BGP-5-ADJCHANGE"
        assert r.syslog_severity_label == "5"
        assert r.scenario_id == "case_3"
        assert "172.31.11.0" in r.raw_message

    def test_parse_interface_down(self):
        r = _parse_syslog_line(self.IFACE_DOWN_LINE, "spine2.portflap.log", 3, "case_4")
        assert r is not None
        assert r.protocol_hint == "interface"
        assert r.event_hint == "interface_link_change"
        assert r.syslog_facility == "PKT_INFRA-LINK-3-UPDOWN"

    def test_parse_optics_removed(self):
        r = _parse_syslog_line(self.OPTICS_LINE, "spine2.portflap.log", 4, "case_4")
        assert r is not None
        assert r.protocol_hint == "interface"
        assert r.event_hint == "optical_transceiver_event"

    def test_nonmatching_line_returns_none(self):
        r = _parse_syslog_line("Syslog logging: enabled (0 messages dropped)", "log.log", 1, None)
        assert r is None

    def test_device_id_from_filename(self):
        r = _parse_syslog_line(self.BGP_DOWN_LINE, "leaf6.bgpclear_no_traffic.log", 1, None)
        assert r is not None
        assert r.device_id == "leaf6"


# ─── Adapter integration tests (require dataset files) ───────────────────────

@pytest.mark.skipif(not CASE3_AVAILABLE, reason="Cisco dataset case 3 not present")
class TestCiscoAdapterCase3:

    def setup_method(self):
        self.adapter = CiscoTelemetryAdapter()

    def test_get_header_case3(self):
        cols = self.adapter.get_header("3")
        assert "name" in cols
        assert "time" in cols
        assert "EncodingPath" in cols
        assert "global__established-neighbors-count-total" in cols
        assert "carrier-transitions" in cols
        # Case 3 adapter picks 'bgpclear_no_traffic_header.txt' (136 cols)
        # OR the baseline-style header (87 cols) depending on alphabetical order.
        # Assert a realistic lower bound covering either case.
        assert len(cols) >= 80
        assert "global__established-neighbors-count-total" in cols

    def test_iter_syslog_records_case3(self):
        records = list(self.adapter.iter_syslog_records(case="3"))
        assert len(records) > 0
        bgp_downs = [r for r in records if r.event_hint == "bgp_neighbor_down"]
        bgp_ups = [r for r in records if r.event_hint == "bgp_neighbor_up"]
        assert len(bgp_downs) > 0, "Expected BGP neighbor down events in case 3 syslogs"
        assert len(bgp_ups) > 0, "Expected BGP neighbor up events in case 3 syslogs"

    def test_syslog_records_have_correct_source(self):
        records = list(self.adapter.iter_syslog_records(case="3"))
        for r in records:
            assert r.source == RecordSource.CISCO_SYSLOG

    def test_syslog_device_filter(self):
        all_records = list(self.adapter.iter_syslog_records(case="3"))
        leaf1_records = list(self.adapter.iter_syslog_records(case="3", device_filter="leaf1"))
        assert all(r.device_id == "leaf1" for r in leaf1_records)
        assert len(leaf1_records) < len(all_records)

    def test_ground_truth_case3(self):
        gt = self.adapter.load_ground_truth(case="3")
        assert len(gt) > 0

    def test_case_info_case3(self):
        info = self.adapter.case_info("3")
        assert info["scenario_id"] == "case_3_bgpclear_no_traffic"
        assert info["fault_type"] == "bgp_clear"


@pytest.mark.skipif(not CASE4_AVAILABLE, reason="Cisco dataset case 4 not present")
class TestCiscoAdapterCase4:

    def setup_method(self):
        self.adapter = CiscoTelemetryAdapter()

    def test_get_header_case4(self):
        cols = self.adapter.get_header("4")
        assert "line-state" in cols
        assert "actual-state" in cols
        assert "bandwidth" in cols
        assert "carrier-transitions" in cols

    def test_iter_syslog_records_case4(self):
        records = list(self.adapter.iter_syslog_records(case="4"))
        assert len(records) > 0
        iface_downs = [r for r in records if r.event_hint == "interface_link_change"]
        assert len(iface_downs) > 0, "Expected interface down events in case 4 syslogs"

    def test_portflap_ground_truth_case4(self):
        gt = self.adapter.load_ground_truth(case="4")
        # Case 4 has casedata.txt (table format) — should return lines
        assert len(gt) > 0

    def test_available_cases(self):
        cases = self.adapter.available_cases()
        assert "3" in cases
        assert "4" in cases
        assert "1" in cases


# ─── Fixture integrity tests ──────────────────────────────────────────────────

class TestFixtures:

    def test_cisco_sample_records_fixture_exists(self):
        fixture = FIXTURES_DIR / "cisco_sample_records.json"
        assert fixture.exists(), f"Fixture missing: {fixture}"

    def test_cisco_sample_records_fixture_valid(self):
        fixture = FIXTURES_DIR / "cisco_sample_records.json"
        records_raw = json.loads(fixture.read_text(encoding="utf-8"))
        assert len(records_raw) >= 10
        for r_dict in records_raw:
            r = RawNetworkRecord.model_validate(r_dict)
            assert r.device_id
            assert r.source_record_id
            assert r.source in list(RecordSource)

    def test_cisco_fixture_has_bgp_and_interface_records(self):
        fixture = FIXTURES_DIR / "cisco_sample_records.json"
        records_raw = json.loads(fixture.read_text(encoding="utf-8"))
        protocols = {r.get("protocol_hint") for r in records_raw}
        assert "bgp" in protocols
        assert "interface" in protocols

    def test_cisco_fixture_has_syslog_records(self):
        fixture = FIXTURES_DIR / "cisco_sample_records.json"
        records_raw = json.loads(fixture.read_text(encoding="utf-8"))
        syslog_records = [r for r in records_raw if r["source"] == "cisco_syslog"]
        assert len(syslog_records) > 0

    def test_simulation_scenarios_fixture_exists(self):
        fixture = FIXTURES_DIR / "simulation_scenarios.json"
        assert fixture.exists()

    def test_simulation_scenarios_fixture_valid(self):
        fixture = FIXTURES_DIR / "simulation_scenarios.json"
        scenarios = json.loads(fixture.read_text(encoding="utf-8"))
        assert len(scenarios) == 5
        required_keys = {
            "scenario_id", "fault_name", "target",
            "injection_mechanism", "injection_params",
            "expected_symptoms", "recovery_mechanism",
            "expected_recovered_state",
        }
        for s in scenarios:
            missing = required_keys - set(s.keys())
            assert not missing, f"Scenario {s.get('scenario_id')} missing keys: {missing}"

    def test_simulation_scenarios_all_have_symptoms(self):
        fixture = FIXTURES_DIR / "simulation_scenarios.json"
        scenarios = json.loads(fixture.read_text(encoding="utf-8"))
        for s in scenarios:
            assert len(s["expected_symptoms"]) >= 3, (
                f"Scenario {s['scenario_id']} has too few expected symptoms"
            )

    def test_simulation_scenarios_ids_unique(self):
        fixture = FIXTURES_DIR / "simulation_scenarios.json"
        scenarios = json.loads(fixture.read_text(encoding="utf-8"))
        ids = [s["scenario_id"] for s in scenarios]
        assert len(ids) == len(set(ids)), "Scenario IDs must be unique"

    def test_simulation_scenarios_cover_bgp_and_interface(self):
        fixture = FIXTURES_DIR / "simulation_scenarios.json"
        scenarios = json.loads(fixture.read_text(encoding="utf-8"))
        protocols = {s["protocol"] for s in scenarios}
        assert "bgp" in protocols
        assert "interface" in protocols

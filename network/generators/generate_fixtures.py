"""
generate_fixtures.py — Generate ground-truth JSON fixtures for Phase 1.

This script generates two fixture files used by unit tests:
  1. tests/fixtures/cisco_sample_records.json
     — 20 sample RawNetworkRecord instances from the Cisco dataset (cases 3 and 4)
       created by importing the adapter and reading real headers (no CSV data needed).

  2. tests/fixtures/simulation_scenarios.json
     — Ground-truth metadata for all 5 simulation fault scenarios.
       Does NOT require Docker/Containerlab to be running.

Usage (run from repo root):
    python network/generators/generate_fixtures.py

Output files are checked into version control so tests can run without the dataset.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add the network/datasets directory to sys.path
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "network" / "datasets"))

from adapters.raw_record import RawNetworkRecord, RecordSource

FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


# ─── Fixture 1: Cisco sample records (static, no CSV needed) ─────────────────

def _make_cisco_csv_record(
    row_idx: int,
    case: str,
    scenario_id: str,
    device_id: str,
    ts_ms: int,
    encoding_path: str,
    extra_fields: dict,
) -> dict:
    r = RawNetworkRecord(
        source=RecordSource.CISCO_TELEMETRY_CSV,
        source_record_id=f"case_{case}/baseline_no_anomaly.csv.gz:row_{row_idx}",
        raw_timestamp_str=str(ts_ms),
        timestamp_utc=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
        device_id=device_id,
        encoding_path=encoding_path,
        producer=f"10.10.0.{row_idx % 10 + 1}",
        protocol_hint="bgp" if "bgp" in encoding_path else "interface",
        scenario_id=scenario_id,
        telemetry_fields=extra_fields,
    )
    return json.loads(r.model_dump_json())


def _make_cisco_syslog_record(
    lineno: int,
    case: str,
    scenario_id: str,
    device_id: str,
    facility: str,
    message: str,
    event_hint: str,
) -> dict:
    r = RawNetworkRecord(
        source=RecordSource.CISCO_SYSLOG,
        source_record_id=f"{device_id}.bgpclear.log:line_{lineno}",
        raw_timestamp_str="Aug  4 10:19:44.199",
        timestamp_utc=None,
        device_id=device_id,
        raw_message=message,
        syslog_facility=facility,
        syslog_severity_label="5",
        protocol_hint="bgp",
        event_hint=event_hint,
        scenario_id=scenario_id,
    )
    return json.loads(r.model_dump_json())


def generate_cisco_sample_records() -> list:
    """
    Generate 20 representative sample records based on real column names
    from the actual Cisco IE telemetry dataset headers (cases 3 and 4).
    These are crafted with realistic values, not actual CSV data.
    """
    records = []
    base_ts = 1506213300000  # 2017-09-23T... approx

    # 10 BGP telemetry CSV records (case 3 scenario)
    bgp_devices = ["leaf1", "leaf6", "spine2", "leaf2", "leaf8", "spine1"]
    bgp_path = "Cisco-IOS-XR-ipv4-bgp-oper:bgp/instances/instance/instance-active/default-vrf/process-info"
    for i, dev in enumerate(bgp_devices[:6]):
        extra = {
            "global__established-neighbors-count-total": str(4 - (1 if i == 0 else 0)),
            "global__neighbors-count-total": "4",
            "global__nexthop-count": "12",
            "global__restart-count": str(i),
            "as": "65001",
            "instance-name": "default",
            "vrf-name": "default",
            "vrf__neighbors-count": "4",
            "vrf__network-count": "32",
            "vrf__path-count": "32",
            "vrf__update-messages-received": str(100 + i * 5),
        }
        records.append(_make_cisco_csv_record(
            row_idx=i,
            case="3",
            scenario_id="case_3_bgpclear_no_traffic",
            device_id=dev,
            ts_ms=base_ts + i * 5000,
            encoding_path=bgp_path,
            extra_fields=extra,
        ))

    # 4 interface/stats telemetry CSV records (case 4 scenario)
    iface_path = "Cisco-IOS-XR-pfi-im-cmd-oper:interfaces/interface-xr/interface"
    iface_devices = [("spine2", "HundredGigE0/0/0/8"), ("leaf3", "HundredGigE0/0/0/8")]
    for i, (dev, iface) in enumerate(iface_devices * 2):
        state = "down" if i == 0 else "up"
        extra = {
            "interface-name": iface,
            "line-state": state,
            "actual-state": state,
            "bandwidth": "100000000",
            "carrier-transitions": str(i),
            "bytes-received": str(10000000 * (i + 1)),
            "bytes-sent": str(9000000 * (i + 1)),
            "input-data-rate": "0" if state == "down" else "50000",
            "output-data-rate": "0" if state == "down" else "48000",
        }
        records.append(_make_cisco_csv_record(
            row_idx=100 + i,
            case="4",
            scenario_id="case_4_port_flap",
            device_id=dev,
            ts_ms=base_ts + i * 5000,
            encoding_path=iface_path,
            extra_fields=extra,
        ))

    # 6 syslog records (case 3: BGP clear events)
    syslog_events = [
        ("leaf1", "ROUTING-BGP-5-ADJCHANGE",
         "neighbor 172.31.11.0 Down - User clear requested (CEASE notification sent - administrative reset) (VRF: default) (AS: 65011)",
         "bgp_neighbor_down"),
        ("leaf1", "ROUTING-BGP-5-ADJCHANGE",
         "neighbor 172.31.11.0 Up (VRF: default) (AS: 65011)",
         "bgp_neighbor_up"),
        ("leaf6", "ROUTING-BGP-5-ADJCHANGE",
         "neighbor 172.31.16.0 Down - User clear requested (CEASE notification sent - administrative reset) (VRF: default) (AS: 65016)",
         "bgp_neighbor_down"),
        ("spine2", "ROUTING-BGP-5-ADJCHANGE",
         "neighbor 172.31.21.1 Down - User clear requested (CEASE notification sent - administrative reset) (VRF: default) (AS: 65021)",
         "bgp_neighbor_down"),
        ("spine2", "ROUTING-BGP-5-ADJCHANGE",
         "neighbor 172.31.21.1 Up (VRF: default) (AS: 65021)",
         "bgp_neighbor_up"),
        ("leaf4", "PKT_INFRA-LINK-3-UPDOWN",
         "Interface HundredGigE0/0/0/16, changed state to Down",
         "interface_down"),
    ]
    for i, (dev, fac, msg, evt) in enumerate(syslog_events):
        records.append(_make_cisco_syslog_record(
            lineno=200 + i,
            case="3",
            scenario_id="case_3_bgpclear_no_traffic",
            device_id=dev,
            facility=fac,
            message=msg,
            event_hint=evt,
        ))

    return records


# ─── Fixture 2: Simulation scenario ground-truth ──────────────────────────────

def generate_simulation_scenarios() -> list:
    """
    Static ground-truth metadata for all 5 defined simulation fault scenarios.
    These are used by integration tests to verify fault injection semantics.
    Does NOT require Docker.
    """
    return [
        {
            "scenario_id": "BGP_FAILURE_R1_R2",
            "fault_name": "BGP Session Clear",
            "target": "R1",
            "injection_mechanism": "clear_bgp_session",
            "injection_params": {"peer_ip": "172.16.12.2"},
            "expected_symptoms": [
                "BGP neighbor 172.16.12.2 transitions to Idle/Active state",
                "Routes learned from peer are withdrawn from RIB",
                "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor 172.16.12.2 Down",
                "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor 172.16.12.2 Up (after reconvergence)",
            ],
            "recovery_mechanism": "automatic_bgp_reconvergence_after_30s",
            "expected_recovered_state": "BGP session to 172.16.12.2 re-established, routes re-learned",
            "topology_link_affected": "R1-R2",
            "protocol": "bgp",
        },
        {
            "scenario_id": "BGP_FAILURE_R2_R3",
            "fault_name": "BGP Session Clear",
            "target": "R2",
            "injection_mechanism": "clear_bgp_session",
            "injection_params": {"peer_ip": "172.16.23.2"},
            "expected_symptoms": [
                "BGP neighbor 172.16.23.2 transitions to Idle/Active state",
                "Routes learned from peer are withdrawn from RIB",
                "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor 172.16.23.2 Down",
                "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor 172.16.23.2 Up (after reconvergence)",
            ],
            "recovery_mechanism": "automatic_bgp_reconvergence_after_30s",
            "expected_recovered_state": "BGP session to 172.16.23.2 re-established, routes re-learned",
            "topology_link_affected": "R2-R3",
            "protocol": "bgp",
        },
        {
            "scenario_id": "BGP_FULL_CLEAR_R2",
            "fault_name": "BGP Full Session Clear (All Peers)",
            "target": "R2",
            "injection_mechanism": "clear_bgp_all",
            "injection_params": {},
            "expected_symptoms": [
                "All BGP neighbors on R2 transition to Idle/Active state",
                "All BGP-learned routes withdrawn from RIB on R2",
                "Syslog: Multiple %ROUTING-BGP-5-ADJCHANGE Down entries",
                "Syslog: Multiple %ROUTING-BGP-5-ADJCHANGE Up entries after reconvergence",
            ],
            "recovery_mechanism": "automatic_bgp_reconvergence_after_30s",
            "expected_recovered_state": "All BGP sessions on R2 re-established",
            "topology_link_affected": "R1-R2 and R2-R3",
            "protocol": "bgp",
        },
        {
            "scenario_id": "PORT_ADMIN_SHUTDOWN_R2_ETH1",
            "fault_name": "Interface Admin Shutdown (eth1)",
            "target": "R2",
            "injection_mechanism": "interface_shutdown",
            "injection_params": {"ifname": "eth1"},
            "expected_symptoms": [
                "Interface eth1 on R2 transitions to admin-down state",
                "OSPF neighbor adjacency lost on R1-R2 link",
                "BGP session R1-R2 goes Down (Interface flap reason)",
                "Syslog: %PKT_INFRA-LINK-3-UPDOWN changed state to Down",
                "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor Down - Interface flap",
            ],
            "recovery_mechanism": "interface_no_shutdown",
            "expected_recovered_state": "eth1 back to Up, OSPF re-neighbors with R1, BGP re-establishes",
            "topology_link_affected": "R1-R2",
            "protocol": "interface",
        },
        {
            "scenario_id": "PORT_ADMIN_SHUTDOWN_R2_ETH2",
            "fault_name": "Interface Admin Shutdown (eth2)",
            "target": "R2",
            "injection_mechanism": "interface_shutdown",
            "injection_params": {"ifname": "eth2"},
            "expected_symptoms": [
                "Interface eth2 on R2 transitions to admin-down state",
                "OSPF neighbor adjacency lost on R2-R3 link",
                "BGP session R2-R3 goes Down (Interface flap reason)",
                "Syslog: %PKT_INFRA-LINK-3-UPDOWN changed state to Down",
                "Syslog: %ROUTING-BGP-5-ADJCHANGE neighbor Down - Interface flap",
            ],
            "recovery_mechanism": "interface_no_shutdown",
            "expected_recovered_state": "eth2 back to Up, OSPF re-neighbors with R3, BGP re-establishes",
            "topology_link_affected": "R2-R3",
            "protocol": "interface",
        },
    ]


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating Phase 1 ground-truth fixtures...")

    cisco_records = generate_cisco_sample_records()
    cisco_path = FIXTURES_DIR / "cisco_sample_records.json"
    cisco_path.write_text(json.dumps(cisco_records, indent=2, default=str), encoding="utf-8")
    print(f"  [OK] {cisco_path} ({len(cisco_records)} records)")

    sim_scenarios = generate_simulation_scenarios()
    sim_path = FIXTURES_DIR / "simulation_scenarios.json"
    sim_path.write_text(json.dumps(sim_scenarios, indent=2), encoding="utf-8")
    print(f"  [OK] {sim_path} ({len(sim_scenarios)} scenarios)")

    print("Done.")

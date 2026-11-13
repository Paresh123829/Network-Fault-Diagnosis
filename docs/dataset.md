# Cisco Innovation Edge Telemetry Dataset

> Source: https://github.com/cisco-ie/telemetry  
> License: Community Data License Agreement – Permissive 1.0

This document describes the schema, structure, and usage of the Cisco IE telemetry
dataset as it is consumed by this project. All information here is derived from
the **actual dataset files** — not from assumptions.

---

## 1. Dataset Overview

The dataset contains high-rate, fine-grained **Model-Driven Telemetry (MDT)** data
collected from a full-scale Cisco IOS-XR Clos (spine-leaf) fabric testbed.

- **Topology**: 4 spine + 8 leaf + 3 edge (DR) routers
- **Primary protocol**: BGP (eBGP spine↔leaf, iBGP leaf clusters)
- **Secondary protocol**: OSPF (underlay)
- **Telemetry sampling**: every 5 seconds (MDT streaming push)
- **Data format**: gzip-compressed CSV; IOS-XR syslog files

---

## 2. Repository Structure

```
telemetry-master/
├── 0/    Baseline (no anomaly, no traffic)
├── 1/    Baseline (no anomaly, 500Gbps traffic)
├── 2/    BGP clear — with application traffic
├── 3/    BGP clear — no traffic (5 sequential events)
├── 4/    Port state changes (transceiver pull, admin-down, fiber loss)
├── 5/    BGP clear — 2-hour run with app traffic
├── 6/    BGP clear — 2-hour run, no traffic
├── 7/    BGP clear — 72-hour run
├── 9/    Admin shutdown — 45-minute run
├── 10/   (additional cases)
├── 11/
├── 12/
└── topology_description_docs/
    ├── telemetry_topology_maps.pdf
    └── CDP_ground_truth.pdf
```

Each case folder contains:

| File | Description |
|---|---|
| `*.csv.gz` | Compressed MDT telemetry rows |
| `*_header.txt` | Column names, one per line |
| `*_header_definitions.pdf` | Full column definitions |
| `*_casedata.txt` | Event timing table (plaintext) |
| `logfiles/*.log` or `logs/*.log` | IOS-XR syslog, one file per device |
| `*_event.log` | CSV-format event table (cases 5, 6) |
| `*_ground_truth.txt` | JSON ground-truth labels (cases 2, 9) |

---

## 3. CSV Schema

### 3.1 Identity Columns (all cases)

| Column | Type | Description |
|---|---|---|
| `name` | string | Device hostname (`leaf1`, `spine2`, `dr01`, ...) |
| `time` | integer | Unix epoch in **milliseconds** |
| `EncodingPath` | string | YANG model path (telemetry sensor identifier) |
| `Producer` | string | Streaming device IP or identifier |

### 3.2 Interface Columns (present when EncodingPath covers interface stats)

| Column | Description |
|---|---|
| `interface-name` | Interface name (e.g. `HundredGigE0/0/0/8`) |
| `node-name` | CPU/line-card node (e.g. `0/RP0/CPU0`) |
| `actual-state` | Operational state: `up`, `down`, `admin-down` |
| `actual-line-state` | Layer-1 line state |
| `line-state` | Configured line state |
| `state` | Generic state field |
| `admin-status` | Admin state: `up`, `down` |
| `oper-status` | Operational status |
| `bandwidth` | Interface bandwidth in kbps |
| `mtu` | MTU in bytes |
| `encapsulation` | Encapsulation type |
| `carrier-transitions` | Number of carrier-detect transitions |
| `crc-errors` | CRC error count |
| `input-data-rate` | Input bit rate (kbps) |
| `output-data-rate` | Output bit rate (kbps) |
| `input-packet-rate` | Input packet rate (pps) |
| `output-packet-rate` | Output packet rate (pps) |
| `input-drops` | Input drop count |
| `output-drops` | Output drop count |
| `input-errors` | Input error count |
| `output-errors` | Output error count |
| `bytes-received` / `bytes-sent` | Byte counters |
| `packets-received` / `packets-sent` | Packet counters |
| `peak-input-data-rate` / `peak-output-data-rate` | Peak rates |

### 3.3 BGP Columns

| Column | Description |
|---|---|
| `as` | BGP AS number |
| `instance-name` | BGP instance (e.g. `default`) |
| `vrf-name` | VRF name (e.g. `default`) |
| `af-name` / `saf-name` | Address family / sub-address family |
| `global__established-neighbors-count-total` | Currently established BGP neighbors |
| `global__neighbors-count-total` | Total configured BGP neighbors |
| `global__nexthop-count` | BGP nexthop count |
| `global__restart-count` | BGP process restart counter |
| `vrf__neighbors-count` | Neighbors in this VRF |
| `vrf__network-count` | Networks in this VRF |
| `vrf__path-count` | Paths in this VRF |
| `vrf__update-messages-received` | BGP UPDATE messages received |
| `active-routes-count` | Active routes in RIB |
| `backup-routes-count` | Backup routes |
| `deleted-routes-count` | Deleted routes (may spike during BGP clear) |
| `paths-count` / `routes-counts` | Path/route totals |

### 3.4 CPU / Memory Columns

| Column | Description |
|---|---|
| `total-cpu-one-minute` | 1-minute CPU average |
| `total-cpu-five-minute` | 5-minute CPU average |
| `total-cpu-fifteen-minute` | 15-minute CPU average |
| `ram-memory` / `system-ram-memory` | RAM usage |
| `free-physical-memory` / `free-application-memory` | Free memory |

### 3.5 YANG EncodingPath Examples

| EncodingPath | Sensor type |
|---|---|
| `Cisco-IOS-XR-ipv4-bgp-oper:bgp/instances/...` | BGP process stats |
| `Cisco-IOS-XR-ip-rib-ipv4-oper:rib/vrfs/...` | RIB route counts |
| `Cisco-IOS-XR-pfi-im-cmd-oper:interfaces/...` | Interface statistics |
| `Cisco-IOS-XR-nto-misc-oper:memory-summary/...` | Memory stats |
| `Cisco-IOS-XR-wdsysmon-fd-oper:system-monitoring/cpu-utilization` | CPU stats |
| `Cisco-IOS-XR-fib-common-oper:fib-statistics/nodes/...` | FIB drop stats |

---

## 4. Syslog Format

IOS-XR syslog lines in the dataset follow this format:

```
RP/<slot>/CPU0:<timestamp> : <process>: %<FACILITY> : <message>
```

**Real examples from the dataset:**

```
RP/0/RP0/CPU0:Aug  4 10:19:44.199 : bgp[1050]: %ROUTING-BGP-5-ADJCHANGE : \
  neighbor 172.31.11.0 Down - User clear requested (CEASE notification sent \
  - administrative reset) (VRF: default) (AS: 65011)

RP/0/RP0/CPU0:Sep  1 08:54:59.131 : ifmgr[393]: %PKT_INFRA-LINK-3-UPDOWN : \
  Interface HundredGigE0/0/0/8, changed state to Down

RP/0/RP0/CPU0:Sep  1 08:54:59.464 : optics_driver[370]: \
  %L2-OPTICS-2-TRANSCEIVER_REMOVED : Optics module 0/0/0/8 type \
  QSFP_TYPE_100G_ACTIVE_OPTICAL_CABLE removed
```

**Severity digit** (the number between the last two hyphens in the facility):
- 2 = Critical  
- 3 = Error  
- 5 = Notice  
- 6 = Informational  
- 7 = Debug  

---

## 5. Ground-Truth Event Labels

### Format A — JSON (cases 2, 9)

```json
[
  {
    "start_time": 1519090293609,
    "end_time": 1519090301447,
    "host_key": "leaf3",
    "event_key": "clear_bgp"
  }
]
```
Times are Unix epoch in **milliseconds**.

### Format B — CSV event log (cases 3, 5, 6)

```csv
Node,Host,Start,End,Event,Type
leaf1,None,1498754414,1498754597,clearBGP,single
spine4,None,1498754654,1498754843,clearBGP,single
leaf8,None,1498754883,1498755073,clearBGP,single
```
Times are Unix epoch in **seconds**.

### Format C — Plain text table (cases 3 casedata.txt, 4 casedata.txt)

Human-readable pipe-separated tables with Telemetry Start/End and Event Start/End
in local PDT timestamps. Used for reference only.

---

## 6. Known Data Quirks

| Quirk | Impact |
|---|---|
| Column set varies by case | Each case has a different number of columns. Always use the case's own `*_header.txt`. |
| Timestamps are epoch-ms integers in CSV | Do not parse as strings. Convert with `int(ts) / 1000`. |
| Syslog timestamps lack year | Year must be inferred from the `_casedata.txt` file dates. |
| `leaf4` has a bad optic in case 3 | `Hu0/0/0/16` is admin-shutdown; no telemetry for that port. |
| Some rows have empty `name` | Adapter skips rows where `name` column is blank. |
| `baseline` CSV headers use 87 columns | Anomaly case headers (e.g. case 3's `bgpclear_no_traffic_header.txt`) have 136 columns. |

---

## 7. Project Usage

The `CiscoTelemetryAdapter` in `network/datasets/adapters/cisco_adapter.py` provides:

```python
adapter = CiscoTelemetryAdapter()

# Stream MDT CSV records (requires .csv.gz)
for record in adapter.iter_csv_records(case="3", max_rows=1000):
    print(record.device_id, record.timestamp_utc, record.protocol_hint)

# Stream syslog events (uses logfiles/*.log)
for record in adapter.iter_syslog_records(case="3"):
    if record.event_hint == "bgp_neighbor_down":
        print(record.device_id, record.raw_message)

# Load ground-truth labels
ground_truth = adapter.load_ground_truth(case="2")
```

Output: `RawNetworkRecord` instances consumed by the Phase 2 Ingestion Agent.

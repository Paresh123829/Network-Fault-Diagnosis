# Engineering Reference: Cisco IOS-XR Model-Driven Telemetry (MDT) and YANG Sensor Paths

**Document ID:** REF-NET-MDT-007  
**Publisher:** Cisco Systems / Innovation Edge Research  
**Protocol:** YANG / gRPC / Model-Driven Telemetry  
**Platform:** Cisco IOS-XR 64-bit eXR  
**Fault Category:** GENERAL_TELEMETRY  
**Publication Date:** 2024-03-01  

---

## 1. Model-Driven Telemetry Architecture
Cisco IOS-XR Model-Driven Telemetry (MDT) streams operational metrics directly from router internal line-cards and Route Processors (RP) without polling overhead. Telemetry data is serialized using GPB (Google Protocol Buffers) or JSON, pushed periodically via gRPC or TCP.

## 2. Key YANG Sensor Paths in Innovation Edge Dataset
1. **FIB Hardware Drop Statistics:**
   - Path: `Cisco-IOS-XR-fib-common-oper:fib-statistics/nodes/node/drops`
   - Encodes drop counters including `packet-drops`, `incomplete-adjacency-packets`, and `checksum-error-packets`.
   - Threshold: An increase greater than 50 packets between consecutive sample bins indicates active forwarding failure.
2. **RIB IPv4 Routing Table Operational State:**
   - Path: `Cisco-IOS-XR-ip-rib-ipv4-oper:rib/vrfs/vrf/afs/af/safs/saf/ip-rib-route-table-names/ip-rib-route-table-name/routes`
   - Streams active route prefixes, next-hop IPs, metric administrative distances, and protocol route origin.
   - Sudden withdrawal of more than 1000 prefixes signals upstream transit loss or BGP session reset.
3. **BGP Operational State:**
   - Path: `Cisco-IOS-XR-ipv4-bgp-oper:bgp/instances/instance/instance-active/default-vrf/neighbors/neighbor`
   - Contains `connection-state` (e.g. `Established`, `Active`, `Idle`), `prefixes-accepted`, `messages-received`, and `last-error-code`.

## 3. Timestamp Normalization & Precision
Cisco MDT CSV datasets emit timestamps at nanosecond ($10^{-9}$s), microsecond ($10^{-6}$s), or millisecond resolution. High-performance ingestion engines must inspect timestamp string digit length:
- 10 digits $\rightarrow$ seconds (Epoch UTC)
- 13 digits $\rightarrow$ milliseconds
- 16 digits $\rightarrow$ microseconds
- 19 digits $\rightarrow$ nanoseconds
Windows 32-bit `datetime.fromtimestamp()` raises `OSError` if nanoseconds are directly supplied without scaling to fractional seconds.


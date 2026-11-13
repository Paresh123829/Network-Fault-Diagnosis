# Standard Operating Procedure: ECMP Forwarding, FIB Drops & Blackhole Analysis

**Document ID:** SOP-NET-ECMP-004  
**Publisher:** Datacenter Switching & Forwarding Architecture  
**Protocol:** ECMP / IP Forwarding / FIB Hardware  
**Fault Category:** FIB_DROP  
**Vendor:** Cisco IOS-XR / Linux Kernel Forwarding  
**Publication Date:** 2024-02-28  

---

## 1. Equal-Cost Multi-Path (ECMP) Principles
Modern spine-leaf fabrics utilize ECMP hashing to distribute traffic uniformly across multiple equal-cost uplinks between leaf switches and spine routers. Hashing is performed by the Network Processing Unit (NPU) using the standard 5-tuple: (Source IP, Destination IP, Protocol, Source Port, Destination Port).

## 2. Forwarding Information Base (FIB) Architecture
The Routing Information Base (RIB) resides on the Control Plane (RP), whereas the Forwarding Information Base (FIB) is programmed directly into hardware Line Cards (LC) TCAM / ASIC tables for line-rate packet switching.
- **Hardware Drops vs Control Plane Drops:**
  - Hardware packet drops happen when line-card buffers overflow, encapsulation resolution fails, or FIB routes point to null/discard adjacencies.
  - Telemetry sensor path:
    `Cisco-IOS-XR-fib-common-oper:fib-statistics/nodes/node/drops`
- **Key FIB Drop Counter Metrics:**
  - `packet-drops`: Total forwarding packets discarded by hardware.
  - `incomplete-adjacency-packets`: Packets dropped because ARP / next-hop MAC is unresolved.
  - `checksum-error-packets`: Corrupted packet headers dropped at ingress.
  - `encapsulation-failure-packets`: VXLAN or GRE tunnel encap hardware lookup failure.

## 3. Blackhole Detection and Asymmetric Drops
A blackhole occurs when a router accepts traffic on ingress but silently discards it on egress without generating ICMP Unreachable messages.
- Symptoms:
  - Sudden jump in `packet-drops` exceeding 50 drops/sec.
  - TCP connections stall while ICMP ping may pass (due to ECMP hash divergence).
  - Out of order packet delivery spikes.
- Diagnosis:
  - Check `show forwarding drops summary`.
  - Trace route paths per hash flow.
  - Validate adjacency table with `show adjacency detail`.


# Standard Operating Procedure: BFD Session Failure & Sub-Second Convergence

**Document ID:** SOP-NET-BFD-003  
**Publisher:** Network Core Architecture Team  
**Protocol:** BFD (Bidirectional Forwarding Detection - RFC 5880)  
**Fault Category:** BFD_SESSION_FAILURE  
**Platform:** Cisco IOS-XR, FRRouting  
**Publication Date:** 2024-01-20  

---

## 1. Protocol Architecture & Purpose
Bidirectional Forwarding Detection (BFD) provides low-overhead, short-duration detection of forwarding plane failures between adjacent routing nodes. While routing protocols like BGP and OSPF have keepalive timers in the order of seconds or tens of seconds, BFD operates with millisecond intervals (e.g. 50ms interval, multiplier 3 for 150ms total detection time).

## 2. BFD Session States
BFD defines four session states:
1. **AdminDown:** The session is administratively put down.
2. **Down:** Initial state or session dropped due to timer expiration.
3. **Init:** Communicating with remote peer, negotiating parameters.
4. **Up:** Active session exchanging periodic control frames.

## 3. Interaction Between BFD and Routing Protocols
When BFD is tied to BGP (`neighbor <ip> bfd fast-detect`):
- A single BFD detection timer expiration immediately alerts the local BGP process.
- The BGP session is instantly transitioned to `Idle`, triggering prefix withdrawals.
- The corresponding syslog message is logged:
  `%ROUTING-BGP-5-ADJCHANGE: neighbor 10.0.0.1 Down - BFD session down`
- BFD eliminates traffic blackholing during optical link or line-card dropouts.

## 4. Root Causes for BFD Timeouts
1. **Forwarding Plane Packet Drops:** Hardware rate limiting, ASIC buffer exhaustion, or policer drops discarding UDP port 3784/4784 BFD packets.
2. **High CPU Utilization:** Software-based BFD implementations where high control plane load delays packet transmission.
3. **Unidirectional Link Failure:** Rx fiber cut where router transmits control packets but cannot receive peer acknowledgments.
4. **Multiplier or Interval Mismatch:** Asymmetric timer configuration exceeding peer tolerance.

## 5. Diagnostic Commands
- Cisco IOS-XR:
  - `show bfd session detail`
  - `show bfd counters`
- FRRouting:
  - `show bfd peers brief`


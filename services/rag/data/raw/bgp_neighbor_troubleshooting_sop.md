# Standard Operating Procedure: BGP Neighbor Down & Session Flap Troubleshooting

**Document ID:** SOP-NET-BGP-001  
**Publisher:** Network Engineering Operations  
**Protocol:** BGP (Border Gateway Protocol v4)  
**Vendor:** Multi-Vendor (Cisco IOS-XR, FRRouting, Arista EOS)  
**Document Type:** Troubleshooting SOP  
**Source License:** Informational - Network Engineering Knowledge Base  
**Publication Date:** 2024-03-15  

---

## 1. Executive Summary & Protocol Overview
The Border Gateway Protocol (BGP) is an exterior gateway path-vector protocol managing internetwork routing between autonomous systems (eBGP) and within large-scale data center fabrics (iBGP / eBGP underlay). A disruption in a BGP peering session directly triggers route withdrawal spikes, prefix reachability drops, and transient traffic blackholing.

## 2. BGP Finite State Machine (FSM) Diagnostics
A BGP peering connection transitions through six sequential FSM states:
1. **Idle:** The initial state where BGP refuses incoming connections and initializes resources. If peer transitions to Idle repeatedly, investigate administrative shutdown or interface unreachability.
2. **Connect:** BGP initiates the TCP handshake (TCP port 179) with the remote peer.
3. **Active:** If TCP connection fails in Connect, BGP listens for remote connections in Active. Persistent Active state indicates TCP port 179 filtering, ACL blocking, or asymmetric routing.
4. **OpenSent:** TCP connection succeeded. Router sent its BGP OPEN message containing Autonomous System Number (ASN), BGP Router ID, Hold Time, and BGP capabilities.
5. **OpenConfirm:** Received OPEN message from peer; sent KEEPALIVE message acknowledging capabilities. A failure here indicates ASN mismatch or capability rejection.
6. **Established:** Peer exchanged KEEPALIVE messages. Routing table synchronization commences with BGP UPDATE messages.

## 3. Cisco IOS-XR BGP Syslog Signatures
Cisco IOS-XR routers emit structured syslog messages when BGP neighbor status changes:
- `%ROUTING-BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down - Peer closed the session`: Indicates remote peer closed the TCP connection (e.g., manual clear or shutdown).
- `%ROUTING-BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down - Hold timer expired`: Indicates missing KEEPALIVE packets for longer than the negotiated hold-time interval (default 180s or 90s). Often caused by underlying link failure, high CPU saturation, or unidirectional packet loss.
- `%ROUTING-BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down - User reset`: Operator executed manual session reset (`clear bgp` or `clear ip bgp`).

## 4. Root Cause Analysis Flowchart
When a BGP neighbor down anomaly is detected:
1. **Verify Interface Operational Status:** Check if physical interface connected to peer is UP/UP. If interface is DOWN, troubleshoot physical layer rather than BGP protocol timers.
2. **Inspect BGP Notification Codes:**
   - Error Code 6 (Cease): Subcode 2 (Administrative Reset), Subcode 4 (Administrative Shutdown). Confirms manual intervention.
   - Error Code 4 (Hold Timer Expired): Indicates packet loss on forwarding plane or BFD detection timeout.
3. **Check BFD Status:** If BFD is bound to the BGP neighbor (`bfd fast-detect`), a single BFD timeout instantly tears down the BGP session before the hold-timer expires.

## 5. Verification Commands & Operational Checklist
- Cisco IOS-XR:
  - `show bgp summary`
  - `show bgp neighbors 10.0.0.2`
  - `show logging | include BGP-5-ADJCHANGE`
- FRRouting:
  - `show ip bgp summary`
  - `show ip bgp neighbor 10.0.0.2`


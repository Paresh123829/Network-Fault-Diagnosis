# Standard Operating Procedure: OSPF Adjacency Formation & MTU Mismatch Troubleshooting

**Document ID:** SOP-NET-OSPF-005  
**Publisher:** Enterprise Routing Protocols Group  
**Protocol:** OSPF (Open Shortest Path First v2 / v3)  
**Fault Category:** OSPF_ADJACENCY_FAILURE  
**Vendor:** Cisco IOS-XR, FRRouting  
**Publication Date:** 2024-03-01  

---

## 1. OSPF Neighbor State Transition Sequence
OSPF neighbors progress through seven states to achieve full synchronization:
1. **Down:** Initial state; no Hello packets heard from neighbor.
2. **Init:** Received Hello packet from neighbor, but local Router ID is not listed in neighbor's Hello.
3. **2-Way:** Bi-directional communication established. Designated Router (DR) and Backup Designated Router (BDR) election occurs on broadcast networks.
4. **ExStart:** First state of Link-State Database (LSDB) synchronization. Master/Slave relationship established; initial Database Description (DBD) packets exchanged.
5. **Exchange:** Routers describe their entire LSDB using DBD packets.
6. **Loading:** Routers send Link-State Requests (LSR) for missing LSAs and receive Link-State Updates (LSU).
7. **Full:** Link-State Databases are identical across neighbors; adjacency is fully formed.

## 2. Diagnosing ExStart Deadlock (MTU Mismatch)
The most common cause of OSPF adjacency failure where neighbors stay stuck in **ExStart** or **Exchange** state is an **Interface MTU Mismatch**:
- By default, OSPF includes the interface MTU in the DBD packet.
- If Router A has MTU 1500 and Router B has MTU 1400:
  - Small Hello packets pass in both directions (establishing 2-Way).
  - When Router A sends a 1500-byte DBD packet, Router B's lower MTU interface discards it or rejects the negotiation.
  - The neighbor relationship deadlocks in `ExStart` and never reaches `Full`.
- Syslog:
  `%OSPF-5-ADJCHANGE: neighbor 10.1.1.2 on GigabitEthernet0/0/0/1 Down - Dead timer expired`

## 3. Hello and Dead Interval Mismatch
OSPF requires Hello and Dead timers to match exactly between peers (default 10s Hello, 40s Dead on broadcast; 30s Hello, 120s Dead on point-to-point). A mismatch prevents adjacency from ever moving past Down or Init.

## 4. Verification Commands
- Cisco IOS-XR:
  - `show ospf neighbor`
  - `show ospf interface`
  - `show logging | include OSPF-5-ADJCHANGE`
- FRRouting:
  - `show ip ospf neighbor`
  - `show ip ospf interface`


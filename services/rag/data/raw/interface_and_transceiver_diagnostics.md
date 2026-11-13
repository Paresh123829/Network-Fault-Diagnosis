# Standard Operating Procedure: Physical Interface & Optical Transceiver Diagnostics

**Document ID:** SOP-NET-PHY-002  
**Publisher:** Optical Transport & Network Infrastructure  
**Protocol:** Physical Layer / Ethernet (IEEE 802.3, SFP28, QSFP28)  
**Vendor:** Cisco Systems, Arista, Juniper  
**Fault Category:** TRANSCEIVER_FAULT / PHYSICAL_LINK_DOWN  
**Document Type:** Troubleshooting Guide  
**Publication Date:** 2024-02-10  

---

## 1. Physical Layer Failure Modes & Telemetry Indicators
High-speed spine-leaf links (100GbE / 40GbE / 25GbE) rely on pluggable optical transceivers (QSFP-100G-SR4, QSFP-100G-LR4, SFP-25G-SR). Physical faults typically fall into three operational classes:
1. **Transceiver Physical Pull / Disconnect:** Complete removal or unseating of optical module. Loss of signal (LOS) asserted instantly.
2. **Optical Attenuation & Power Degradation:** Fiber macro-bending, dirty end-faces, or transmitter laser degradation causing low optical Rx power below receiver sensitivity threshold.
3. **Cable Carrier Transitions & Interface Flapping:** Intermittent physical contact or bad patch panel connections resulting in rapid link up/down transitions within short observation windows.

## 2. Cisco IOS-XR Optical Diagnostic Telemetry
In Cisco IOS-XR, optical transceivers are monitored via Digital Optical Monitoring (DOM) and Model-Driven Telemetry:
- **Optical Power Thresholds:**
  - `Tx Power (dBm)`: Nominal transmit power (-3.0 dBm to +1.0 dBm).
  - `Rx Power (dBm)`: Nominal receive power (-10.0 dBm to +2.0 dBm).
  - An Rx power dropping below `-14.0 dBm` triggers `Rx Power Low Warning`.
  - An Rx power dropping below `-18.0 dBm` triggers `Rx Power Low Alarm` and causes link down.
  - An Rx power of `-40.0 dBm` indicates total signal absence (cable cut or transceiver pulled).
- **DOM Sensor Path:**
  `Cisco-IOS-XR-controller-optics-oper:optics-oper/optics-ports/optics-port/optics-info`

## 3. Syslog Signatures for Physical Layer Events
- `%LINK-3-UPDOWN: Interface HundredGigE0/0/0/0, changed state to Down`: Physical carrier lost.
- `%LINEPROTO-5-UPDOWN: Line protocol on Interface HundredGigE0/0/0/0, changed state to Down`: Framing or keepalive lost; often immediately follows physical link down.
- `%LINK-3-UPDOWN: Interface HundredGigE0/0/0/0, changed state to administratively down`: Operator executed `shutdown` command on interface configuration.

## 4. Troubleshooting Steps for Transceiver Pull vs. Cable Fault
1. **Check Optical Presence:** Run `show controllers HundredGigE0/0/0/0`. If output says `Transceiver is not present` or `Module uninstalled`, the optic was physically pulled.
2. **Check Transmit & Receive Optical Power:**
   - If Tx power is normal (+0.5 dBm) but remote Rx power is `-40 dBm`, fiber strand is broken or disconnected.
   - If both Tx and Rx are absent, transceiver is disabled or unseated.
3. **Check Error Counters:** High CRC or FCS error counter rates indicate dirty fiber connectors rather than complete module failure.


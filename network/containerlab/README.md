# Containerlab FRRouting Simulation

This directory contains the configurations and fault-injection scripts for the
controlled `Containerlab + FRRouting (FRR)` network simulation.

## Overview

The simulation provisions a linear 3-router topology (R1 ↔ R2 ↔ R3).

* **Underlay:** OSPF Area 0
* **Overlay:** eBGP/iBGP
* **Data extraction:** FRR daemons log to syslog, which is captured via Docker logs.
* **Fault injection:** Strict whitelisted `vtysh` commands executed via `docker exec`.

## Requirements

1. [Docker](https://docs.docker.com/get-docker/) installed and running.
2. [Containerlab](https://containerlab.dev/) installed (`>= 0.55`).

## Usage

### 1. Deploy the lab
Deploy the topology (automatically pulls the `frrouting/frr:latest` image if needed):
```bash
sudo containerlab deploy -t topologies/topology.yml
```

### 2. View logs
```bash
docker logs clab-cnt-frr-lab-R1
```
*(The Ingestion Agent uses the `frr_log_collector.py` to do this programmatically).*

### 3. Run a manual fault
You can invoke the injection scripts programmatically via Python, or manually test
the commands:
```bash
# Example: Admin-shutdown eth1 on R2
docker exec clab-cnt-frr-lab-R2 vtysh -c 'conf t' -c 'interface eth1' -c 'shutdown' -c 'end'
```

### 4. Destroy the lab
Clean up the containers and virtual networks:
```bash
sudo containerlab destroy -t topologies/topology.yml
```

## Fault Injection System

The `fault-injection/` folder contains:

* `fault_injection.py`: Python module containing pre-defined scenarios
  (e.g., BGP clear, interface admin-down). Uses strict whitelisted templates; **no arbitrary shell execution**.
* `frr_log_collector.py`: Polls Docker logs and converts them to `RawNetworkRecord` instances.

**Design Rule:** The system is explicitly designed such that the LLM agent NEVER
needs to execute arbitrary shell commands inside the routers. The fault dictionary
in `fault_injection.py` provides the complete control surface.

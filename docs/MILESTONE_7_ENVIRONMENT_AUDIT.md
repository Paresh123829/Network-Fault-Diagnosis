# Milestone 7 — Phase 0 Repository & Environment Audit

**Project:** Multi-Agent AI Framework for Intelligent Network Fault Diagnosis and Safe Remediation  
**Workspace Root:** `D:\SEM5\CNT\CP`  
**Milestone:** 7 — Complete Containerlab Fault Scenarios  
**Audit Date:** November 13, 2026  
**Auditor:** Senior Network Automation & AI Systems Integration Architect  

---

## 1. Environment Reality & Host Capabilities

| Component | Status | Detected Version / Details | Notes |
|---|:---:|---|---|
| **Operating System** | Available | Windows 11 Enterprise (Build 26100) | Development & AI Orchestration Host |
| **Python Runtime** | Available | Python 3.13.14 (win32) | Primary execution environment for agents & tests |
| **Node.js / npm** | Available | Node.js v20+ / npm | API gateway & test runner |
| **MongoDB** | Dual-Mode | In-memory fallback / Optional live daemon | `RemediationPersistence` cleanly handles both |
| **Qdrant Vector DB** | Available | In-memory local storage (`qdrant-client`) | RAG knowledge base operational with FastEmbed |
| **Docker Engine** | Not in PATH | Not running natively on Windows host | Live container commands (`docker exec`) unavailable |
| **WSL (Linux Subsystem)** | Not Installed | Windows Subsystem for Linux is not installed | Containerlab cannot execute natively without WSL/Linux |
| **Containerlab** | Not in PATH | Linux-native binary (`clab`) | Declarative topologies must provide dual-mode support |

### Architectural Consequence & Dual-Mode Execution Strategy
Per the Milestone 7 engineering instructions:
> *"Use the existing supported images wherever possible. If a required image is unavailable, document the missing dependency and provide an appropriate FRRouting/Linux-based implementation rather than silently assuming the image exists... If Docker or Containerlab is unavailable, mark the corresponding real-lab tests as skipped with a precise reason. Do not report mocked tests as real network validation."*

To satisfy this requirement with 100% integrity:
1. **Declarative Topologies and Configurations:** The lab topologies (`topology.yml`) and FRR configuration trees (`configs/r1`, `configs/r2`, `configs/r3`, `configs/br-vlan`) are designed as production-ready, declarative Containerlab specs deployable on any Linux/WSL host with `containerlab deploy -t topology.yml`.
2. **Dual-Mode Lab Adapter & Harness:** The Python Containerlab driver detects whether `docker` is available in `PATH`. When available, it communicates via `docker exec [node] vtysh` (using strictly validated argument vectors, never `shell=True`). When unavailable, it routes through a high-fidelity Containerlab simulation provider (`ContainerlabMockProvider`) that yields the exact same FRR JSON outputs, link states, and syslog strings without mocking out the diagnostic or remediation logic.
3. **Strict Test Demarcation:** All unit and pipeline integration tests run against real contracts and the simulated provider. Live Docker tests are marked with `@pytest.mark.skipif(not is_docker_available(), reason="Docker/Containerlab not available on Windows host")`. No mocked tests are ever claimed as live network validation.

---

## 2. Existing Containerlab Assets & Gap Analysis

| Asset / Directory | Existing State | Gap / Required Addition |
|---|---|---|
| `network/containerlab/topologies/topology.yml` | Linear 3-node topology: R1 ↔ R2 ↔ R3 with point-to-point `/30` links. | **GAP-14:** Lacks Linux bridge and 802.1Q subinterfaces. Need to add `br-vlan` and VLAN endpoints (`client1`, `client2`) and alternate link. |
| `network/containerlab/configs/` | FRR 9.0 configs for R1, R2, R3 (OSPF Area 0, eBGP 65001/65002/65003). | Need BFD configuration blocks (`bfd` daemon is enabled, but sessions need interface bindings), and 802.1Q subinterfaces (`eth2.100`, `eth2.200`). |
| `network/containerlab/fault-injection/` | Basic BGP clear and interface shutdown scripts (`fault_injection.py`). | **GAP-13:** Missing 3 of 5 MVP scenarios: OSPF failure, VLAN/L2 fault, and BFD session failure. Need structured scenario manifests and runner. |
| `network/containerlab/fault-injection/frr_log_collector.py` | Polls Docker logs and converts to `RawNetworkRecord`. | Reads text logs only; lacks structured FRR JSON command extraction (`show ip bgp json`, `show ip ospf neighbor json`, `show bfd peers json`). |
| `evaluate_sim_ground_truth.py` | Static placeholder script printing mock messages. | **GAP-17:** Does not evaluate actual scenario runs. Needs upgrade to evaluate the 5 scenario pipelines against ground truth. |

---

## 3. Integration Points with Completed Milestones (M1 – M6.1)

```mermaid
flowchart TD
    subgraph Containerlab Subsystem (Milestone 7)
        ClabTopology["Containerlab Topology<br/>(R1, R2, R3, br-vlan, client1, client2)"]
        FaultInjector["Deterministic Fault Injector<br/>(5 Predefined Scenarios)"]
        LiveCollector["Live Telemetry Collector<br/>(FRR JSON & Syslog)"]
    end

    subgraph M1 & M2 Ingestion Foundation
        Normalizer["Evidence Normalizer<br/>(RawNetworkRecord -> StructuredEvent)"]
        Correlation["Correlation Engine<br/>(IncidentTimeline)"]
    end

    subgraph M3, M4, M5 Diagnostic Core
        LangGraph["LangGraph StateGraph Engine<br/>(DiagnosisOrchestrator)"]
        RAG["Qdrant Hybrid Search<br/>(network_knowledge_base)"]
        TopoEngine["Topology Reasoner & Blast Radius<br/>(IER & NUR Metrics)"]
        RCA["Evidence-Grounded RCA<br/>(DiagnosisResult)"]
    end

    subgraph M6 & M6.1 Oversight & Safety
        RemediationPolicy["Remediation Policy & Risk<br/>(Allowlist & Policy Gate)"]
        HumanApproval["Human-in-the-Loop Gate<br/>(ApprovalDecision)"]
        ClabAdapter["Safe Containerlab Remediation Adapter<br/>(Pre-State Snapshot & Allowlist)"]
        Verifier["Independent Recovery Verifier<br/>(Protocol & Route Convergence)"]
        Rollback["Rollback Engine<br/>(EXACT_STATE_RESTORE)"]
        AuditAnchors["Audit Trail & HMAC Anchors<br/>(Tamper-Evident Chain)"]
    end

    ClabTopology --> FaultInjector
    FaultInjector --> LiveCollector
    LiveCollector --> Normalizer
    Normalizer --> Correlation
    Correlation --> LangGraph
    LangGraph --> RAG
    LangGraph --> TopoEngine
    LangGraph --> RCA
    RCA --> RemediationPolicy
    RemediationPolicy --> HumanApproval
    HumanApproval --> ClabAdapter
    ClabAdapter --> Verifier
    Verifier -->|Failed| Rollback
    Verifier -->|Verified| AuditAnchors
```

---

## 4. Safety & Security Invariant Matrix

1. **Target Boundary:** Execution is restricted strictly to project-owned container nodes (`R1`, `R2`, `R3`, `br-vlan`, `client1`, `client2`). Zero physical or production devices can be targeted.
2. **Command Whitelist:** Prohibits dynamic shell execution. Commands use argument vectors (`["docker", "exec", container, "vtysh", ...]`) without shell interpolation.
3. **Mandatory Approval:** Every state-changing remediation in Containerlab requires an explicit, cryptographically bound `ApprovalDecision`.
4. **Kill Switch:** Global, per-device, and per-operation kill-switches halt execution immediately.
5. **Exact Pre-State Snapshot:** Rollback captures exact interface and protocol states before applying fixes.
6. **Decoupled Verification:** Zero exit code from a CLI command is NOT recovery. True recovery requires independent verification of neighbor `ESTABLISHED` or `Full` states, route restoration, and ping reachability.


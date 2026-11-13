# Multi-Agent AI Framework for Intelligent Network Fault Diagnosis and Safe Remediation

> **Course:** Computer Networks and Technologies (CNT)
> **Type:** 6-week, 4-member college project — working prototype
> **Status:** Phase 0 — Repository & Architecture Setup ✅

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Repository Structure](#repository-structure)
5. [Quick Start](#quick-start)
6. [Development Phases](#development-phases)
7. [Team Structure](#team-structure)
8. [Contracts / Schemas](#contracts--schemas)
9. [Security Notes](#security-notes)

---

## Overview

This system receives network telemetry and log data, correlates events into incidents, diagnoses root causes using a multi-agent AI workflow (orchestrated with LangGraph), generates bounded remediation proposals, enforces human approval before any state-changing action, executes only pre-approved simulated operations in an isolated Containerlab + FRRouting environment, and displays the full incident lifecycle in a React dashboard.

### Core MVP Fault Scenarios

| # | Scenario |
|---|---|
| 1 | BGP anomaly / neighbor event |
| 2 | Port flap |
| 3 | Port administrative shutdown |
| 4 | OSPF adjacency failure |
| 5 | VLAN / connectivity fault |

Stretch (after all five core scenarios work): DHCP, DNS.

---

## Architecture

```
External Dataset (Cisco Telemetry)
            ↓
Containerlab + FRR Simulation
            ↓
  ┌─────────────────────┐
  │   Ingestion Agent   │  → StructuredEvent
  └──────────┬──────────┘
             ↓
  ┌─────────────────────┐
  │  Correlation Agent  │  → IncidentTimeline
  └──────────┬──────────┘
             ↓
  ┌─────────────────────┐
  │   Topology Agent    │  → TopologyContext
  └──────┬──────────────┘
         │
  ┌──────┴──────┐   ┌──────────────┐
  │ RAG/Qdrant  │   │ Network Graph│
  └──────┬──────┘   └──────┬───────┘
         └─────────┬────────┘
                   ↓
  ┌─────────────────────┐
  │  Diagnostic Agent   │  → DiagnosisResult
  └──────────┬──────────┘
             ↓
  ┌─────────────────────┐
  │ Remediation Agent   │  → RemediationProposal
  └──────────┬──────────┘
             ↓
  ┌─────────────────────┐
  │ Oversight/Safety    │  → ApprovalState
  └──────────┬──────────┘
             ↓
      Human Approval (APPROVE / REJECT / EDIT / REQUEST MORE DIAGNOSIS)
             ↓
  ┌─────────────────────┐
  │ Simulated Executor  │  (deterministic, allow-listed ops only)
  └──────────┬──────────┘
             ↓
  ┌─────────────────────┐
  │   Verification      │  → VerificationResult
  └──────────┬──────────┘
             ↓
  Node.js API + WebSocket
             ↓
     React Dashboard
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite) |
| Backend API | Node.js + Express |
| AI Service | Python + FastAPI |
| Agent Orchestration | LangGraph |
| LLM | Configurable (OpenAI / Google / Anthropic / Ollama) |
| Vector Database | Qdrant |
| Primary Database | MongoDB |
| Network Simulation | Containerlab + FRRouting (FRR) |
| Dataset | Cisco Innovation Edge Telemetry |
| Deployment | Docker / Docker Compose |
| Communication | REST API + WebSocket (Socket.IO) |

---

## Repository Structure

```
project-root/
│
├── services/
│   ├── ai/              # Python AI service (LangGraph agents, FastAPI)
│   ├── api/             # Node.js REST + WebSocket API
│   ├── ingestion/       # Ingestion Agent module
│   ├── correlation/     # Correlation Agent module
│   ├── topology/        # Topology Agent module
│   └── rag/             # Knowledge Retrieval (RAG) Agent module
│
├── network/
│   ├── datasets/        # Cisco telemetry data + preprocessed samples
│   ├── containerlab/    # Containerlab topology definitions
│   └── generators/      # Fault scenario generators / scripts
│
├── automation/
│   └── simulated-executor/  # Deterministic allow-listed executor
│
├── frontend/            # React dashboard
│
├── database/
│   └── schemas/         # MongoDB schema definitions (Mongoose/JSON Schema)
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/        # Deterministic test data
│
├── docs/                # Architecture diagrams, ADRs, API specs
│
├── docker-compose.yml
├── .env.example
├── README.md
└── .gitignore
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker Desktop
- Git

### 1. Clone and set up environment

```bash
git clone <repo-url>
cd cnt-fault-diagnosis

cp .env.example .env
# Edit .env with your API keys and settings
```

### 2. Start infrastructure (MongoDB + Qdrant)

```bash
docker compose up -d mongodb qdrant
```

### 3. Start the Python AI service

```bash
cd services/ai
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Start the Node.js API

```bash
cd services/api
npm install
npm run dev
```

### 5. Start the React frontend

```bash
cd frontend
npm install
npm run dev
```

### 6. Health checks

```
GET http://localhost:8000/health   # Python AI service
GET http://localhost:4000/health   # Node.js API
```

---

## Development Phases

| Phase | Description | Owner |
|---|---|---|
| 0 | Repository & architecture setup | All |
| 1 | Network dataset + Containerlab/FRR foundation | Member 1 |
| 2 | Ingestion Agent | Member 1 |
| 3 | Correlation Agent | Member 1 |
| 4 | Topology Agent | Member 2 |
| 5 | RAG / Knowledge Retrieval | Member 2 |
| 6 | Diagnostic Agent | Member 3 |
| 7 | Remediation Agent | Member 3 |
| 8 | Oversight + Human Approval | Member 3 |
| 9 | Simulated Executor + Verification | Member 3 |
| 10 | Node.js API + WebSocket | Member 4 |
| 11 | React Dashboard | Member 4 |
| 12 | End-to-end integration | All |
| 13 | Evaluation and benchmarks | All |
| 14 | Testing, Docker, documentation, final demo | All |

---

## Team Structure

| Member | Responsibilities | Branch |
|---|---|---|
| Member 1 | Dataset, simulation, ingestion, correlation | `feat/member1-network-data` |
| Member 2 | Topology, RAG | `feat/member2-topology-rag` |
| Member 3 | LangGraph, diagnosis, remediation, safety | `feat/member3-ai-safety` |
| Member 4 | Node.js, React, MongoDB, WebSocket, integration | `feat/member4-platform-ui` |

Main branches: `main`, `develop`

*   **Phase 2 — Ingestion Agent Pipeline:** Validates, normalizes, sanitizes, classifies, deduplicates, and persists `RawNetworkRecord`s into deterministic `StructuredEvent`s.
*   **Phase 3 — Correlation Agent:** Deterministically groups `StructuredEvent`s into `IncidentTimeline`s using temporal sliding windows and state transitions.

## Quick Start (Demo)

### Phase 2: Ingestion CLI
To run a batch pipeline demonstrating raw log parsing to MongoDB persistence:
```bash
python -m services.ai.agents.ingestion.cli
```

### Phase 3: Correlation CLI
To correlate ingested events into incidents in MongoDB:
```bash
python -m services.ai.agents.correlation.cli
```

---

## Contracts / Schemas

All inter-agent communication uses typed, validated schemas defined in:

- Python: `services/ai/schemas/contracts.py`
- JSON Schema: `database/schemas/`

See [`docs/contracts.md`](docs/contracts.md) for the full contract reference.

---

## Security Notes

- **Never commit `.env`** — use `.env.example` as the template.
- All network log text is treated as **untrusted input** and sanitized.
- The LLM **cannot generate arbitrary shell commands** — all operations go through the allow-list in the Simulated Executor.
- Any state-changing remediation requires **explicit human approval** via the dashboard.
- Secrets are passed via **environment variables only** — never hard-coded.

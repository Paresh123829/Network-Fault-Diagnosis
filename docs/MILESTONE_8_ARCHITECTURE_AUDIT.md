# MILESTONE 8 ARCHITECTURE AUDIT
## REST APIS, REAL-TIME EVENT STREAMING & REACT FRONTEND ECOSYSTEM

**Project:** Multi-Agent AI Framework for Intelligent Network Fault Diagnosis and Safe Remediation  
**Workspace Root:** `D:\SEM5\CNT\CP`  
**Milestone:** Milestone 8 — Real-Time Streaming APIs & React Frontend  
**Audit Date:** November 13, 2026  
**Auditor:** Full-Stack & System Integration Engineering Team  

---

## 1. Executive Summary

This architecture audit establishes the exact technical baseline for Milestone 8 implementation across the Python AI backend, Node.js API Gateway, real-time streaming infrastructure, and React operator frontend.

Milestones 1 through 7 delivered robust Python backend modules for:
- Cisco MDT and syslog ingestion/normalization (M1, M2).
- LangGraph 9-stage multi-agent diagnosis and RCA orchestration (M3, M3.1, M3.1.1).
- Qdrant hybrid vector search and RAG knowledge retrieval (M4).
- Multi-layer topology graph modeling and blast radius quantification (M5, M5.1).
- Safe remediation proposal formulation, human approval gate, exact snapshots, rollback, and tamper-evident audit trails (M6, M6.1).
- Multi-protocol Containerlab topology, fault injection, and independent recovery verification (M7).

Milestone 8 builds the operational interface layer exposing these capabilities via:
1. Versioned REST API endpoints (`/api/v1/`).
2. Real-time event streaming over Socket.IO and WebSockets.
3. A responsive, production-grade React operator dashboard.

---

## 2. Current Backend Architecture Audit

### 2.1 Python AI Service (`services/ai/`)
- **Framework:** FastAPI $\ge 0.111.0$ with Uvicorn $\ge 0.29.0$, running on port 8000.
- **Data Contracts:** Strictly typed Pydantic v2 models in `services/ai/schemas/contracts.py`:
  - `StructuredEvent`, `IncidentTimeline`, `EventType`, `Severity`, `IncidentStatus`.
  - `SymptomFinding`, `SymptomAnalysisReport`, `Hypothesis`, `DiagnosisResult`.
  - `TopologyGraphModel`, `TopologyContext`, `BlastRadiusReport`.
  - `RemediationProposal`, `ApprovalDecision`, `ExecutionResult`, `VerificationResult`, `RollbackResult`.
- **Agent Engines:**
  - `services.ai.orchestrator.service.DiagnosisOrchestrator`: 9-stage LangGraph StateGraph compiler.
  - `services.ai.agents.topology.*`: Multi-layer NetworkX topology graphs, path redundancy, failure simulation, blast radius.
  - `services.rag.src.*`: Persistent Qdrant vector store and FastEmbed embeddings.
  - `services.ai.agents.oversight.approval_manager`: Proposal registration, expiration, and cryptographic approval validation.
  - `services.ai.agents.oversight.kill_switch`: Multi-scope kill switch (global, device, operation).
  - `services.ai.agents.oversight.audit_verifier`: SHA-256 hash-chain verification and HMAC external checkpointing.
  - `network.containerlab.*`: Fault injection, multi-protocol telemetry, remediation adapter, and recovery verifier.

### 2.2 Node.js API Gateway (`services/api/`)
- **Framework:** Express 4.19.2 with HTTP server, running on port 4000.
- **WebSocket Engine:** `socket.io` 4.7.5 installed and available in `node_modules`.
- **Database Driver:** `mongoose` 8.4.4 installed for MongoDB connection.
- **Testing Framework:** Jest 29.7.0 and Supertest 7.0.0.
- **Current State:** `/health` endpoint implemented; router placeholders commented out (`GAP-11`).

### 2.3 Database Ecosystem
- **MongoDB:** Database `cnt_fault_diagnosis` (and test eval `cnt_fault_diagnosis_eval`) on `mongodb://localhost:27017`.
  - Collections: `incidents`, `events`, `incident_timelines`, `diagnoses`, `remediation_proposals`, `approvals`, `execution_results`, `verification_results`, `audit_records`.
- **Qdrant:** Persistent vector storage at `services/rag/qdrant_storage` with collection `network_knowledge_base`.

---

## 3. Current Frontend Architecture Audit

### 3.1 Directory State (`frontend/`)
- **Structure:** `frontend/src/` contains 4 empty placeholder folders: `api/`, `components/`, `hooks/`, `pages/`.
- **Missing Assets (`GAP-12`):** No `package.json`, `index.html`, Vite build config, styling configuration, or React components.
- **Tooling Target:**
  - React 18 (`react`, `react-dom`).
  - Build Tool: Vite (`vite`, `@vitejs/plugin-react`).
  - Styling: Tailwind CSS (`tailwindcss`, `postcss`, `autoprefixer`) for enterprise dark-mode theme.
  - Icons & Graph Visualization: `lucide-react` for iconography, custom responsive SVG/canvas for topology graphs.
  - Real-Time Client: `socket.io-client` connecting to port 4000 / port 8000.

---

## 4. Existing API Routes & Contracts

### 4.1 Implemented Endpoints (Prior to M8)
- `GET /health` on Node.js API (`http://localhost:4000/health`): Returns `{ service: "api", status: "ok", version: "0.1.0" }`.
- `GET /health` on Python AI service (`http://localhost:8000/health`): Returns `{ service: "ai", status: "ok", version: "0.1.0", llm_provider, llm_model }`.
- `POST /knowledge/query` on Python AI service (RAG router): Returns vector passages.

### 4.2 Gaps Identified for Milestone 8
1. **Incident API:** No REST endpoints to list, filter, or fetch incident details and histories.
2. **Diagnosis API:** No endpoint to trigger LangGraph diagnosis on demand or inspect diagnostic status.
3. **Topology API:** No endpoints exposing devices, links, paths, or blast radius reports.
4. **Remediation API:** No endpoints listing proposals, handling operator approval/rejection, or reporting execution/verification status.
5. **Kill Switch API:** No endpoints exposing active kill-switch status or allowing authenticated activation/deactivation.
6. **Audit API:** No read-only endpoints exposing audit history or cryptographic chain verification.
7. **Real-Time Streaming:** Socket.IO placeholder not mounted; no domain event publisher emitting lifecycle updates.

---

## 5. Architectural Strategy for Milestone 8

To avoid unnecessary process complexity while honoring existing framework conventions:
1. **Primary REST & AI Engine (`services/ai/`):** Exposes FastAPI router `/api/v1/` implementing typed endpoints for System Status, Incidents, Diagnosis, Topology, Knowledge, Remediation, Kill Switch, and Audit, with interactive OpenAPI docs at `/docs`.
2. **Streaming Gateway (`services/api/`):** Express app on port 4000 with Socket.IO server, exposing proxy routes and broadcasting live events (`incident:created`, `diagnosis:completed`, `remediation:approved`, `kill_switch:changed`, `audit:record`) to connected clients.
3. **React Dashboard (`frontend/`):** React 18 single-page application on port 3000 consuming the REST API and Socket.IO event stream.
4. **Data Provider Transparency:** Explicit indicator reflecting whether data originates from the live Containerlab environment or the high-fidelity mock provider.

---

## 6. Gap Resolution Plan

| Gap ID | Target | Planned Milestone 8 Resolution |
|---|---|---|
| **GAP-11** | `services/api/src/index.js` | Implement Express routers (`routes/incidents.js`, `routes/approvals.js`, `routes/system.js`) and mount Socket.IO server. |
| **GAP-12** | `frontend/` | Scaffold React 18 + Vite + Tailwind CSS application with 8 operational dashboard pages. |
| **API-01** | `services/ai/` | Implement FastAPI `/api/v1` routers for incidents, diagnosis, topology, remediation, kill switch, and audit. |
| **STR-01** | `services/` | Implement Domain Event Publisher bridging agent lifecycle events to Socket.IO and WebSockets. |

---

## 7. Audit Sign-Off
Phase 0 complete. Proceeding to Phase 1 implementation.


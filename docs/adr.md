# Architecture Decision Records (ADR)

This file captures key technical decisions made during Phase 0.

---

## ADR-001: Monorepo with Flat Service Directories

**Decision**: Use a monorepo with `services/`, `network/`, `automation/`, `frontend/`, `database/`, `tests/` at the root.

**Rationale**: A flat monorepo is appropriate for a 4-person, 6-week project. It avoids the overhead of managing separate repositories while keeping code organized by responsibility.

**Consequence**: All team members work in one repo. Branch strategy (`feat/member*`) keeps work isolated.

---

## ADR-002: Pydantic v2 for Contract Schemas

**Decision**: Use Pydantic v2 models in `services/ai/schemas/contracts.py` as the canonical source of truth for all inter-agent data contracts.

**Rationale**: Pydantic provides runtime type validation, clear field documentation, and JSON serialization for free. v2 is faster than v1 and is the current standard.

**Consequence**: All Python agent code must import from `schemas.contracts`. The JSON Schema under `database/schemas/` is derived from these models.

---

## ADR-003: Configurable LLM Provider

**Decision**: The LLM provider and model are specified via `LLM_PROVIDER` and `LLM_MODEL` environment variables, with the provider abstraction implemented in `services/ai/config.py`.

**Rationale**: The project spec requires avoiding hard-coding to one provider. Using env vars makes it trivial to switch between OpenAI, Google, Anthropic, and Ollama.

**Consequence**: Agent code must not import provider-specific clients directly. A factory/adapter must be used (implemented in Phase 6).

---

## ADR-004: Simulated Executor is NOT an AI Agent

**Decision**: The remediation executor is a deterministic Python/Node.js component with a hard-coded allow-list of operations. It never receives LLM-generated shell commands.

**Rationale**: Safety requirement. The LLM must not have the ability to generate and execute arbitrary network commands.

**Consequence**: All allowed operations must be pre-defined and documented in the allow-list (implemented in Phase 9).

---

## ADR-005: Human Approval is NOT an Agent

**Decision**: Human approval is a UI gate, not an AI agent. It is implemented as a WebSocket/REST interaction between the React dashboard and the Node.js API.

**Rationale**: The spec is explicit: human approval is not an eighth agent.

**Consequence**: The approval workflow is owned by Member 4 (platform/UI), not Member 3 (AI/safety).

---

## ADR-006: Docker is not available in PATH (Phase 0 finding)

**Status**: Unresolved.

**Finding**: `docker` is not found in the system PATH on the development machine. Docker Desktop may need to be installed.

**Impact**: `docker compose up` cannot be run until Docker Desktop is installed and started.

**Action**: Team must install Docker Desktop from https://www.docker.com/products/docker-desktop/ and restart the terminal before Phase 1.

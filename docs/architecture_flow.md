# System Architecture & Flow (Phases 0 to 3)

This document provides a detailed, easily explainable walkthrough of the network fault diagnosis system's architecture, data flow, and file responsibilities built from Phase 0 to Phase 3.

---

## 1. High-Level Data Flow

The ultimate goal of the system up to this point is to reliably capture messy, unstructured network data (like router logs and telemetry statistics), clean it up, categorize it, and save it in a neat, standardized format into our database so that future AI agents (Phase 3+) can easily analyze it.

Here is the exact journey a piece of network data takes:

```mermaid
graph TD
    A[Raw Network Sources\n(Cisco Dataset / FRR Simulation)] -->|Reads files/streams| B(Adapter Layer)
    B -->|Yields| C[RawNetworkRecord]
    
    subgraph Ingestion Agent Pipeline [Phase 2: Ingestion Agent]
        C --> D[Validator]
        D -->|Validates required fields| E[Normalizer]
        E -->|Fixes timestamps/strings| F[Classifier]
        F -->|Identifies MVP Event Types| G[Deduplicator]
        G -->|Generates deterministic SHA-256| H[StructuredEvent]
    end
    
    H -->|Provides canonical model| I[(MongoDB)]
    
    subgraph Correlation Agent Pipeline [Phase 3: Correlation Agent]
        I -->|Reads StructuredEvents| J[Correlation Service]
        J -->|Temporal & Context Matching| K[Correlation Algorithm]
        K -->|Groups into Incidents| L[IncidentTimeline]
    end
    
    L -->|Upserts Incident| I
```

---

## 2. Phase Breakdown & File Responsibilities

### Phase 0: The Foundation
Phase 0 established the "rules of the system." It created the standard data models (contracts) that all future components must strictly follow, along with the database infrastructure.

*   **`services/ai/schemas/contracts.py`**
    *   **What it does:** Defines the "Canonical Contracts" using Pydantic. It contains `StructuredEvent` (how an event must look in the database), `EventType` (enums like `PORT_DOWN`, `BGP_NEIGHBOR_UP`), and `Severity`.
    *   **Why it matters:** Ensures every part of the system speaks the exact same language.
*   **`database/schemas/01_init.js`**
    *   **What it does:** The MongoDB initialization script. It creates the `events` collection and sets up a unique index on the `event_id` field.
*   **`docker-compose.yml`**
    *   **What it does:** Spins up MongoDB (for structured events) and Qdrant (for vector embeddings in future phases).

### Phase 1: Data Acquisition & Simulation
Phase 1 was about getting our hands on real and simulated network data without letting its messiness pollute the rest of our system.

*   **`network/datasets/adapters/raw_record.py`**
    *   **What it does:** Defines `RawNetworkRecord`. This is a transitional "messy" data container. It holds data exactly as it was found in the logs or CSV files before any real cleanup happens.
*   **`network/datasets/adapters/cisco_adapter.py`**
    *   **What it does:** The `CiscoTelemetryAdapter` class knows exactly how to open the zipped Cisco telemetry CSVs and raw IOS-XR syslog files. It reads these complex files line-by-line and packages them into `RawNetworkRecord`s.
*   **`network/containerlab/` (Directory)**
    *   **What it does:** Contains the infrastructure to spin up a simulated 3-router FRRouting (FRR) network locally using Docker. This allows us to inject real network faults dynamically if we don't want to use the static Cisco dataset.

### Phase 2: The Ingestion Agent
Phase 2 built the actual pipeline that takes a `RawNetworkRecord` and transforms it into a perfectly clean `StructuredEvent`. It is located entirely in `services/ai/agents/ingestion/`.

*   **`service.py`** (The Orchestrator)
    *   **What it does:** Contains the `IngestionService`. It acts as the manager. It receives a batch of `RawNetworkRecord`s and passes each record through the pipeline stages (validator → normalizer → classifier → deduplicator), ultimately creating `StructuredEvent`s and passing them to persistence.
*   **`validator.py`** (The Gatekeeper)
    *   **What it does:** Checks if a record has the bare minimum data to survive (e.g., does it have a device name? A timestamp?). If not, it throws a `ValidationError` and drops the record, protecting the database from garbage.
*   **`normalizer.py`** (The Cleaner)
    *   **What it does:** Standardizes formats. It converts messy, yearless Cisco timestamps (e.g., `Aug 4 10:19:44`) or raw millisecond epochs into standard UTC Python `datetime` objects. It also standardizes interface names (e.g., changing `Hu0/0` to `HundredGigE0/0`) and strips hidden control characters out of text.
*   **`classifier.py`** (The Categorizer)
    *   **What it does:** Uses fast, deterministic rules (regex and keyword matching) to map raw log text into our 5 MVP scenarios. For example, if it sees `%ROUTING-BGP-5-ADJCHANGE : neighbor 1.1.1.1 Down`, it classifies it as `EventType.BGP_NEIGHBOR_DOWN`.
*   **`deduplicator.py`** (The Bouncer)
    *   **What it does:** Computes a highly specific SHA-256 hash (`event_id`) based on the event's timestamp, device, interface, classification, and source file line number. 
    *   **Why it matters:** If we process the same dataset twice, this hash guarantees we don't insert duplicate events into the database (idempotency).
*   **`persistence.py`** (The Writer)
    *   **What it does:** Connects to MongoDB via `pymongo` and attempts to insert the clean `StructuredEvent`. If MongoDB complains about a `DuplicateKeyError` (because the `event_id` hash already exists), it safely catches the error and ignores it.
*   **`cli.py`** (The Demo)
    *   **What it does:** A command-line script to easily test and demonstrate the entire pipeline from end-to-end without needing to write external scripts.

### Phase 3: The Correlation Agent
Phase 3 takes the standardized events from Phase 2 and logically groups related events together into a single `IncidentTimeline`. This provides context (e.g. an interface going down and bringing a BGP peer down with it) rather than just a stream of isolated events. It is located in `services/ai/agents/correlation/`.

*   **`service.py`** (The Orchestrator)
    *   **What it does:** The `CorrelationService` reads chronologically sorted `StructuredEvent`s from MongoDB in batches and manages the correlation pipeline.
*   **`algorithm.py`** (The Brain)
    *   **What it does:** The purely deterministic engine that decides if an event belongs to an ongoing incident. It uses a temporal sliding window (e.g., 120 seconds) anchored to the fault's root event. It enforces strict context matching (events must share the same device and either the same interface or protocol) to prevent over-correlation. Cross-device correlation is disabled here to defer to topology awareness in later phases. It also natively detects fault recoveries (e.g., matching a BGP DOWN with its corresponding BGP UP).
*   **`persistence.py`** (The Writer)
    *   **What it does:** Idempotently persists `IncidentTimeline`s back to MongoDB using deterministic IDs and `upsert` operations. If a script is run twice, it updates the existing incident safely rather than spawning duplicates.
*   **`cli.py`** (The Demo)
    *   **What it does:** A command-line script that connects to MongoDB, correlates the stored events, and outputs a summary of incidents created, updated, and closed.

---

## 3. Summary of the Goal Achieved
By the end of Phase 3, we have a highly robust, purely deterministic (no LLM hallucinations) ingestion and correlation pipeline. The messy network world is successfully hidden behind the Ingestion Agent, and the Correlation Agent logically groups related symptoms together. This means that when we build the LLM-powered Diagnostic Agents in future phases, they will only ever have to deal with perfectly formatted, contextualized `IncidentTimeline`s pulled directly from MongoDB.

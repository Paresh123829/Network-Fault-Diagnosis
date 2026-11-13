# Phase 3: Correlation Agent

## 1. Purpose
The Correlation Agent is responsible for determining which `StructuredEvent`s belong together as a single network incident. It outputs an `IncidentTimeline` that tracks the temporal history of the fault and groups contextually related events (e.g., interface failure on a router and BGP neighbor dropping on that same router). 

It specifically avoids inferring **root cause**. Its job is to provide contextual sequence tracking for the downstream Diagnostic Agent.

## 2. Input and Output
- **Input:** Chronologically ordered `StructuredEvent`s (from MongoDB `events` collection).
- **Output:** `IncidentTimeline` (saved to MongoDB `incident_timelines` collection).

## 3. Correlation Signals
The agent groups events using deterministic rules without involving LLMs:
1. **Rule A (Same Device/Interface):** Strong correlation if events affect the same `device_id` and `interface` within the temporal window.
2. **Rule B (Same Device/Protocol):** Correlation if events share a `protocol_hint` (e.g., bgp) on the same device.
3. **Rule C (Temporal Proximity):** Events must occur within `CORRELATION_WINDOW_SECONDS` (default: 120s) of each other.

## 4. Incident Lifecycle & Recovery Detection
- **OPEN**: Assigned when an incident starts. Stays open while events continue to arrive within the time window.
- **CLOSED**:
  - The window natively expires.
  - A deterministic recovery event is detected (e.g., `BGP_NEIGHBOR_DOWN` is followed by `BGP_NEIGHBOR_UP` on the same device).

## 5. Incident ID Strategy & Idempotency
To ensure deterministic reruns over the same dataset, the `incident_id` is derived directly from the ID of the first (root) event that triggered the incident creation (`inc_{root_event_id}`). 
This guarantees idempotency because updating the incident merely triggers a MongoDB `upsert` on the same `incident_id` rather than spawning duplicates.

## 6. Persistence & Error Handling
All `IncidentTimeline`s are persisted to MongoDB using bulk `UpdateOne(upsert=True)` statements. Any malformed events or DB connection issues will be logged gracefully, rejecting the batch without crashing the agent.

## 7. Configuration
- `MONGO_URI`: The MongoDB connection URI (default `mongodb://localhost:27017`).
- `MONGO_DB_NAME`: The database name (default `cnt_fault_diagnosis`).
- `CORRELATION_WINDOW_SECONDS`: The sliding temporal correlation window (default `120`).

## 8. CLI Usage
Run the pipeline batch against the database:
```bash
python -m services.ai.agents.correlation.cli --window 120 --limit 1000
```

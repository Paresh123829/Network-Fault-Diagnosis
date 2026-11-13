# Ingestion Agent Pipeline

The Ingestion Agent forms Phase 2 of the intelligent fault diagnosis system. It serves as the boundary between raw network observations and the canonical data model used by downstream reasoning agents.

## Purpose
The primary purpose is to transform `RawNetworkRecord` instances into `StructuredEvent` instances, while applying validation, normalization, sanitization, classification, and deduplication logic deterministically (without using an LLM).

## Input and Output
*   **Input**: `RawNetworkRecord` (from adapters like `CiscoTelemetryAdapter`).
*   **Output**: `StructuredEvent` saved to a MongoDB `events` collection.

## Processing Pipeline

### 1. Validation
The `validator.py` ensures the incoming record is not malformed. It requires a `device_id`, a timestamp, and a `source_record_id`. Syslog entries are required to have a `raw_message`. Invalid records raise a `ValidationError` which the pipeline logs and quarantines, allowing batch ingestion to continue uninterrupted.

### 2. Normalization
The `normalizer.py` ensures equivalent fields use the same strings:
*   **Timestamps**: Converts both Cisco MDT epoch strings and IOS-XR syslog string formats (`Aug 4 10:19:44.199`) into standard timezone-aware UTC Python `datetime` objects.
*   **Device IDs**: Lowercased and whitespace stripped.
*   **Interfaces**: Expanded from common abbreviations (e.g., `Hu0/0/0/16` → `HundredGigE0/0/0/16`).

### 3. Sanitization
The normalizer also strips potential unprintable control characters from payload messages to prevent downstream processing errors.

### 4. Event Classification
The `classifier.py` deterministically maps raw protocol hints, MDT payloads, and syslog strings into canonical `EventType`s and `Severity` levels defined in Phase 0. It explicitly supports the 5 MVP scenarios (BGP anomaly, Port flap, Port admin shutdown, OSPF adjacency failure, VLAN/connectivity fault). It does *not* do root-cause analysis (e.g., an interface down is simply classified as an interface down, leaving reasoning to the future Diagnostic Agent).

### 5. Deduplication
The `deduplicator.py` enforces idempotency. It hashes the `timestamp`, `device_id`, `event_type`, `interface`, and a text fingerprint to generate a UUID-like deterministic `event_id`.

### 6. Persistence
`persistence.py` handles writing to MongoDB. It uses `pymongo` to connect to the database. By utilizing a unique index on the MongoDB collection for `event_id`, duplicates across multiple ingestion runs are naturally prevented with `DuplicateKeyError`.

## Error Handling
Record-level errors (validation, parse issues) are caught and tallied as "rejected" or "errors" in the `IngestionResult`, allowing the rest of the batch to succeed. System-level errors (database offline) will fail the batch immediately.

## Example Ingestion Flow (CLI)
You can test the pipeline using the provided CLI which loads fixtures from Phase 1:

```bash
python -m services.ai.agents.ingestion.cli
```

This will output a summary showing how many records were processed, rejected, and persisted.

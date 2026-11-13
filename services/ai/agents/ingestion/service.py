from __future__ import annotations

import logging
from typing import Iterable, Iterator

from network.datasets.adapters.raw_record import RawNetworkRecord
from services.ai.schemas.contracts import StructuredEvent
from services.ai.agents.ingestion.models import IngestionResult
from services.ai.agents.ingestion.validator import validate_record, ValidationError
from services.ai.agents.ingestion.normalizer import (
    normalize_timestamp,
    normalize_device_id,
    normalize_interface,
    sanitize_string,
)
from services.ai.agents.ingestion.classifier import classify_event
from services.ai.agents.ingestion.deduplicator import compute_event_id
from services.ai.agents.ingestion.persistence import IngestionPersistence

logger = logging.getLogger(__name__)


class IngestionService:
    """
    Orchestrates the ingestion pipeline.
    """

    def __init__(self, persistence: IngestionPersistence):
        self.persistence = persistence

    def process_record(self, raw_record: RawNetworkRecord) -> StructuredEvent:
        """
        Passes a single record through validation, normalization, classification,
        and deduplication to yield a StructuredEvent.
        """
        # 1. Validation
        validate_record(raw_record)

        # 2. Normalization
        timestamp = normalize_timestamp(raw_record.timestamp_utc, raw_record.raw_timestamp_str)
        device_id = normalize_device_id(raw_record.device_id)
        
        # Try to infer interface if not provided explicitly, then normalize
        raw_interface = raw_record.telemetry_fields.get("interface-name") if raw_record.telemetry_fields else None
        # Fallback to looking in the message string for something resembling an interface
        if not raw_interface and raw_record.raw_message:
            # Simple heuristic: if word starts with 'HundredGigE' or 'GigabitEthernet' etc.
            import re
            match = re.search(r'(HundredGigE\S+|GigabitEthernet\S+|Hu\d+/\d+/\d+/\d+|Gi\d+/\d+/\d+/\d+|eth\d+)', raw_record.raw_message, re.IGNORECASE)
            if match:
                raw_interface = match.group(1)
                
        interface = normalize_interface(raw_interface)

        # 3. Sanitization
        raw_message = sanitize_string(raw_record.raw_message)

        # 4. Classification
        event_type, severity = classify_event(raw_record)

        # 5. Deduplication
        event_id = compute_event_id(
            timestamp=timestamp,
            device_id=device_id,
            event_type=event_type,
            interface=interface,
            raw_message=raw_message,
            payload=raw_record.telemetry_fields,
            source_record_id=raw_record.source_record_id
        )

        # 6. StructuredEvent Creation
        normalized_fields = {}
        if raw_message:
            normalized_fields["raw_message"] = raw_message
        if raw_record.telemetry_fields:
            normalized_fields["telemetry_fields"] = raw_record.telemetry_fields
        if raw_record.protocol_hint:
            normalized_fields["protocol_hint"] = raw_record.protocol_hint
        if raw_record.event_hint:
            normalized_fields["event_hint"] = raw_record.event_hint

        return StructuredEvent(
            event_id=event_id,
            timestamp=timestamp,
            device_id=device_id,
            interface=interface,
            event_type=event_type,
            severity=severity,
            normalized_fields=normalized_fields,
            raw_reference=raw_record.source_record_id
        )

    def process_batch(self, records: Iterable[RawNetworkRecord]) -> IngestionResult:
        """
        Processes a batch (or stream) of records, persisting valid ones,
        and returns an aggregated result.
        """
        result = IngestionResult()
        
        # Ensure DB is reachable before starting a large batch
        if not self.persistence.check_connection():
            result.errors.append("SYSTEM-LEVEL FAILURE: Database is unreachable.")
            return result

        logger.info("Starting ingestion batch...")

        for record in records:
            result.records_received += 1
            
            try:
                # Process
                event = self.process_record(record)
                result.records_valid += 1
                result.events_created += 1
                
                # Persist
                persisted = self.persistence.insert_event(event)
                if persisted:
                    result.events_persisted += 1
                else:
                    result.duplicates_prevented += 1
                    
            except ValidationError as e:
                result.records_rejected += 1
                # Log at debug so we don't spam for standard malformed records
                logger.debug(f"Record {record.source_record_id} rejected: {e}")
            except Exception as e:
                # Catch-all for unexpected processing or DB errors on a specific record
                result.records_rejected += 1
                result.persistence_failures += 1
                err_msg = f"RECORD-LEVEL FAILURE: {record.source_record_id} failed: {e}"
                logger.warning(err_msg)
                result.errors.append(err_msg)

        logger.info(f"Ingestion batch completed. Persisted {result.events_persisted} events.")
        return result

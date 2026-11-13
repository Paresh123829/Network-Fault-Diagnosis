"""
Ingestion Agent Pipeline.

Converts RawNetworkRecords into canonical StructuredEvents and 
persists them into the MongoDB 'events' collection.
"""

from services.ai.agents.ingestion.models import IngestionResult
from services.ai.agents.ingestion.validator import validate_record, ValidationError
from services.ai.agents.ingestion.normalizer import (
    normalize_timestamp, 
    normalize_device_id, 
    normalize_interface, 
    sanitize_string
)
from services.ai.agents.ingestion.classifier import classify_event
from services.ai.agents.ingestion.deduplicator import compute_event_id
from services.ai.agents.ingestion.persistence import IngestionPersistence
from services.ai.agents.ingestion.service import IngestionService

__all__ = [
    "IngestionResult",
    "validate_record",
    "ValidationError",
    "normalize_timestamp",
    "normalize_device_id",
    "normalize_interface",
    "sanitize_string",
    "classify_event",
    "compute_event_id",
    "IngestionPersistence",
    "IngestionService"
]

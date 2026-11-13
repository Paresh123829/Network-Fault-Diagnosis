from __future__ import annotations

from typing import Optional

from network.datasets.adapters.raw_record import RawNetworkRecord


class ValidationError(Exception):
    """Raised when a RawNetworkRecord fails validation."""
    pass


def validate_record(record: RawNetworkRecord) -> None:
    """
    Validates a RawNetworkRecord for the minimum requirements needed
    to construct a StructuredEvent.

    Raises:
        ValidationError: if the record is malformed or missing required fields.
    """
    if not record.device_id or not record.device_id.strip():
        raise ValidationError("Record is missing a valid device_id.")

    if not record.timestamp_utc and not record.raw_timestamp_str:
        raise ValidationError("Record is missing both timestamp_utc and raw_timestamp_str.")

    if not record.source_record_id or not record.source_record_id.strip():
        raise ValidationError("Record is missing source_record_id.")
    
    # Syslog records must have a raw message
    if record.source.value.endswith("_syslog") and not record.raw_message:
        raise ValidationError("Syslog record missing raw_message.")

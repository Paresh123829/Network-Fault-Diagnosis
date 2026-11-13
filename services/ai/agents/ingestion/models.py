from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class IngestionResult:
    """
    Tracks metrics for a batch ingestion run.
    """
    records_received: int = 0
    records_valid: int = 0
    records_rejected: int = 0
    duplicates_prevented: int = 0
    events_created: int = 0
    events_persisted: int = 0
    persistence_failures: int = 0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Ingestion Result:\n"
            f"  Received: {self.records_received}\n"
            f"  Valid: {self.records_valid}\n"
            f"  Rejected: {self.records_rejected}\n"
            f"  Events Created: {self.events_created}\n"
            f"  Persisted: {self.events_persisted}\n"
            f"  Duplicates Prevented: {self.duplicates_prevented}\n"
            f"  Persistence Failures: {self.persistence_failures}\n"
            f"  Errors: {len(self.errors)}"
        )

import logging
from typing import List, Optional

from services.ai.schemas.contracts import StructuredEvent, IncidentTimeline
from .models import CorrelationResult
from .algorithm import CorrelationAlgorithm
from .persistence import CorrelationPersistence

logger = logging.getLogger(__name__)

class CorrelationService:
    def __init__(self, persistence: Optional[CorrelationPersistence] = None, window_seconds: int = 120):
        self.persistence = persistence or CorrelationPersistence()
        self.algorithm = CorrelationAlgorithm(window_seconds=window_seconds)

    def process_batch(self, events: List[StructuredEvent]) -> CorrelationResult:
        """
        Processes a batch of chronologically ordered StructuredEvents.
        Returns a CorrelationResult outlining what happened.
        """
        result = CorrelationResult()
        
        if not events:
            return result
            
        result.events_processed = len(events)
        logger.info(f"Processing batch of {len(events)} events for correlation.")
        
        try:
            # 1. Fetch currently open incidents from the DB
            open_incidents = self.persistence.get_open_incidents()
        except Exception as e:
            logger.error(f"Failed to fetch open incidents: {e}")
            result.errors.append(str(e))
            return result
            
        # 2. Run the algorithm
        modified_or_new = self.algorithm.group_events(events, open_incidents)
        
        # 3. Persist the results
        if modified_or_new:
            try:
                upserted, modified = self.persistence.upsert_incidents(modified_or_new)
                
                # Calculate metrics
                # Since an upsert creates a new document if it doesn't exist, upserted = new incidents.
                # modified = existing incidents that were updated.
                result.incidents_created = upserted
                result.incidents_updated = modified
                
                # We can manually count how many of the modified_or_new were CLOSED during this run
                closed_count = sum(1 for inc in modified_or_new if inc.status.value == "closed")
                result.incidents_closed = closed_count
                
                logger.info(f"Upserted {upserted} new incidents, updated {modified} existing incidents. ({closed_count} closed)")
            except Exception as e:
                logger.error(f"Failed to persist incidents: {e}")
                result.errors.append(str(e))
                
        return result

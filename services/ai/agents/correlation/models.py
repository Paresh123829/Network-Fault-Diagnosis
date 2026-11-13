import os
from typing import List, Optional
from pydantic import BaseModel, Field

# Configuration can be passed in, but we can set defaults here.
DEFAULT_CORRELATION_WINDOW_SECONDS = int(os.environ.get("CORRELATION_WINDOW_SECONDS", 120))


class CorrelationResult(BaseModel):
    """
    Result model for a single batch run of the Correlation Agent.
    """
    events_processed: int = 0
    incidents_created: int = 0
    incidents_updated: int = 0
    incidents_closed: int = 0
    errors: List[str] = Field(default_factory=list)

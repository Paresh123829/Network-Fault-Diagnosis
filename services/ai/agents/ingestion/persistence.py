from __future__ import annotations

import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from services.ai.config import get_settings
from services.ai.schemas.contracts import StructuredEvent

logger = logging.getLogger(__name__)


class IngestionPersistence:
    """
    Handles MongoDB persistence for StructuredEvents.
    """

    def __init__(self, db_name: Optional[str] = None, collection_name: str = "events"):
        settings = get_settings()
        self.client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or settings.mongo_db]
        self.collection = self.db[collection_name]

    def insert_event(self, event: StructuredEvent) -> bool:
        """
        Attempts to insert the event into MongoDB.
        Returns True if successful.
        Returns False if a duplicate key (event_id) prevented insertion.
        Raises an exception if the database is unreachable or another error occurs.
        """
        doc = event.model_dump()
        try:
            self.collection.insert_one(doc)
            return True
        except DuplicateKeyError:
            return False

    def check_connection(self) -> bool:
        """Pings the database to ensure availability."""
        try:
            self.client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

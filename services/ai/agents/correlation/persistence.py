import os
import logging
from typing import List, Optional
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError

from services.ai.schemas.contracts import IncidentTimeline

logger = logging.getLogger(__name__)

class CorrelationPersistence:
    def __init__(self, mongo_uri: Optional[str] = None, db_name: Optional[str] = None):
        self.mongo_uri = mongo_uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name or os.environ.get("MONGO_DB_NAME", "cnt_fault_diagnosis")
        self.client = None
        self.db = None
        self.collection = None

    def connect(self):
        if not self.client:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.db_name]
            self.collection = self.db["incident_timelines"]
            # Verify connection
            self.client.admin.command('ping')
            logger.info(f"Connected to MongoDB at {self.mongo_uri}, database: {self.db_name}")

    def upsert_incidents(self, incidents: List[IncidentTimeline]) -> tuple[int, int]:
        """
        Upserts a list of IncidentTimelines to MongoDB.
        Uses incident_id as the unique key.
        Returns (upserted_count, modified_count).
        """
        if not incidents:
            return 0, 0

        if not self.client:
            self.connect()

        operations = []
        for incident in incidents:
            doc = incident.model_dump(mode='json')
            operations.append(
                UpdateOne(
                    {"incident_id": incident.incident_id},
                    {"$set": doc},
                    upsert=True
                )
            )

        try:
            result = self.collection.bulk_write(operations, ordered=False)
            return result.upserted_count, result.modified_count
        except PyMongoError as e:
            logger.error(f"Failed to upsert incidents: {e}")
            raise
            
    def get_open_incidents(self) -> List[IncidentTimeline]:
        """
        Retrieves all currently OPEN incidents.
        """
        if not self.client:
            self.connect()
            
        try:
            cursor = self.collection.find({"status": "open"})
            return [IncidentTimeline(**doc) for doc in cursor]
        except PyMongoError as e:
            logger.error(f"Failed to fetch open incidents: {e}")
            raise

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

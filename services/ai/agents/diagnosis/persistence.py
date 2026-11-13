"""
persistence.py — MongoDB Persistence for Structured Diagnosis Results.

Persists DiagnosisResult documents linking incident timeline, source events,
topology context, symptom findings, and RCA hypotheses with complete provenance.
Guarantees idempotency and deduplication.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from pymongo import MongoClient, UpdateOne
from datetime import datetime, timezone

from services.ai.schemas.contracts import (
    DiagnosisResult,
    IncidentTimeline,
    TopologyContext,
)
from services.ai.agents.symptom.models import SymptomAnalysisReport

logger = logging.getLogger(__name__)


class DiagnosisPersistence:
    """
    MongoDB persistence manager for multi-agent diagnostic records.
    """

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collection_name: str = "diagnosis_results"
    ):
        self.mongo_uri = mongo_uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name or os.environ.get("MONGO_DB_NAME", "cnt_fault_diagnosis_eval")
        self.collection_name = collection_name
        self._client: Optional[MongoClient] = None

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            self._client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=3000)
        return self._client

    @property
    def collection(self):
        return self.client[self.db_name][self.collection_name]

    def check_connection(self) -> bool:
        """Pings MongoDB to ensure connectivity."""
        try:
            self.client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning(f"MongoDB connection check failed: {e}")
            return False

    def save_diagnosis(
        self,
        incident_id: str,
        timeline: IncidentTimeline,
        diagnosis: DiagnosisResult,
        symptom_report: Optional[SymptomAnalysisReport] = None,
        topology_context: Optional[TopologyContext] = None,
        execution_trace: Optional[List[str]] = None
    ) -> bool:
        """
        Idempotently persists or updates a DiagnosisResult document with rich provenance.
        """
        try:
            doc = diagnosis.model_dump(mode="json")
            doc["_id"] = incident_id
            doc["incident_id"] = incident_id
            doc["incident_timeline"] = timeline.model_dump(mode="json")
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            if symptom_report:
                doc["symptom_report"] = symptom_report.model_dump(mode="json")
            if topology_context:
                doc["topology_context"] = topology_context.model_dump(mode="json")
            if execution_trace:
                doc["execution_trace"] = execution_trace

            # Upsert by incident_id
            self.collection.replace_one({"_id": incident_id}, doc, upsert=True)
            logger.info(f"Successfully persisted diagnosis for incident '{incident_id}' into {self.db_name}.{self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to persist diagnosis for incident '{incident_id}': {e}")
            return False

    def get_diagnosis(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a persisted diagnosis by incident_id."""
        try:
            return self.collection.find_one({"_id": incident_id})
        except Exception as e:
            logger.error(f"Failed to fetch diagnosis for incident '{incident_id}': {e}")
            return None

    def list_diagnoses(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists recently persisted diagnoses."""
        try:
            return list(self.collection.find().sort("updated_at", -1).limit(limit))
        except Exception as e:
            logger.error(f"Failed to list diagnoses: {e}")
            return []


import pytest
import os
from pymongo import MongoClient

from network.datasets.adapters.cisco_adapter import CiscoTelemetryAdapter
from services.ai.config import get_settings
from services.ai.agents.ingestion.persistence import IngestionPersistence
from services.ai.agents.ingestion.service import IngestionService


@pytest.fixture(scope="module")
def mongo_collection():
    settings = get_settings()
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command('ping')
    except Exception:
        pytest.skip("ENVIRONMENT LIMITATION: MongoDB is not available.")
        
    db = client["cnt_test_diagnosis"]
    collection = db["test_events"]
    
    # Ensure empty state and create index
    collection.delete_many({})
    collection.create_index("event_id", unique=True)
    
    yield collection
    
    # Cleanup after
    collection.delete_many({})
    client.close()


@pytest.fixture(scope="module")
def persistence(mongo_collection):
    p = IngestionPersistence(db_name="cnt_test_diagnosis", collection_name="test_events")
    # Replace the collection reference to ensure we use our isolated test collection
    p.collection = mongo_collection 
    return p


def test_mongodb_connection(persistence):
    assert persistence.check_connection() is True


def test_end_to_end_ingestion_fixture(persistence, mongo_collection):
    service = IngestionService(persistence)
    adapter = CiscoTelemetryAdapter()
    
    # Load case 3 syslogs and csvs from fixture
    syslog_records = list(adapter.iter_syslog_records(case="3"))
    
    # Process batch
    result = service.process_batch(syslog_records)
    
    assert result.records_received > 0
    assert result.errors == []
    
    # Check that events were actually persisted
    count = mongo_collection.count_documents({})
    assert count == result.events_persisted
    
    # If we run it again, everything should be a duplicate
    result_dup = service.process_batch(syslog_records)
    assert result_dup.events_created == len(syslog_records)
    assert result_dup.events_persisted == 0
    assert result_dup.duplicates_prevented == len(syslog_records)

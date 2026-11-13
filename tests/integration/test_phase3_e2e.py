import pytest
import os
from pymongo import MongoClient

from network.datasets.adapters.cisco_adapter import CiscoTelemetryAdapter
from services.ai.agents.ingestion.service import IngestionService
from services.ai.agents.correlation.service import CorrelationService
from services.ai.agents.correlation.persistence import CorrelationPersistence


def get_test_mongo_uri():
    return os.environ.get("MONGO_URI", "mongodb://localhost:27017")


@pytest.fixture
def mongo_dbs():
    client = MongoClient(get_test_mongo_uri(), serverSelectionTimeoutMS=2000)
    try:
        client.admin.command('ping')
    except Exception as e:
        pytest.skip(f"MongoDB unavailable: {e}")
        
    db = client["cnt_test_e2e"]
    db.events.delete_many({})
    db.incident_timelines.delete_many({})
    
    yield db
    client.close()


def test_full_e2e_correlation(mongo_dbs, tmp_path):
    # This E2E test runs Phase 1 adapter, Phase 2 ingestion, and Phase 3 correlation
    
    # We will use Case 3 (BGP Flap) because it's a perfect correlation scenario
    case3_id = "case_3_bgpclear_no_traffic"
    
    # 1. Adapter (Phase 1)
    adapter = CiscoTelemetryAdapter()
    
    # Grab the ground truth fixture
    fixture_path = os.path.join("tests", "fixtures", "cisco_sample_records.json")
    if not os.path.exists(fixture_path):
        pytest.skip("Sample records fixture not found.")
        
    records = list(adapter.iter_syslog_records(case="3"))
    
    # 2. Ingestion (Phase 2)
    # Configure ingestion to write to our test DB
    os.environ["MONGO_URI"] = get_test_mongo_uri()
    from services.ai.agents.ingestion.persistence import IngestionPersistence
    ing_persistence = IngestionPersistence(db_name="cnt_test_e2e")
    ingestion_service = IngestionService(persistence=ing_persistence)
    
    ingestion_result = ingestion_service.process_batch(records)
    assert ingestion_result.events_persisted > 0
    
    # 3. Fetch structured events
    from services.ai.schemas.contracts import StructuredEvent
    cursor = mongo_dbs.events.find().sort("timestamp", 1)
    events = [StructuredEvent(**doc) for doc in cursor]
    
    assert len(events) == ingestion_result.events_persisted
    
    # 4. Correlation (Phase 3)
    corr_persistence = CorrelationPersistence(mongo_uri=get_test_mongo_uri(), db_name="cnt_test_e2e")
    correlation_service = CorrelationService(persistence=corr_persistence, window_seconds=120)
    
    corr_result = correlation_service.process_batch(events)
    
    # Verify correlation happened
    assert corr_result.events_processed == len(events)
    assert corr_result.incidents_created > 0
    
    # Fetch incidents
    incidents_cursor = mongo_dbs.incident_timelines.find()
    incidents = list(incidents_cursor)
    
    assert len(incidents) > 0
    
    # Check that at least one incident grouped multiple events
    max_events_in_incident = max(len(inc["events"]) for inc in incidents)
    assert max_events_in_incident > 1, "Expected at least one multi-event incident"

    # Verify idempotency
    corr_result_2 = correlation_service.process_batch(events)
    assert corr_result_2.incidents_created == 0 # no new incidents created
    assert corr_result_2.incidents_updated > 0  # they were updated in place
    
    # Verify counts didn't increase
    incidents_count = mongo_dbs.incident_timelines.count_documents({})
    assert incidents_count == len(incidents)

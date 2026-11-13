import pytest
import os
from pymongo import MongoClient
from datetime import datetime, timezone

from services.ai.schemas.contracts import StructuredEvent, EventType, Severity, IncidentTimeline, TimeWindow, IncidentStatus
from services.ai.agents.correlation.persistence import CorrelationPersistence


def get_test_mongo_uri():
    return os.environ.get("MONGO_URI", "mongodb://localhost:27017")


@pytest.fixture
def mongo_collection():
    client = MongoClient(get_test_mongo_uri(), serverSelectionTimeoutMS=2000)
    try:
        client.admin.command('ping')
    except Exception as e:
        pytest.skip(f"MongoDB unavailable: {e}")
        
    db = client["cnt_test_correlation"]
    collection = db["incident_timelines"]
    collection.delete_many({})
    collection.create_index("incident_id", unique=True)
    yield collection
    client.close()

@pytest.fixture
def persistence(mongo_collection):
    p = CorrelationPersistence(mongo_uri=get_test_mongo_uri(), db_name="cnt_test_correlation")
    yield p
    p.close()

def make_test_incident(incident_id: str) -> IncidentTimeline:
    ts = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ev = StructuredEvent(
        event_id="e1",
        timestamp=ts,
        device_id="r1",
        event_type=EventType.PORT_DOWN,
        severity=Severity.HIGH,
        raw_reference="test"
    )
    return IncidentTimeline(
        incident_id=incident_id,
        time_window=TimeWindow(start=ts, end=ts),
        events=[ev],
        affected_devices=["r1"]
    )


class TestCorrelationPersistence:
    
    def test_upsert_new_incident(self, persistence, mongo_collection):
        inc = make_test_incident("inc_1")
        upserted, modified = persistence.upsert_incidents([inc])
        
        assert upserted == 1
        assert modified == 0
        
        doc = mongo_collection.find_one({"incident_id": "inc_1"})
        assert doc is not None
        assert doc["incident_id"] == "inc_1"

    def test_upsert_existing_incident(self, persistence, mongo_collection):
        inc = make_test_incident("inc_1")
        persistence.upsert_incidents([inc])
        
        # Modify and upsert again
        inc.affected_devices.append("r2")
        upserted, modified = persistence.upsert_incidents([inc])
        
        # It's an update
        assert upserted == 0
        assert modified == 1
        
        doc = mongo_collection.find_one({"incident_id": "inc_1"})
        assert "r2" in doc["affected_devices"]

    def test_get_open_incidents(self, persistence):
        inc1 = make_test_incident("inc_1")
        inc2 = make_test_incident("inc_2")
        inc2.status = IncidentStatus.CLOSED
        
        persistence.upsert_incidents([inc1, inc2])
        
        open_incs = persistence.get_open_incidents()
        assert len(open_incs) == 1
        assert open_incs[0].incident_id == "inc_1"

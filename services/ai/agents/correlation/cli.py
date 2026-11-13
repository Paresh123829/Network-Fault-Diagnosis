import argparse
import logging
from pymongo import MongoClient

from services.ai.agents.correlation.service import CorrelationService
from services.ai.agents.correlation.persistence import CorrelationPersistence
from services.ai.schemas.contracts import StructuredEvent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Correlation Agent CLI")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017", help="MongoDB URI")
    parser.add_argument("--db-name", default="cnt_fault_diagnosis", help="MongoDB Database Name")
    parser.add_argument("--window", type=int, default=120, help="Correlation window in seconds")
    parser.add_argument("--limit", type=int, default=1000, help="Limit number of events to fetch")
    args = parser.parse_args()

    logger.info("Initializing Correlation Agent...")
    persistence = CorrelationPersistence(mongo_uri=args.mongo_uri, db_name=args.db_name)
    service = CorrelationService(persistence=persistence, window_seconds=args.window)

    logger.info("Connecting to MongoDB to fetch events...")
    try:
        client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[args.db_name]
        # Fetch events chronologically
        cursor = db["events"].find().sort("timestamp", 1).limit(args.limit)
        events = [StructuredEvent(**doc) for doc in cursor]
    except Exception as e:
        logger.error(f"Failed to fetch events from MongoDB: {e}")
        return

    logger.info(f"Fetched {len(events)} events.")
    if not events:
        logger.info("No events to correlate.")
        return

    logger.info("Running correlation batch...")
    result = service.process_batch(events)

    print("\n" + "="*50)
    print("CORRELATION SUMMARY")
    print("="*50)
    print(f"Events processed   : {result.events_processed}")
    print(f"Incidents created  : {result.incidents_created}")
    print(f"Incidents updated  : {result.incidents_updated}")
    print(f"Incidents closed   : {result.incidents_closed}")
    if result.errors:
        print(f"Errors             : {len(result.errors)}")
        for err in result.errors:
            print(f"  - {err}")
    print("="*50)

    # Print a sample incident
    logger.info("Fetching a sample incident for demonstration...")
    try:
        sample = db["incident_timelines"].find_one()
        if sample:
            print("\nEXAMPLE INCIDENT:")
            print(f"ID               : {sample.get('incident_id')}")
            print(f"Status           : {sample.get('status')}")
            print(f"Start            : {sample.get('time_window', {}).get('start')}")
            print(f"End              : {sample.get('time_window', {}).get('end')}")
            print(f"Devices          : {sample.get('affected_devices')}")
            print(f"Interfaces       : {sample.get('affected_interfaces')}")
            print(f"Protocols        : {sample.get('suspected_protocols')}")
            print(f"Reason           : {sample.get('correlation_reason')}")
            events_len = len(sample.get('events', []))
            print(f"Ordered events   : {events_len}")
    except Exception as e:
        logger.error(f"Failed to fetch sample incident: {e}")


if __name__ == "__main__":
    main()

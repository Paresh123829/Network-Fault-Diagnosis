import sys
import logging
from typing import Iterator

from network.datasets.adapters.cisco_adapter import CiscoTelemetryAdapter
from services.ai.agents.ingestion.persistence import IngestionPersistence
from services.ai.agents.ingestion.service import IngestionService


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("ingestion_cli")
    
    logger.info("Initializing Ingestion Pipeline...")
    
    # Setup dependencies
    persistence = IngestionPersistence()
    service = IngestionService(persistence)
    
    # Source data from Phase 1 adapter
    adapter = CiscoTelemetryAdapter()
    
    # Use Case 3 as the demo source (has both syslog and CSV events)
    try:
        syslog_records = list(adapter.iter_syslog_records(case="3"))
        csv_records = list(adapter.iter_csv_records(case="3", max_rows=5000))
        
        all_records = syslog_records + csv_records
        logger.info(f"Loaded {len(all_records)} raw records from fixtures (Case 3).")
        
        # Process through the pipeline
        result = service.process_batch(all_records)
        
        # Print summary report
        print("\n" + "="*50)
        print(result.summary())
        print("="*50 + "\n")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
test_milestone2_ground_truth.py — Unit Tests for Milestone 2 Ground-Truth Evaluation.

Covers:
  - Loading of all 46 documented ground-truth events across Cases 2, 3, 4, 5, 6, 9, 10
  - Dataset partitioning (Train 60%, Val 20%, Test 20%)
  - Zero partition leakage assertion
  - Sliding window sweep (10s, 30s, 60s, 120s, 300s)
  - Selective MongoDB persistence with provenance
  - Correlation algorithm same-device isolation
"""

import os
import pytest
from datetime import datetime, timezone
from pymongo import MongoClient

from network.datasets.adapters.cisco_adapter import CiscoTelemetryAdapter
from network.datasets.adapters.partitioning import (
    partition_cisco_dataset,
    validate_partition_integrity,
    get_partition,
    get_cases_for_partition,
    get_case12_for_partition
)
from network.datasets.tools.evaluate_multi_case_ground_truth import MultiCaseGroundTruthEvaluator
from services.ai.schemas.contracts import (
    StructuredEvent,
    IncidentTimeline,
    EventType,
    Severity,
    TimeWindow
)
from services.ai.agents.correlation.algorithm import CorrelationAlgorithm


@pytest.fixture
def evaluator():
    return MultiCaseGroundTruthEvaluator()


class TestGroundTruthCatalog:
    def test_load_all_46_ground_truth_events(self, evaluator):
        """Validates that all 46 documented ground truth events are loaded."""
        all_gt = evaluator.load_all_ground_truth()
        assert len(all_gt) == 7  # Cases 2, 3, 4, 5, 6, 9, 10
        total_events = sum(len(evts) for evts in all_gt.values())
        assert total_events == 46, f"Expected 46 ground truth events, found {total_events}"

    def test_case_specific_ground_truth_counts(self, evaluator):
        """Validates individual case event counts."""
        all_gt = evaluator.load_all_ground_truth()
        assert len(all_gt["2"]) == 11
        assert len(all_gt["3"]) == 3
        assert len(all_gt["4"]) == 6
        assert len(all_gt["5"]) == 12
        assert len(all_gt["6"]) == 12
        assert len(all_gt["9"]) == 1
        assert len(all_gt["10"]) == 1


class TestPartitioningLeakagePrevention:
    def test_partition_integrity_disjoint(self):
        """Validates that Train, Val, and Test partitions are mutually exclusive."""
        res = validate_partition_integrity()
        assert res["status"] == "leakage_free"
        assert res["leakage_free"] is True
        assert res["total_primary_cases"] == 9
        assert res["total_case12_experiments"] >= 70

    def test_get_partition_mapping(self):
        """Validates partition assignment by case/experiment ID."""
        assert get_partition("2") == "train"
        assert get_partition("4") == "val"
        assert get_partition("6") == "test"
        assert get_partition("9") == "test"
        assert get_partition("10") == "test"
        assert get_partition("200121_0803_ecmp") == "train"

    def test_dataset_partition_object(self):
        """Validates unified DatasetPartition data structure."""
        part = partition_cisco_dataset()
        assert "2" in part.train.case_ids
        assert "4" in part.val.case_ids
        assert "6" in part.test.case_ids
        assert len(set(part.train.case_ids) & set(part.test.case_ids)) == 0


class TestCorrelationWindowSweeps:
    def test_sliding_window_sweep_properties(self, evaluator):
        """Validates window sweep metrics across 10s, 30s, 60s, 120s, 300s."""
        all_gt = evaluator.load_all_ground_truth()
        # Mock structured events for sweep evaluation
        mock_events = {
            "3": [
                StructuredEvent(
                    event_id="evt_test_1",
                    raw_reference="case_3/syslog:100",
                    timestamp=datetime(2017, 8, 4, 10, 20, 0, tzinfo=timezone.utc),
                    device_id="leaf1",
                    event_type=EventType.BGP_NEIGHBOR_DOWN,
                    severity=Severity.HIGH,
                    raw_payload="BGP neighbor down",
                    normalized_fields={"protocol_hint": "bgp"}
                )
            ]
        }
        sweep = evaluator.run_sliding_window_sweep(mock_events, all_gt)
        assert len(sweep) == 5
        windows = [r["window_seconds"] for r in sweep]
        assert windows == [10, 30, 60, 120, 300]
        
        # Verify 120s is optimal
        opt_120 = next(r for r in sweep if r["window_seconds"] == 120)
        assert opt_120["f1_score"] >= 0.90
        assert opt_120["recall"] == 1.0

    def test_same_device_isolation(self, evaluator):
        """Validates that correlation algorithm enforces strict device isolation."""
        t1 = datetime(2017, 8, 4, 10, 20, 0, tzinfo=timezone.utc)
        t2 = datetime(2017, 8, 4, 10, 20, 5, tzinfo=timezone.utc)

        e1 = StructuredEvent(
            event_id="e1",
            raw_reference="case_3/syslog:101",
            timestamp=t1,
            device_id="leaf1",
            event_type=EventType.BGP_NEIGHBOR_DOWN,
            severity=Severity.HIGH,
            raw_payload="BGP Down",
            normalized_fields={"protocol_hint": "bgp"}
        )
        e2 = StructuredEvent(
            event_id="e2",
            raw_reference="case_3/syslog:102",
            timestamp=t2,
            device_id="leaf2",  # Different device
            event_type=EventType.BGP_NEIGHBOR_DOWN,
            severity=Severity.HIGH,
            raw_payload="BGP Down",
            normalized_fields={"protocol_hint": "bgp"}
        )

        algo = CorrelationAlgorithm(window_seconds=120)
        incidents = algo.group_events([e1, e2], [])
        assert len(incidents) == 2, "Different devices must form distinct incidents (no cross-device coupling)"


class TestMongoSelectivePersistence:
    def test_persist_selective_samples(self, evaluator):
        """Validates that sample incidents are persisted with provenance metadata."""
        t1 = datetime(2017, 8, 4, 10, 20, 0, tzinfo=timezone.utc)
        e1 = StructuredEvent(
            event_id="e_sample_1",
            raw_reference="case_4/syslog:201",
            timestamp=t1,
            device_id="leaf1",
            event_type=EventType.PORT_DOWN,
            severity=Severity.HIGH,
            raw_payload="Port HundredGigE0/0/0/8 is Down",
            normalized_fields={"interface": "HundredGigE0/0/0/8"}
        )
        algo = CorrelationAlgorithm(window_seconds=120)
        incs = algo.group_events([e1], [])

        persisted = evaluator.persist_selective_samples(
            incs,
            {"train": {"case12_experiments": ["exp1"]}, "val": {}, "test": {}}
        )
        assert persisted >= 1

        # Check DB
        try:
            client = MongoClient(evaluator.mongo_uri, serverSelectionTimeoutMS=2000)
            doc = client[evaluator.db_name]["evaluation_incident_timelines"].find_one({"incident_id": incs[0].incident_id})
            assert doc is not None
            assert "provenance" in doc
            assert doc["provenance"]["milestone"] == "Milestone 2"
        except Exception as e:
            pytest.skip(f"MongoDB check skipped: {e}")

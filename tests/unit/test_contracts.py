"""
test_contracts.py — Unit tests for all canonical inter-agent contracts.

These tests validate schema structure, field validation, and enum coverage.
They use deterministic fixtures (no external services required).

Run with: pytest tests/unit/test_contracts.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

# Adjust the import path: we run pytest from the project root
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/ai"))

from schemas.contracts import (
    ApprovalState,
    ApprovalStatus,
    DiagnosisResult,
    EventType,
    Hypothesis,
    IncidentTimeline,
    RemediationProposal,
    RetrievedEvidence,
    EvidencePassage,
    ReviewerAction,
    RiskLevel,
    Severity,
    StructuredEvent,
    TimeWindow,
    TopologyContext,
    TopologyLink,
    TopologyNode,
    VerificationCheck,
    VerificationResult,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

NOW = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


def make_structured_event(**overrides) -> dict:
    base = {
        "event_id": "evt-001",
        "timestamp": NOW,
        "device_id": "router-1",
        "interface": "eth0",
        "event_type": EventType.BGP_NEIGHBOR_DOWN,
        "severity": Severity.HIGH,
        "normalized_fields": {"peer_ip": "10.0.0.2", "as_number": 65001},
        "raw_reference": "cisco_telemetry_row_42",
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# StructuredEvent tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStructuredEvent:
    def test_valid_event(self):
        event = StructuredEvent(**make_structured_event())
        assert event.event_id == "evt-001"
        assert event.device_id == "router-1"
        assert event.event_type == EventType.BGP_NEIGHBOR_DOWN
        assert event.severity == Severity.HIGH

    def test_interface_is_optional(self):
        data = make_structured_event()
        data.pop("interface")
        event = StructuredEvent(**data)
        assert event.interface is None

    def test_empty_device_id_raises(self):
        with pytest.raises(ValidationError):
            StructuredEvent(**make_structured_event(device_id="   "))

    def test_invalid_event_type_raises(self):
        with pytest.raises(ValidationError):
            StructuredEvent(**make_structured_event(event_type="not_a_real_event_type"))

    def test_invalid_severity_raises(self):
        with pytest.raises(ValidationError):
            StructuredEvent(**make_structured_event(severity="catastrophic"))

    def test_unknown_event_type_accepted(self):
        event = StructuredEvent(**make_structured_event(event_type=EventType.UNKNOWN))
        assert event.event_type == EventType.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# IncidentTimeline tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentTimeline:
    def test_valid_timeline(self):
        event = StructuredEvent(**make_structured_event())
        timeline = IncidentTimeline(
            incident_id="inc-001",
            time_window=TimeWindow(start=NOW, end=NOW),
            events=[event],
            affected_devices=["router-1"],
            suspected_protocols=["bgp"],
        )
        assert timeline.incident_id == "inc-001"
        assert len(timeline.events) == 1
        assert "bgp" in timeline.suspected_protocols

    def test_empty_suspected_protocols_defaults(self):
        event = StructuredEvent(**make_structured_event())
        timeline = IncidentTimeline(
            incident_id="inc-002",
            time_window=TimeWindow(start=NOW, end=NOW),
            events=[event],
            affected_devices=["router-1"],
        )
        assert timeline.suspected_protocols == []


# ─────────────────────────────────────────────────────────────────────────────
# TopologyContext tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTopologyContext:
    def test_valid_topology(self):
        ctx = TopologyContext(
            nodes=[
                TopologyNode(node_id="r1", node_type="router"),
                TopologyNode(node_id="r2", node_type="router"),
            ],
            links=[
                TopologyLink(source="r1", target="r2", interface_source="eth0", interface_target="eth1"),
            ],
            affected_path=["r1", "r2"],
            neighbors={"r1": ["r2"], "r2": ["r1"]},
            protocol_relationships={"bgp_peers": [{"local": "r1", "remote": "r2"}]},
        )
        assert len(ctx.nodes) == 2
        assert ctx.neighbors["r1"] == ["r2"]

    def test_empty_topology_is_valid(self):
        ctx = TopologyContext(nodes=[], links=[])
        assert ctx.nodes == []


# ─────────────────────────────────────────────────────────────────────────────
# RetrievedEvidence tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRetrievedEvidence:
    def test_valid_evidence(self):
        ev = RetrievedEvidence(
            query="BGP neighbor down root cause",
            passages=[
                EvidencePassage(
                    passage_id="p-001",
                    text="BGP sessions drop when TCP keepalives are missed.",
                    source_id="src-001",
                    relevance_score=0.92,
                )
            ],
            source_ids=["src-001"],
            relevance_scores=[0.92],
        )
        assert ev.passages[0].relevance_score == 0.92

    def test_relevance_score_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            EvidencePassage(
                passage_id="p-001",
                text="some text",
                source_id="src-001",
                relevance_score=1.5,  # > 1.0
            )


# ─────────────────────────────────────────────────────────────────────────────
# DiagnosisResult tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDiagnosisResult:
    def test_valid_diagnosis(self):
        result = DiagnosisResult(
            hypotheses=[
                Hypothesis(
                    hypothesis_id="h-001",
                    description="BGP peer config mismatch",
                    supporting_evidence_ids=["p-001"],
                    confidence=0.85,
                )
            ],
            probable_root_cause="BGP peer configuration mismatch on router-1",
            evidence_ids=["p-001"],
            confidence=0.85,
            affected_components=["router-1", "eth0"],
        )
        assert result.confidence == 0.85

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            DiagnosisResult(
                hypotheses=[],
                probable_root_cause="test",
                confidence=1.5,  # > 1.0
            )


# ─────────────────────────────────────────────────────────────────────────────
# RemediationProposal tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRemediationProposal:
    def test_valid_proposal(self):
        proposal = RemediationProposal(
            action_id="act-001",
            target="router-1",
            operation="clear_bgp_session",
            parameters={"peer_ip": "10.0.0.2"},
            risk=RiskLevel.MEDIUM,
            expected_effect="BGP session re-established with peer 10.0.0.2",
            verification_condition="bgp_session_established",
        )
        assert proposal.operation == "clear_bgp_session"
        assert proposal.risk == RiskLevel.MEDIUM

    def test_invalid_risk_raises(self):
        with pytest.raises(ValidationError):
            RemediationProposal(
                action_id="act-002",
                target="router-1",
                operation="clear_bgp_session",
                parameters={},
                risk="very_risky",  # not a valid RiskLevel
                expected_effect="something",
                verification_condition="something",
            )


# ─────────────────────────────────────────────────────────────────────────────
# ApprovalState tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalState:
    def test_default_state(self):
        state = ApprovalState()
        assert state.status == ApprovalStatus.PENDING
        assert state.requires_human_approval is True
        assert state.reviewer_action is None

    def test_approved_state(self):
        state = ApprovalState(
            status=ApprovalStatus.APPROVED,
            reviewer_action=ReviewerAction.APPROVE,
            timestamp=NOW,
            comments="Looks safe, approving.",
        )
        assert state.status == ApprovalStatus.APPROVED


# ─────────────────────────────────────────────────────────────────────────────
# VerificationResult tests
# ─────────────────────────────────────────────────────────────────────────────

class TestVerificationResult:
    def test_success_result(self):
        result = VerificationResult(
            checks=[
                VerificationCheck(
                    check_id="chk-001",
                    description="BGP session established",
                    passed=True,
                    observed_value="established",
                    expected_value="established",
                )
            ],
            observed_state={"bgp_session": "established"},
            expected_state={"bgp_session": "established"},
            success=True,
        )
        assert result.success is True
        assert result.failure_reason is None

    def test_failure_result(self):
        result = VerificationResult(
            checks=[
                VerificationCheck(
                    check_id="chk-001",
                    description="BGP session established",
                    passed=False,
                    observed_value="idle",
                    expected_value="established",
                )
            ],
            observed_state={"bgp_session": "idle"},
            expected_state={"bgp_session": "established"},
            success=False,
            failure_reason="BGP session still in IDLE state after clear",
        )
        assert result.success is False
        assert "IDLE" in result.failure_reason

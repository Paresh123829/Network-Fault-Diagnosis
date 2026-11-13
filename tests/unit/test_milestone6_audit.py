"""
test_milestone6_audit.py — Unit tests for Hash-Chained Audit Trail and Persistence.
"""

import pytest

from services.ai.schemas.contracts import (
    ApprovalDecision,
    ApprovalStatus,
    AuditRecord,
    ExecutionResult,
    ExecutionStatus,
    PolicyDecision,
    PolicyStatus,
    RemediationProposal,
    ReviewerRole,
    RiskLevel,
    VerificationResult,
    VerificationStatus,
)
from services.ai.agents.diagnosis.remediation_persistence import RemediationPersistence


@pytest.fixture
def persistence():
    p = RemediationPersistence()
    p.check_connection = lambda: False
    p.reset_in_memory()
    return p


class TestRemediationAuditTrail:
    def test_audit_hash_chain_creation(self, persistence):
        # 1. Proposal
        r1 = persistence.append_audit_record(
            incident_id="inc_audit_1",
            action_type="PROPOSAL_CREATED",
            actor="proposal_engine",
            payload={"action_id": "act_1", "operation": "reset_bgp_session"}
        )
        assert r1.sequence_number == 0
        assert r1.prev_hash == persistence.GENESIS_HASH
        assert len(r1.current_hash) == 64

        # 2. Approval
        r2 = persistence.append_audit_record(
            incident_id="inc_audit_1",
            action_type="APPROVAL_APPROVED",
            actor="alice_noc",
            payload={"approval_id": "dec_1", "status": "approved"}
        )
        assert r2.sequence_number == 1
        assert r2.prev_hash == r1.current_hash
        assert len(r2.current_hash) == 64

        # 3. Execution
        r3 = persistence.append_audit_record(
            incident_id="inc_audit_1",
            action_type="EXECUTION_SUCCEEDED",
            actor="simulated_executor",
            payload={"execution_id": "exec_1", "status": "succeeded"}
        )
        assert r3.sequence_number == 2
        assert r3.prev_hash == r2.current_hash

    def test_audit_integrity_verification_intact_chain(self, persistence):
        for i in range(5):
            persistence.append_audit_record(
                incident_id="inc_verify",
                action_type=f"STEP_{i}",
                actor="test_runner",
                payload={"step": i}
            )

        is_valid, errors = persistence.verify_audit_chain_integrity()
        assert is_valid is True
        assert len(errors) == 0

    def test_tamper_detection_modified_payload(self, persistence):
        r1 = persistence.append_audit_record(incident_id="inc_t1", action_type="STEP_1", actor="bot", payload={"val": 100})
        r2 = persistence.append_audit_record(incident_id="inc_t1", action_type="STEP_2", actor="bot", payload={"val": 200})

        # Deliberately modify r1 payload in-memory (simulating unauthorized modification)
        r1.payload["val"] = 999  # Tamper!

        is_valid, errors = persistence.verify_audit_chain_integrity()
        assert is_valid is False
        assert any("Tamper detected" in e for e in errors)

    def test_tamper_detection_broken_chain_link(self, persistence):
        r1 = persistence.append_audit_record(incident_id="inc_t2", action_type="STEP_1", actor="bot", payload={"val": 1})
        r2 = persistence.append_audit_record(incident_id="inc_t2", action_type="STEP_2", actor="bot", payload={"val": 2})

        # Deliberately falsify prev_hash on r2
        r2.prev_hash = "deadbeef" * 8

        is_valid, errors = persistence.verify_audit_chain_integrity()
        assert is_valid is False
        assert any("Audit chain broken" in e or "Tamper detected" in e for e in errors)

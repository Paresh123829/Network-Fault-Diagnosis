"""
Unit tests for Milestone 6.1 full audit-chain cryptographic integrity traversal.
"""

import copy
import pytest

from services.ai.agents.diagnosis.remediation_persistence import RemediationPersistence
from services.ai.agents.oversight.audit_verifier import AuditVerifier


@pytest.fixture
def persistence():
    p = RemediationPersistence()
    p.check_connection = lambda: False
    p.reset_in_memory()
    return p


@pytest.fixture
def verifier(persistence, tmp_path):
    from services.ai.agents.oversight.audit_anchor import AuditAnchorManager
    isolated_anchor_mgr = AuditAnchorManager(anchor_dir=str(tmp_path))
    return AuditVerifier(persistence=persistence, anchor_manager=isolated_anchor_mgr)


def test_audit_full_chain_clean(persistence, verifier):
    persistence.append_audit_record("inc_01", "PROPOSAL_CREATED", "engine", {"id": "p1"})
    persistence.append_audit_record("inc_01", "APPROVAL_APPROVED", "dave", {"appr_id": "a1"})
    persistence.append_audit_record("inc_01", "EXECUTION_SUCCEEDED", "executor", {"exec_id": "e1"})
    persistence.append_audit_record("inc_01", "VERIFICATION_RECOVERED", "verifier", {"ver_id": "v1"})

    rep = verifier.verify_full_chain_integrity()
    assert rep.is_valid is True
    assert rep.records_examined == 4
    assert rep.sequence_range == (0, 3)
    assert rep.genesis_verified is True
    assert len(rep.detected_violations) == 0


def test_audit_detects_payload_modification(persistence, verifier):
    persistence.append_audit_record("inc_01", "PROPOSAL_CREATED", "engine", {"id": "p1"})
    persistence.append_audit_record("inc_01", "APPROVAL_APPROVED", "dave", {"appr_id": "a1"})
    persistence.append_audit_record("inc_01", "EXECUTION_SUCCEEDED", "executor", {"exec_id": "e1"})

    # Tamper with record 1 payload in-memory
    persistence._in_memory_audit[1].payload["appr_id"] = "TAMPERED_APPROVAL"

    rep = verifier.verify_full_chain_integrity()
    assert rep.is_valid is False
    assert any("AUDIT_PAYLOAD_TAMPER" in err for err in rep.detected_violations)


def test_audit_detects_sequence_gap_or_deletion(persistence, verifier):
    persistence.append_audit_record("inc_01", "PROPOSAL_CREATED", "engine", {"id": "p1"})
    persistence.append_audit_record("inc_01", "APPROVAL_APPROVED", "dave", {"appr_id": "a1"})
    persistence.append_audit_record("inc_01", "EXECUTION_SUCCEEDED", "executor", {"exec_id": "e1"})

    # Delete record 1 (middle deletion)
    del persistence._in_memory_audit[1]

    rep = verifier.verify_full_chain_integrity()
    assert rep.is_valid is False
    assert any("AUDIT_SEQUENCE_GAP" in err or "AUDIT_CHAIN_BROKEN" in err for err in rep.detected_violations)


def test_audit_detects_genesis_corruption(persistence, verifier):
    persistence.append_audit_record("inc_01", "PROPOSAL_CREATED", "engine", {"id": "p1"})
    # Corrupt genesis prev_hash
    persistence._in_memory_audit[0].prev_hash = "f" * 64

    rep = verifier.verify_full_chain_integrity()
    assert rep.is_valid is False
    assert any("AUDIT_GENESIS_CORRUPTION" in err for err in rep.detected_violations)


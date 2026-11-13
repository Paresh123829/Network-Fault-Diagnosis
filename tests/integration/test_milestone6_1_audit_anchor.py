"""
Integration tests for Milestone 6.1 independently protected audit anchors and tamper detection.
"""

import tempfile
import pytest

from services.ai.agents.diagnosis.remediation_persistence import RemediationPersistence
from services.ai.agents.oversight.audit_anchor import AuditAnchorManager
from services.ai.agents.oversight.audit_verifier import AuditVerifier


@pytest.fixture
def test_env():
    p = RemediationPersistence()
    p.check_connection = lambda: False
    p.reset_in_memory()

    with tempfile.TemporaryDirectory() as td:
        am = AuditAnchorManager(anchor_dir=td, secret_key="test_audit_anchor_key_2026")
        v = AuditVerifier(persistence=p, anchor_manager=am)
        yield p, am, v


def test_audit_detects_full_chain_database_rewrite(test_env):
    """
    Scenario 6: Privileged attacker alters historical database record AND
    recalculates all downstream hashes to make internal DB chain self-consistent.
    The independently protected anchor MUST detect the mismatch!
    """
    persistence, anchor_mgr, verifier = test_env

    # 1. Append authentic audit events
    persistence.append_audit_record("inc_01", "PROPOSAL_CREATED", "engine", {"id": "p1"})
    persistence.append_audit_record("inc_01", "APPROVAL_APPROVED", "dave", {"appr_id": "a1"})
    r2 = persistence.append_audit_record("inc_01", "EXECUTION_SUCCEEDED", "executor", {"exec_id": "e1"})
    r3 = persistence.append_audit_record("inc_01", "VERIFICATION_RECOVERED", "verifier", {"ver_id": "v1"})

    # 2. Create independent anchor at sequence 3
    anchor = anchor_mgr.create_anchor(
        chain_id="main_chain",
        latest_sequence_number=r3.sequence_number,
        latest_chain_hash=r3.current_hash,
    )
    assert anchor_mgr.verify_anchor_signature(anchor) is True

    # Initial verification clean
    rep_initial = verifier.verify_full_chain_integrity(chain_id="main_chain")
    assert rep_initial.is_valid is True
    assert rep_initial.anchor_verified is True

    # 3. Simulate Attacker modifying record 1 AND recalculating all hashes
    records = persistence._in_memory_audit
    records[1].payload = {"appr_id": "FORGED_APPROVAL"}
    # Recalculate hash of record 1
    records[1].current_hash = records[1].calculate_hash()
    # Relink and recalculate record 2
    records[2].prev_hash = records[1].current_hash
    records[2].current_hash = records[2].calculate_hash()
    # Relink and recalculate record 3
    records[3].prev_hash = records[2].current_hash
    records[3].current_hash = records[3].calculate_hash()

    # If only verifying the internal DB chain, it might look valid:
    # but with the independent anchor:
    rep_attack = verifier.verify_full_chain_integrity(chain_id="main_chain")
    assert rep_attack.is_valid is False
    assert any("AUDIT_ANCHOR_MISMATCH" in v for v in rep_attack.detected_violations), \
        "Full-chain rewrite must be caught by independent anchor mismatch!"


def test_audit_detects_tail_truncation(test_env):
    """
    Scenario 7: Database administrator truncates the latest records from MongoDB.
    The independent anchor detects that the DB chain is shorter than the committed anchor.
    """
    persistence, anchor_mgr, verifier = test_env

    # Append 5 records (seq 0..4)
    for i in range(5):
        persistence.append_audit_record("inc_01", f"EVENT_{i}", "actor", {"idx": i})

    latest_rec = persistence._in_memory_audit[-1]
    assert latest_rec.sequence_number == 4

    # Anchor at sequence 4
    anchor_mgr.create_anchor(
        chain_id="main_chain",
        latest_sequence_number=latest_rec.sequence_number,
        latest_chain_hash=latest_rec.current_hash,
    )

    # Truncate last 2 records from database
    del persistence._in_memory_audit[-1]
    del persistence._in_memory_audit[-1]
    assert len(persistence._in_memory_audit) == 3

    rep_trunc = verifier.verify_full_chain_integrity(chain_id="main_chain")
    assert rep_trunc.is_valid is False
    assert any("AUDIT_TRUNCATION_DETECTED" in v for v in rep_trunc.detected_violations)


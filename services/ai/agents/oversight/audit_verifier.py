"""
audit_verifier.py — Complete Audit-Chain Integrity & Independent Anchor Verification.

Performs exhaustive full-chain traversal from genesis to latest sequence and validates
against independently protected HMAC anchors to detect record tampering, middle deletion,
sequence truncation, and full-chain database rewrites.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from services.ai.schemas.contracts import AuditRecord
from services.ai.agents.diagnosis.remediation_persistence import remediation_persistence
from services.ai.agents.oversight.audit_anchor import audit_anchor_manager, AuditAnchor

logger = logging.getLogger(__name__)


class AuditVerificationReport(BaseModel):
    is_valid: bool
    records_examined: int
    sequence_range: Tuple[int, int] = (0, 0)
    genesis_verified: bool = False
    latest_sequence_number: int = 0
    latest_chain_hash: str = ""
    anchor_verified: bool = False
    anchor_id: Optional[str] = None
    detected_violations: List[str] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditVerifier:
    """
    Exhaustive full-chain and anchor verification engine.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, persistence=None, anchor_manager=None) -> None:
        self.persistence = persistence or remediation_persistence
        self.anchor_mgr = anchor_manager or audit_anchor_manager

    def verify_full_chain_integrity(
        self,
        chain_id: str = "main_chain",
        incident_id: Optional[str] = None,
        anchor: Optional[AuditAnchor] = None,
    ) -> AuditVerificationReport:
        """
        Traverses all records in the audit chain and verifies cryptographic invariants:
        1. Sequence continuity from 0 to N without gaps or duplicates.
        2. Unbroken previous_hash linkage across every consecutive pair.
        3. Recalculated SHA-256 payload authenticity for each record.
        4. Independent anchor compliance (detecting tail truncation & complete chain rewrites).
        """
        records = self.persistence.get_audit_trail(incident_id=incident_id)
        violations: List[str] = []

        target_anchor = anchor or self.anchor_mgr.get_latest_anchor(chain_id)

        if not records:
            if target_anchor and target_anchor.latest_sequence_number >= 0:
                violations.append(
                    f"AUDIT_TRUNCATION_DETECTED: Database contains 0 records, but trusted anchor "
                    f"'{target_anchor.anchor_id}' commits sequence {target_anchor.latest_sequence_number}."
                )
                return AuditVerificationReport(
                    is_valid=False,
                    records_examined=0,
                    sequence_range=(0, 0),
                    detected_violations=violations,
                )
            return AuditVerificationReport(
                is_valid=True,
                records_examined=0,
                sequence_range=(0, 0),
                genesis_verified=True,
                detected_violations=[],
            )

        expected_prev = self.GENESIS_HASH
        expected_seq = 0
        genesis_verified = False

        for i, rec in enumerate(records):
            # Check 1: Sequence number continuity
            if not incident_id and rec.sequence_number != expected_seq:
                violations.append(
                    f"AUDIT_SEQUENCE_GAP: Record index {i} has sequence {rec.sequence_number}, "
                    f"expected {expected_seq}."
                )

            # Check 2: Genesis record validation
            if i == 0 and not incident_id:
                if rec.prev_hash != self.GENESIS_HASH:
                    violations.append(
                        f"AUDIT_GENESIS_CORRUPTION: Genesis record has prev_hash '{rec.prev_hash}', "
                        f"expected {self.GENESIS_HASH}."
                    )
                else:
                    genesis_verified = True
            elif i > 0:
                if rec.prev_hash != expected_prev:
                    violations.append(
                        f"AUDIT_CHAIN_BROKEN: Record {rec.sequence_number} prev_hash '{rec.prev_hash}' "
                        f"does NOT link to preceding hash '{expected_prev}'."
                    )

            # Check 3: Recomputed SHA-256 integrity
            computed = rec.calculate_hash()
            if rec.current_hash != computed:
                violations.append(
                    f"AUDIT_PAYLOAD_TAMPER: Record {rec.sequence_number} claimed hash '{rec.current_hash}' "
                    f"differs from recomputed hash '{computed}'."
                )

            expected_prev = rec.current_hash
            expected_seq = rec.sequence_number + 1

        latest_record = records[-1]
        seq_range = (records[0].sequence_number, latest_record.sequence_number)
        anchor_verified = False
        anchor_id = None

        # Check 4: Independent Anchor Verification
        if target_anchor:
            anchor_id = target_anchor.anchor_id
            # 4a. Signature integrity of anchor itself
            if not self.anchor_mgr.verify_anchor_signature(target_anchor):
                violations.append(
                    f"AUDIT_ANCHOR_UNVERIFIABLE: Anchor '{target_anchor.anchor_id}' signature "
                    f"failed HMAC verification. Secret key mismatch or anchor file tampered."
                )
            else:
                # 4b. Check for truncation (chain shorter than committed anchor)
                if latest_record.sequence_number < target_anchor.latest_sequence_number:
                    violations.append(
                        f"AUDIT_TRUNCATION_DETECTED: Latest database sequence {latest_record.sequence_number} "
                        f"is shorter than trusted anchor sequence {target_anchor.latest_sequence_number}."
                    )
                else:
                    # 4c. Find record at anchored sequence
                    anchored_rec = next(
                        (r for r in records if r.sequence_number == target_anchor.latest_sequence_number),
                        None
                    )
                    if not anchored_rec:
                        violations.append(
                            f"AUDIT_TRUNCATION_DETECTED: Anchored sequence {target_anchor.latest_sequence_number} "
                            f"missing from audit trail."
                        )
                    elif anchored_rec.current_hash != target_anchor.latest_chain_hash:
                        # CRITICAL: Catches full-chain rewrite where attacker recomputed all DB hashes!
                        violations.append(
                            f"AUDIT_ANCHOR_MISMATCH: Database hash '{anchored_rec.current_hash}' at sequence "
                            f"{target_anchor.latest_sequence_number} does not match trusted anchor hash "
                            f"'{target_anchor.latest_chain_hash}'. Full chain rewrite detected!"
                        )
                    else:
                        anchor_verified = True

        is_valid = len(violations) == 0
        if is_valid:
            logger.info(
                f"[AUDIT VERIFICATION SUCCESS] Verified {len(records)} records (seq {seq_range[0]}..{seq_range[1]}). "
                f"Anchor={anchor_id or 'none'} valid={anchor_verified}."
            )
        else:
            logger.critical(f"[AUDIT VERIFICATION FAILED] {len(violations)} violations detected: {violations}")

        return AuditVerificationReport(
            is_valid=is_valid,
            records_examined=len(records),
            sequence_range=seq_range,
            genesis_verified=genesis_verified,
            latest_sequence_number=latest_record.sequence_number,
            latest_chain_hash=latest_record.current_hash,
            anchor_verified=anchor_verified,
            anchor_id=anchor_id,
            detected_violations=violations,
        )


# Global singleton instance
audit_verifier = AuditVerifier()


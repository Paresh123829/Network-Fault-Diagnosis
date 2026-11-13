"""
remediation_persistence.py — Durable Remediation Auditing & Tamper-Evident Hash Chaining.

Persists remediation proposals, policy decisions, approvals, execution results, verifications,
and rollbacks to MongoDB. Maintains an append-only, sequentially hash-chained audit trail
with automated integrity verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from pymongo import MongoClient, ASCENDING

from services.ai.schemas.contracts import (
    ApprovalDecision,
    AuditRecord,
    ExecutionResult,
    PolicyDecision,
    RemediationProposal,
    RollbackResult,
    VerificationResult,
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.ai.agents.oversight.models import ApprovalRequest

logger = logging.getLogger(__name__)


class RemediationPersistence:
    """
    MongoDB persistence and tamper-evident audit chain manager for network remediations.
    """

    GENESIS_HASH = "0" * 64

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: Optional[str] = None,
    ) -> None:
        self.mongo_uri = mongo_uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name or os.environ.get("MONGO_DB_NAME", "cnt_fault_diagnosis")
        self._client: Optional[MongoClient] = None
        self._lock = threading.RLock()

        # In-memory audit fallback for test environments or offline Mongo
        self._in_memory_audit: List[AuditRecord] = []
        self._in_memory_proposals: Dict[str, Dict[str, Any]] = {}
        self._in_memory_approvals: Dict[str, Dict[str, Any]] = {}
        self._in_memory_executions: Dict[str, Dict[str, Any]] = {}
        self._in_memory_verifications: Dict[str, Dict[str, Any]] = {}
        self._in_memory_rollbacks: Dict[str, Dict[str, Any]] = {}

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            self._client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=2000)
        return self._client

    @property
    def db(self):
        return self.client[self.db_name]

    def check_connection(self) -> bool:
        """Pings MongoDB to determine availability."""
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def ensure_indexes(self) -> None:
        """Configures unique and search indexes in MongoDB collections."""
        if not self.check_connection():
            return
        try:
            self.db.remediation_proposals.create_index([("action_id", ASCENDING)], unique=True)
            self.db.remediation_proposals.create_index([("incident_id", ASCENDING)])
            self.db.approvals.create_index([("request_id", ASCENDING)], unique=True)
            self.db.approvals.create_index([("proposal_id", ASCENDING)])
            self.db.execution_results.create_index([("execution_id", ASCENDING)], unique=True)
            self.db.verification_results.create_index([("verification_id", ASCENDING)], unique=True)
            self.db.rollback_results.create_index([("rollback_id", ASCENDING)], unique=True)
            self.db.audit_records.create_index([("sequence_number", ASCENDING)], unique=True)
            self.db.audit_records.create_index([("incident_id", ASCENDING)])
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    # ─── 1. Document Persistence ──────────────────────────────────────────────

    def save_proposal(self, proposal: RemediationProposal) -> bool:
        doc = proposal.model_dump()
        doc["created_at"] = doc["created_at"].isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at")
        doc["expires_at"] = doc["expires_at"].isoformat() if isinstance(doc.get("expires_at"), datetime) else doc.get("expires_at")
        self._in_memory_proposals[proposal.action_id] = doc

        if self.check_connection():
            try:
                self.db.remediation_proposals.replace_one({"action_id": proposal.action_id}, doc, upsert=True)
            except Exception as e:
                logger.error(f"Failed to persist proposal to MongoDB: {e}")

        # Append to audit chain
        self.append_audit_record(
            incident_id=proposal.incident_id,
            action_type="PROPOSAL_CREATED",
            actor="remediation_proposal_engine",
            payload={
                "action_id": proposal.action_id,
                "operation": proposal.operation,
                "target": proposal.target,
                "canonical_hash": proposal.canonical_hash,
                "risk": proposal.risk.value if hasattr(proposal.risk, "value") else str(proposal.risk),
            }
        )
        return True

    def save_approval_request(self, request: ApprovalRequest) -> bool:
        doc = request.model_dump()
        doc["created_at"] = doc["created_at"].isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at")
        doc["expires_at"] = doc["expires_at"].isoformat() if isinstance(doc.get("expires_at"), datetime) else doc.get("expires_at")
        self._in_memory_approvals[request.request_id] = doc

        if self.check_connection():
            try:
                self.db.approvals.replace_one({"request_id": request.request_id}, doc, upsert=True)
            except Exception as e:
                logger.error(f"Failed to persist approval request to MongoDB: {e}")
        return True

    def save_approval_decision(self, request: ApprovalRequest, decision: ApprovalDecision) -> bool:
        self.save_approval_request(request)

        # Append to audit chain
        self.append_audit_record(
            incident_id=request.incident_id,
            action_type=f"APPROVAL_{decision.status.value.upper()}",
            actor=decision.reviewer_identity,
            payload={
                "approval_id": decision.approval_id,
                "request_id": request.request_id,
                "proposal_id": decision.proposal_id,
                "proposal_hash": decision.proposal_hash,
                "reviewer_role": decision.reviewer_role.value if hasattr(decision.reviewer_role, "value") else str(decision.reviewer_role),
                "status": decision.status.value if hasattr(decision.status, "value") else str(decision.status),
                "comments": decision.comments,
            }
        )
        return True

    def save_execution_result(self, result: ExecutionResult, incident_id: str = "") -> bool:
        doc = result.model_dump()
        doc["started_at"] = doc["started_at"].isoformat() if isinstance(doc.get("started_at"), datetime) else doc.get("started_at")
        doc["completed_at"] = doc["completed_at"].isoformat() if isinstance(doc.get("completed_at"), datetime) else doc.get("completed_at")
        self._in_memory_executions[result.execution_id] = doc

        if self.check_connection():
            try:
                self.db.execution_results.replace_one({"execution_id": result.execution_id}, doc, upsert=True)
            except Exception as e:
                logger.error(f"Failed to persist execution result to MongoDB: {e}")

        # Append to audit chain
        self.append_audit_record(
            incident_id=incident_id or result.proposal_id,
            action_type=f"EXECUTION_{result.status.value.upper()}",
            actor="simulated_remediation_executor",
            payload={
                "execution_id": result.execution_id,
                "proposal_id": result.proposal_id,
                "operation": result.operation,
                "target_device": result.target_device,
                "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        return True

    def save_verification_result(self, result: VerificationResult, incident_id: str = "") -> bool:
        doc = result.model_dump()
        doc["verified_at"] = doc["verified_at"].isoformat() if isinstance(doc.get("verified_at"), datetime) else doc.get("verified_at")
        self._in_memory_verifications[result.verification_id] = doc

        if self.check_connection():
            try:
                self.db.verification_results.replace_one({"verification_id": result.verification_id}, doc, upsert=True)
            except Exception as e:
                logger.error(f"Failed to persist verification result to MongoDB: {e}")

        # Append to audit chain
        self.append_audit_record(
            incident_id=incident_id or result.execution_id,
            action_type=f"VERIFICATION_{result.status.value.upper()}",
            actor="post_remediation_verifier",
            payload={
                "verification_id": result.verification_id,
                "execution_id": result.execution_id,
                "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                "success": result.success,
                "checks_passed": len([c for c in result.checks if c.passed]),
                "total_checks": len(result.checks),
                "failure_reason": result.failure_reason,
            }
        )
        return True

    def save_rollback_result(self, result: RollbackResult, incident_id: str = "") -> bool:
        doc = result.model_dump()
        doc["started_at"] = doc["started_at"].isoformat() if isinstance(doc.get("started_at"), datetime) else doc.get("started_at")
        doc["completed_at"] = doc["completed_at"].isoformat() if isinstance(doc.get("completed_at"), datetime) else doc.get("completed_at")
        self._in_memory_rollbacks[result.rollback_id] = doc

        if self.check_connection():
            try:
                self.db.rollback_results.replace_one({"rollback_id": result.rollback_id}, doc, upsert=True)
            except Exception as e:
                logger.error(f"Failed to persist rollback result to MongoDB: {e}")

        # Append to audit chain
        self.append_audit_record(
            incident_id=incident_id or result.proposal_id,
            action_type=f"ROLLBACK_{result.status.value.upper()}",
            actor="remediation_rollback_engine",
            payload={
                "rollback_id": result.rollback_id,
                "proposal_id": result.proposal_id,
                "execution_id": result.execution_id,
                "operation": result.operation,
                "status": result.status.value if hasattr(result.status, "value") else str(result.status),
                "is_verified": result.is_verified,
                "failure_reason": result.failure_reason,
            }
        )
        return True

    # ─── Query Helpers ────────────────────────────────────────────────────────

    def get_proposal(self, action_id: str) -> Optional[RemediationProposal]:
        with self._lock:
            if self.check_connection():
                try:
                    doc = self.db.remediation_proposals.find_one({"action_id": action_id})
                    if doc:
                        doc.pop("_id", None)
                        return RemediationProposal(**doc)
                except Exception as e:
                    logger.warning(f"Error fetching proposal {action_id} from Mongo: {e}")
            raw = self._in_memory_proposals.get(action_id)
            return RemediationProposal(**raw) if raw else None

    def get_approval_decision(self, proposal_id: str) -> Optional[ApprovalDecision]:
        with self._lock:
            if self.check_connection():
                try:
                    doc = self.db.approvals.find_one({"proposal_id": proposal_id})
                    if doc:
                        doc.pop("_id", None)
                        dec_data = doc.get("decision")
                        if dec_data:
                            return ApprovalDecision(**dec_data)
                        # Maybe stored directly
                        if "approval_id" in doc:
                            return ApprovalDecision(**doc)
                except Exception as e:
                    logger.warning(f"Error fetching approval for {proposal_id} from Mongo: {e}")
            for req in self._in_memory_approvals.values():
                if req.get("proposal_id") == proposal_id and req.get("decision"):
                    return ApprovalDecision(**req["decision"])
            return None

    def get_execution_for_proposal(self, proposal_id: str) -> Optional[ExecutionResult]:
        with self._lock:
            if self.check_connection():
                try:
                    doc = self.db.execution_results.find_one({"proposal_id": proposal_id})
                    if doc:
                        doc.pop("_id", None)
                        return ExecutionResult(**doc)
                except Exception as e:
                    logger.warning(f"Error fetching execution for {proposal_id} from Mongo: {e}")
            for ex in self._in_memory_executions.values():
                if ex.get("proposal_id") == proposal_id:
                    return ExecutionResult(**ex)
            return None

    def get_execution_result(self, execution_id: str) -> Optional[ExecutionResult]:
        with self._lock:
            if self.check_connection():
                try:
                    doc = self.db.execution_results.find_one({"execution_id": execution_id})
                    if doc:
                        doc.pop("_id", None)
                        return ExecutionResult(**doc)
                except Exception as e:
                    logger.warning(f"Error fetching execution {execution_id} from Mongo: {e}")
            raw = self._in_memory_executions.get(execution_id)
            return ExecutionResult(**raw) if raw else None

    def get_verification_for_execution(self, execution_id: str) -> Optional[VerificationResult]:
        with self._lock:
            if self.check_connection():
                try:
                    doc = self.db.verification_results.find_one({"execution_id": execution_id})
                    if doc:
                        doc.pop("_id", None)
                        return VerificationResult(**doc)
                except Exception as e:
                    logger.warning(f"Error fetching verification for {execution_id} from Mongo: {e}")
            for ver in self._in_memory_verifications.values():
                if ver.get("execution_id") == execution_id:
                    return VerificationResult(**ver)
            return None

    def get_rollback_result(self, rollback_id: str) -> Optional[RollbackResult]:
        with self._lock:
            if self.check_connection():
                try:
                    doc = self.db.rollback_results.find_one({"rollback_id": rollback_id})
                    if doc:
                        doc.pop("_id", None)
                        return RollbackResult(**doc)
                except Exception as e:
                    logger.warning(f"Error fetching rollback {rollback_id} from Mongo: {e}")
            raw = self._in_memory_rollbacks.get(rollback_id)
            return RollbackResult(**raw) if raw else None

    def append_audit_record(
        self,
        incident_id: str,
        action_type: str,
        actor: str,
        payload: Dict[str, Any]
    ) -> AuditRecord:
        """
        Appends a sequentially hash-chained audit record.
        Computes SHA-256 over: prev_hash + sequence_number + timestamp + payload.
        """
        with self._lock:
            # Determine previous hash and sequence number
            prev_hash = self.GENESIS_HASH
            seq_num = 0

            if self.check_connection():
                try:
                    last_record = self.db.audit_records.find_one(sort=[("sequence_number", -1)])
                    if last_record:
                        prev_hash = last_record.get("current_hash", self.GENESIS_HASH)
                        seq_num = last_record.get("sequence_number", 0) + 1
                except Exception as e:
                    logger.warning(f"Error reading last audit record from Mongo: {e}")
                    if self._in_memory_audit:
                        prev_hash = self._in_memory_audit[-1].current_hash
                        seq_num = len(self._in_memory_audit)
            else:
                if self._in_memory_audit:
                    prev_hash = self._in_memory_audit[-1].current_hash
                    seq_num = len(self._in_memory_audit)

            now = datetime.now(timezone.utc)
            record_id = f"aud_{uuid.uuid4().hex[:12]}"

            # Construct preliminary record
            record = AuditRecord(
                record_id=record_id,
                sequence_number=seq_num,
                incident_id=incident_id,
                action_type=action_type,
                actor=actor,
                payload=payload,
                timestamp=now,
                prev_hash=prev_hash,
                current_hash="",
            )
            record.current_hash = record.calculate_hash()

            # Store in-memory
            self._in_memory_audit.append(record)

            # Store in MongoDB
            if self.check_connection():
                try:
                    doc = record.model_dump()
                    doc["timestamp"] = doc["timestamp"].isoformat()
                    self.db.audit_records.insert_one(doc)
                except Exception as e:
                    logger.error(f"Failed to insert audit record to MongoDB: {e}")

            logger.info(f"[AUDIT CHAIN] Appended record {seq_num} ({action_type}) hash={record.current_hash[:16]}...")
            return record

    def get_audit_trail(self, incident_id: Optional[str] = None) -> List[AuditRecord]:
        """Retrieves audit records in chronological sequence."""
        with self._lock:
            if self.check_connection():
                try:
                    query = {"incident_id": incident_id} if incident_id else {}
                    cursor = self.db.audit_records.find(query).sort("sequence_number", 1)
                    records = []
                    for doc in cursor:
                        doc.pop("_id", None)
                        if isinstance(doc.get("timestamp"), str):
                            doc["timestamp"] = datetime.fromisoformat(doc["timestamp"])
                        records.append(AuditRecord(**doc))
                    if records:
                        return records
                except Exception as e:
                    logger.warning(f"Failed reading audit records from Mongo: {e}")

            # Fallback in-memory
            if incident_id:
                return [r for r in self._in_memory_audit if r.incident_id == incident_id]
            return list(self._in_memory_audit)

    def verify_audit_chain_integrity(self, incident_id: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Traverses the audit chain and verifies:
        1. Monotonically increasing sequence numbers with zero gaps.
        2. prev_hash equals current_hash of preceding record (or GENESIS_HASH).
        3. Recalculated hash matches stored current_hash.
        Detects tampering, insertion, or record deletion.
        """
        records = self.get_audit_trail(incident_id=incident_id)
        if not records:
            return True, ["Audit chain is empty. No tampering detected."]

        errors: List[str] = []
        expected_prev = self.GENESIS_HASH

        for i, rec in enumerate(records):
            # Check 1: Sequence number
            if not incident_id and rec.sequence_number != i:
                errors.append(f"Audit sequence gap at index {i}: expected sequence {i}, got {rec.sequence_number}.")

            # Check 2: Hash link to predecessor
            if i == 0 and not incident_id:
                if rec.prev_hash != self.GENESIS_HASH:
                    errors.append(f"Genesis record 0 has invalid prev_hash '{rec.prev_hash}' (expected {self.GENESIS_HASH}).")
            elif i > 0:
                if rec.prev_hash != expected_prev:
                    errors.append(
                        f"Audit chain broken at record {rec.sequence_number}: prev_hash '{rec.prev_hash}' "
                        f"does NOT match previous record hash '{expected_prev}'."
                    )

            # Check 3: Hash authenticity
            calculated = rec.calculate_hash()
            if rec.current_hash != calculated:
                errors.append(
                    f"Tamper detected in record {rec.sequence_number}: claimed hash '{rec.current_hash}' "
                    f"does NOT match recalculated hash '{calculated}'."
                )

            expected_prev = rec.current_hash

        is_valid = len(errors) == 0
        if is_valid:
            logger.info(f"[AUDIT VERIFICATION SUCCESS] Verified {len(records)} consecutive audit records. 0 errors.")
        else:
            logger.critical(f"[AUDIT VERIFICATION FAILURE] Detected {len(errors)} audit integrity errors: {errors}")

        return is_valid, errors

    def reset_in_memory(self) -> None:
        """Resets local in-memory records (used for test isolation)."""
        with self._lock:
            self._in_memory_audit.clear()
            self._in_memory_proposals.clear()
            self._in_memory_approvals.clear()
            self._in_memory_executions.clear()
            self._in_memory_verifications.clear()
            self._in_memory_rollbacks.clear()


# Global singleton instance
remediation_persistence = RemediationPersistence()


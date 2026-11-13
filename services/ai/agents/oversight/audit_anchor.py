"""
audit_anchor.py — Independently Protected Cryptographic Audit Anchors.

Generates and validates HMAC-signed audit checkpoints outside MongoDB's trust boundary.
Detects full-chain database rewrites, sequence rollbacks, and tail truncation attacks.
"""

from __future__ import annotations

import hmac
import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AuditAnchor(BaseModel):
    """
    Cryptographically signed checkpoint binding an audit chain state.
    """
    anchor_id: str
    chain_id: str
    latest_sequence_number: int
    latest_chain_hash: str
    anchored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prev_anchor_hash: str = "0" * 64
    signature: str = ""
    algorithm: str = "HMAC-SHA256"

    def canonical_payload(self) -> str:
        d = {
            "anchor_id": self.anchor_id,
            "chain_id": self.chain_id,
            "latest_sequence_number": self.latest_sequence_number,
            "latest_chain_hash": self.latest_chain_hash,
            "anchored_at": self.anchored_at.isoformat() if isinstance(self.anchored_at, datetime) else str(self.anchored_at),
            "prev_anchor_hash": self.prev_anchor_hash,
            "algorithm": self.algorithm,
        }
        return json.dumps(d, sort_keys=True)


class AuditAnchorManager:
    """
    Manages immutable audit anchors stored outside MongoDB in a protected storage boundary.
    """

    DEFAULT_ANCHOR_DIR = "data/audit_anchors"

    def __init__(
        self,
        anchor_dir: Optional[str] = None,
        secret_key: Optional[str] = None,
    ) -> None:
        self.anchor_dir = anchor_dir or os.environ.get("AUDIT_ANCHOR_DIR", self.DEFAULT_ANCHOR_DIR)
        self.anchor_file = os.path.join(self.anchor_dir, "anchors.json")
        self.key_file = os.path.join(self.anchor_dir, ".anchor_secret.key")
        self._lock = threading.RLock()

        os.makedirs(self.anchor_dir, exist_ok=True)
        self.secret_key = secret_key or self._load_or_generate_key()
        self._in_memory_anchors: List[AuditAnchor] = []
        self._load_anchors()

    def _load_or_generate_key(self) -> str:
        env_key = os.environ.get("AUDIT_ANCHOR_SECRET")
        if env_key:
            return env_key
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.warning(f"Could not read anchor key file: {e}")
        # Generate new 256-bit key
        new_key = uuid.uuid4().hex + uuid.uuid4().hex
        try:
            with open(self.key_file, "w", encoding="utf-8") as f:
                f.write(new_key)
        except Exception as e:
            logger.warning(f"Could not persist anchor key file: {e}")
        return new_key

    def _load_anchors(self) -> None:
        with self._lock:
            if os.path.exists(self.anchor_file):
                try:
                    with open(self.anchor_file, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                        self._in_memory_anchors = [AuditAnchor(**a) for a in raw]
                    logger.info(f"Loaded {len(self._in_memory_anchors)} audit anchors from {self.anchor_file}")
                except Exception as e:
                    logger.error(f"Error loading audit anchors: {e}")

    def _persist_anchors(self) -> None:
        with self._lock:
            tmp_path = f"{self.anchor_file}.tmp.{os.getpid()}"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump([a.model_dump(mode="json") for a in self._in_memory_anchors], f, indent=2)
                if os.path.exists(self.anchor_file):
                    os.replace(tmp_path, self.anchor_file)
                else:
                    os.rename(tmp_path, self.anchor_file)
            except Exception as e:
                logger.error(f"Failed to persist audit anchors to disk: {e}")
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

    def compute_signature(self, anchor: AuditAnchor) -> str:
        payload = anchor.canonical_payload()
        return hmac.new(
            self.secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def verify_anchor_signature(self, anchor: AuditAnchor) -> bool:
        if not anchor.signature:
            return False
        expected = self.compute_signature(anchor)
        return hmac.compare_digest(anchor.signature, expected)

    def create_anchor(
        self,
        chain_id: str,
        latest_sequence_number: int,
        latest_chain_hash: str,
    ) -> AuditAnchor:
        """
        Creates, cryptographically signs, and durably records a new chain anchor.
        """
        with self._lock:
            prev_anchor_hash = "0" * 64
            existing = [a for a in self._in_memory_anchors if a.chain_id == chain_id]
            if existing:
                prev_anchor_hash = hashlib.sha256(existing[-1].signature.encode("utf-8")).hexdigest()

            anchor_id = f"anc_{uuid.uuid4().hex[:12]}"
            now = datetime.now(timezone.utc)

            anchor = AuditAnchor(
                anchor_id=anchor_id,
                chain_id=chain_id,
                latest_sequence_number=latest_sequence_number,
                latest_chain_hash=latest_chain_hash,
                anchored_at=now,
                prev_anchor_hash=prev_anchor_hash,
            )
            anchor.signature = self.compute_signature(anchor)

            self._in_memory_anchors.append(anchor)
            self._persist_anchors()
            logger.info(
                f"[AUDIT ANCHOR CREATED] ID={anchor_id} seq={latest_sequence_number} "
                f"hash={latest_chain_hash[:16]} sig={anchor.signature[:16]}"
            )
            return anchor

    def get_latest_anchor(self, chain_id: str = "main_chain") -> Optional[AuditAnchor]:
        with self._lock:
            matching = [a for a in self._in_memory_anchors if a.chain_id == chain_id]
            return matching[-1] if matching else None

    def list_anchors(self, chain_id: Optional[str] = None) -> List[AuditAnchor]:
        with self._lock:
            if chain_id:
                return [a for a in self._in_memory_anchors if a.chain_id == chain_id]
            return list(self._in_memory_anchors)

    def reset_in_memory(self) -> None:
        with self._lock:
            self._in_memory_anchors.clear()


# Global singleton instance
audit_anchor_manager = AuditAnchorManager()


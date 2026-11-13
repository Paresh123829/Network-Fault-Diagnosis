"""
Unit tests for Milestone 6.1 independent cryptographic audit anchors.
"""

import os
import tempfile
import pytest

from services.ai.agents.oversight.audit_anchor import (
    AuditAnchor,
    AuditAnchorManager,
)


def test_anchor_creation_and_signature():
    with tempfile.TemporaryDirectory() as td:
        mgr = AuditAnchorManager(anchor_dir=td, secret_key="super_secret_test_key")
        anchor = mgr.create_anchor(
            chain_id="test_chain",
            latest_sequence_number=10,
            latest_chain_hash="a" * 64,
        )

        assert anchor.anchor_id.startswith("anc_")
        assert anchor.latest_sequence_number == 10
        assert anchor.latest_chain_hash == "a" * 64
        assert len(anchor.signature) == 64
        assert mgr.verify_anchor_signature(anchor) is True


def test_anchor_detects_signature_tamper():
    with tempfile.TemporaryDirectory() as td:
        mgr = AuditAnchorManager(anchor_dir=td, secret_key="super_secret_test_key")
        anchor = mgr.create_anchor(
            chain_id="test_chain",
            latest_sequence_number=5,
            latest_chain_hash="b" * 64,
        )

        # Alter hash without resigning
        anchor.latest_chain_hash = "c" * 64
        assert mgr.verify_anchor_signature(anchor) is False


def test_anchor_persistence_across_instances():
    with tempfile.TemporaryDirectory() as td:
        mgr1 = AuditAnchorManager(anchor_dir=td, secret_key="static_test_key")
        a1 = mgr1.create_anchor("chain_01", 1, "1" * 64)
        a2 = mgr1.create_anchor("chain_01", 2, "2" * 64)

        # New manager instance reading disk
        mgr2 = AuditAnchorManager(anchor_dir=td, secret_key="static_test_key")
        anchors = mgr2.list_anchors("chain_01")
        assert len(anchors) == 2
        assert anchors[-1].latest_sequence_number == 2
        assert anchors[-1].latest_chain_hash == "2" * 64
        assert mgr2.verify_anchor_signature(anchors[-1]) is True


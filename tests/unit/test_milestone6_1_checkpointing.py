"""
Unit tests for Milestone 6.1 persistent checkpointing subsystem.
"""

import os
import tempfile
import pytest

import services.ai.orchestrator
from services.ai.orchestrator.checkpointer import (
    FileCheckpointSaver,
    get_persistent_checkpointer,
)


def test_file_checkpoint_saver_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        cp_path = os.path.join(td, "checkpoints.pkl")
        saver1 = FileCheckpointSaver(filepath=cp_path)

        config = {"configurable": {"thread_id": "thread_unit_01", "checkpoint_ns": ""}}
        checkpoint = {
            "v": 1,
            "id": "cp_001",
            "ts": "2026-11-13T00:00:00Z",
            "channel_values": {"msg": "hello_checkpoint"},
            "channel_versions": {"msg": 1},
            "versions_seen": {},
            "pending_sends": [],
        }
        metadata = {"source": "unit_test", "step": 1, "writes": {}, "parents": {}}

        # Save in process 1
        new_config = saver1.put(config, checkpoint, metadata, {"msg": 1})
        assert os.path.exists(cp_path)

        # Re-open in simulated process 2
        saver2 = FileCheckpointSaver(filepath=cp_path)
        retrieved = saver2.get_tuple(new_config)

        assert retrieved is not None
        assert retrieved.checkpoint["id"] == "cp_001"
        assert retrieved.checkpoint["channel_values"]["msg"] == "hello_checkpoint"


def test_file_checkpoint_saver_delete_thread():
    with tempfile.TemporaryDirectory() as td:
        cp_path = os.path.join(td, "checkpoints.pkl")
        saver = FileCheckpointSaver(filepath=cp_path)

        config = {"configurable": {"thread_id": "thread_del_01", "checkpoint_ns": ""}}
        checkpoint = {
            "v": 1,
            "id": "cp_del_001",
            "ts": "2026-11-13T00:00:00Z",
            "channel_values": {"val": 42},
            "channel_versions": {"val": 1},
            "versions_seen": {},
            "pending_sends": [],
        }
        new_config = saver.put(config, checkpoint, {}, {"val": 1})
        assert saver.get_tuple(new_config) is not None

        saver.delete_thread("thread_del_01")
        assert saver.get_tuple(new_config) is None


def test_get_persistent_checkpointer_modes():
    # Memory mode
    cp_mem = get_persistent_checkpointer(mode="memory")
    assert cp_mem is not None

    # File mode
    with tempfile.TemporaryDirectory() as td:
        fpath = os.path.join(td, "test.pkl")
        cp_file = get_persistent_checkpointer(mode="file", filepath=fpath)
        assert isinstance(cp_file, FileCheckpointSaver)

    # Auto mode
    cp_auto = get_persistent_checkpointer(mode="auto")
    assert cp_auto is not None


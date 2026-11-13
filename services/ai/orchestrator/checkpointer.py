"""
checkpointer.py — Persistent Checkpointing Subsystem for LangGraph Remediation Workflows.

Supports official MongoDB persistence via MongoDBSaver as well as a durable FileCheckpointSaver
for restart recovery testing and offline/isolated execution environments.
"""

from __future__ import annotations

from collections import defaultdict
import logging
import os
import pickle
import threading
from typing import Any, Dict, Optional, Sequence
from types import TracebackType

from pymongo import MongoClient

try:
    import services.ai.orchestrator  # fallback uuid_utils if needed
except ImportError:
    pass

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    RunnableConfig,
)
from langgraph.checkpoint.memory import MemorySaver, InMemorySaver

try:
    from langgraph.checkpoint.mongodb import MongoDBSaver
    HAS_MONGO_SAVER = True
except ImportError:
    MongoDBSaver = None
    HAS_MONGO_SAVER = False

logger = logging.getLogger(__name__)


def _to_plain_dict(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _to_plain_dict(v) for k, v in d.items()}
    return d


def _make_storage_defaultdict(d: Optional[Dict[str, Any]] = None) -> defaultdict:
    storage = defaultdict(lambda: defaultdict(dict))
    if d:
        for thread_id, ns_dict in d.items():
            for ns, cp_dict in ns_dict.items():
                for cp_id, cp_val in cp_dict.items():
                    storage[thread_id][ns][cp_id] = cp_val
    return storage


class FileCheckpointSaver(InMemorySaver):
    """
    Durable file-backed checkpointer for LangGraph workflows.
    Serializes state atomically to disk on every put / write, enabling
    safe recovery across distinct OS processes without requiring external daemons.
    """

    def __init__(self, filepath: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.filepath = filepath
        self._file_lock = threading.RLock()
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        with self._file_lock:
            if os.path.exists(self.filepath) and os.path.getsize(self.filepath) > 0:
                try:
                    with open(self.filepath, "rb") as f:
                        data = pickle.load(f)
                        raw_storage = data.get("storage", {})
                        raw_writes = data.get("writes", {})
                        self.storage = _make_storage_defaultdict(raw_storage)
                        self.writes = defaultdict(dict, raw_writes)
                        self.blobs = defaultdict(dict, data.get("blobs", {}))
                    logger.info(f"Loaded persistent checkpoints from {self.filepath}")
                except Exception as e:
                    logger.error(f"Error loading checkpoints from {self.filepath}: {e}")

    def _save_to_disk(self) -> None:
        with self._file_lock:
            tmp_path = f"{self.filepath}.tmp.{os.getpid()}"
            try:
                payload = {
                    "storage": _to_plain_dict(self.storage),
                    "writes": _to_plain_dict(self.writes),
                    "blobs": _to_plain_dict(self.blobs),
                }
                with open(tmp_path, "wb") as f:
                    pickle.dump(payload, f)
                # Atomic replace on Windows/POSIX
                if os.path.exists(self.filepath):
                    os.replace(tmp_path, self.filepath)
                else:
                    os.rename(tmp_path, self.filepath)
            except Exception as e:
                logger.error(f"Failed to persist checkpoints to {self.filepath}: {e}")
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        res = super().put(config, checkpoint, metadata, new_versions)
        self._save_to_disk()
        return res

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        super().put_writes(config, writes, task_id, task_path)
        self._save_to_disk()

    def delete_thread(self, thread_id: str) -> None:
        super().delete_thread(thread_id)
        self._save_to_disk()


def get_persistent_checkpointer(
    mode: str = "auto",
    mongo_uri: Optional[str] = None,
    db_name: Optional[str] = None,
    filepath: Optional[str] = None,
) -> BaseCheckpointSaver:
    """
    Factory function returning a persistent checkpointer.
    
    Modes:
      - 'mongo': Forces MongoDBSaver.
      - 'file': Forces FileCheckpointSaver on disk.
      - 'memory': Uses transient in-memory MemorySaver.
      - 'auto': Prefers MongoDB if reachable, falls back to FileCheckpointSaver.
    """
    uri = mongo_uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    database_name = db_name or os.environ.get("MONGO_DB_NAME", "cnt_fault_diagnosis")

    if mode in ("mongo", "auto") and HAS_MONGO_SAVER:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            logger.info(f"Using persistent MongoDBSaver on {uri}/{database_name}")
            return MongoDBSaver(
                client=client,
                db_name=database_name,
                checkpoint_collection_name="langgraph_checkpoints",
                writes_collection_name="langgraph_checkpoint_writes",
            )
        except Exception as e:
            if mode == "mongo":
                logger.error(f"MongoDB checkpointer requested but connection failed: {e}")
                raise
            logger.warning(f"MongoDB not available for checkpointer ({e}); falling back to file checkpointer.")

    if mode in ("file", "auto"):
        target_file = filepath or os.environ.get("CHECKPOINT_FILEPATH", "data/checkpoints/workflow_checkpoints.pkl")
        return FileCheckpointSaver(filepath=target_file)

    return MemorySaver()

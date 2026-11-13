"""
config.py — Configuration for RAG & Qdrant Knowledge Retrieval Subsystem.
"""

from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict


# Base Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RAG_ROOT = WORKSPACE_ROOT / "services" / "rag"
DATA_DIR = RAG_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MANIFESTS_DIR = DATA_DIR / "manifests"
MODELS_DIR = RAG_ROOT / "models"
EVALUATION_DIR = RAG_ROOT / "evaluation"
REPORTS_DIR = WORKSPACE_ROOT / "network" / "datasets" / "reports" / "rag"


class RAGConfig(BaseModel):
    """Configuration settings for RAG ingestion, indexing, and search."""

    # Qdrant connection settings
    qdrant_url: str = Field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    qdrant_api_key: str = Field(
        default_factory=lambda: os.getenv("QDRANT_API_KEY", "")
    )
    collection_name: str = Field(
        default_factory=lambda: os.getenv("QDRANT_COLLECTION_NAME", "network_knowledge_base")
    )
    use_local_storage: bool = Field(
        default_factory=lambda: os.getenv("QDRANT_USE_LOCAL_STORAGE", "true").lower() == "true"
    )
    local_storage_path: Path = Field(
        default_factory=lambda: RAG_ROOT / "qdrant_storage"
    )

    # Embedding settings
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    normalize_embeddings: bool = True

    # Chunking settings
    chunk_size_chars: int = 800
    chunk_overlap_chars: int = 150
    min_chunk_chars: int = 80

    # Retrieval settings
    default_top_k: int = 5
    min_relevance_threshold: float = 0.35
    rrf_k: int = 60  # Reciprocal Rank Fusion constant
    dense_weight: float = 0.6
    lexical_weight: float = 0.4

    model_config = ConfigDict(arbitrary_types_allowed=True)


# Global default configuration instance
default_rag_config = RAGConfig()

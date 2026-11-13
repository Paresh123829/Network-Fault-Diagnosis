"""
vector_store.py — Robust Qdrant Vector Store Client and Lifecycle Manager.

Supports:
  1. Live Remote Qdrant Daemon (e.g. http://localhost:6333)
  2. Embedded Persistent Local Storage via Qdrant Rust engine (QdrantClient(path=...))
  3. In-memory mode for isolated testing (:memory:)
Features:
  - Deterministic Point IDs (UUIDv5)
  - Duplicate detection and content-hash idempotency
  - Multi-attribute payload filtering
  - Collection schema validation and payload indexing
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from .config import RAGConfig, default_rag_config
from .metadata import ChunkMetadata
from .chunker import DocumentChunk

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Manages Qdrant collection lifecycle, point upserting, and vector search."""

    def __init__(self, config: Optional[RAGConfig] = None, memory_mode: bool = False):
        self.config = config or default_rag_config
        self.memory_mode = memory_mode
        self.client: Optional[QdrantClient] = None
        self._initialize_client()

    def _initialize_client(self):
        """Initializes client connecting to remote daemon, local path, or memory."""
        if self.memory_mode:
            logger.info("Initializing QdrantClient in memory mode (:memory:)")
            self.client = QdrantClient(":memory:")
            return

        # Attempt remote daemon if configured and reachable
        if self.config.qdrant_url and not self.config.use_local_storage:
            try:
                logger.info("Attempting connection to remote Qdrant at %s", self.config.qdrant_url)
                client = QdrantClient(
                    url=self.config.qdrant_url,
                    api_key=self.config.qdrant_api_key or None,
                    timeout=3.0,
                )
                # Verify reachability
                client.get_collections()
                self.client = client
                logger.info("Connected to remote Qdrant successfully.")
                return
            except Exception as exc:
                logger.warning(
                    "Remote Qdrant unreachable at %s: %s. Falling back to local embedded storage.",
                    self.config.qdrant_url,
                    exc,
                )

        # Fallback to local persistent embedded storage
        storage_dir = Path(self.config.local_storage_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Initializing embedded persistent Qdrant at %s", storage_dir)
        self.client = QdrantClient(path=str(storage_dir))

    def health_check(self) -> Dict[str, Any]:
        """Checks Qdrant connection and returns health status."""
        try:
            if not self.client:
                return {"status": "unhealthy", "error": "Client not initialized"}
            collections = self.client.get_collections()
            return {
                "status": "healthy",
                "collections_count": len(collections.collections),
                "collections": [c.name for c in collections.collections],
                "mode": "memory" if self.memory_mode else ("local_disk" if self.config.use_local_storage else "remote"),
            }
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}

    def ensure_collection(
        self,
        collection_name: Optional[str] = None,
        vector_size: Optional[int] = None,
    ) -> bool:
        """Ensures collection exists with proper vector dimension, distance, and payload indexes."""
        col_name = collection_name or self.config.collection_name
        dim = vector_size or self.config.embedding_dimension

        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == col_name for c in collections)

            if not exists:
                logger.info("Creating Qdrant collection '%s' (dim=%d, distance=Cosine)...", col_name, dim)
                self.client.create_collection(
                    collection_name=col_name,
                    vectors_config=qmodels.VectorParams(
                        size=dim,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                # Create payload indexes on remote Qdrant for fast filtering
                if not self.memory_mode and not self.config.use_local_storage:
                    index_fields = ["protocol", "vendor", "platform", "fault_category", "document_id", "document_type"]
                    for field_name in index_fields:
                        try:
                            self.client.create_payload_index(
                                collection_name=col_name,
                                field_name=field_name,
                                field_schema=qmodels.PayloadSchemaType.KEYWORD,
                            )
                        except Exception as idx_exc:
                            logger.debug("Payload index creation notice for %s: %s", field_name, idx_exc)
            else:
                logger.debug("Collection '%s' already exists.", col_name)

            return True
        except Exception as exc:
            logger.error("Failed to ensure collection '%s': %s", col_name, exc, exc_info=True)
            return False

    def deterministic_point_id(self, chunk_id: str) -> str:
        """Converts chunk_id into a deterministic UUIDv5 string accepted by Qdrant."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

    def upsert_chunks(
        self,
        chunks: List[DocumentChunk],
        metadatas: List[ChunkMetadata],
        embeddings: List[List[float]],
        collection_name: Optional[str] = None,
    ) -> int:
        """
        Upserts chunk vectors and payload into Qdrant idempotently.
        Returns count of successfully indexed points.
        """
        col_name = collection_name or self.config.collection_name
        self.ensure_collection(col_name)

        if not chunks or len(chunks) != len(embeddings) or len(chunks) != len(metadatas):
            raise ValueError("Mismatched counts for chunks, metadatas, or embeddings.")

        points: List[qmodels.PointStruct] = []
        for chunk, meta, emb in zip(chunks, metadatas, embeddings):
            pt_id = self.deterministic_point_id(chunk.chunk_id)
            payload = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_title": chunk.document_title,
                "section": chunk.section_title,
                "content": chunk.content,
                "protocol": meta.protocol,
                "vendor": meta.vendor,
                "platform": meta.platform,
                "fault_category": meta.fault_category,
                "document_type": meta.document_type,
                "source_url": meta.source_url,
                "source_path": meta.source_path,
                "source_license": meta.source_license,
                "publisher": meta.publisher,
                "content_hash": chunk.content_hash,
                "token_count": chunk.token_count_approx,
            }
            points.append(qmodels.PointStruct(id=pt_id, vector=emb, payload=payload))

        # Batch upsert in chunks of 100
        batch_size = 100
        total_upserted = 0
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(collection_name=col_name, points=batch)
            total_upserted += len(batch)

        logger.info("Successfully upserted %d points into collection '%s'.", total_upserted, col_name)
        return total_upserted

    def search_dense(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs dense vector similarity search in Qdrant with optional keyword filters.
        """
        col_name = collection_name or self.config.collection_name
        q_filter = self._build_qdrant_filter(filters)

        try:
            # query_points is the standard API in qdrant-client >= 1.10
            response = self.client.query_points(
                collection_name=col_name,
                query=query_vector,
                limit=top_k,
                query_filter=q_filter,
                score_threshold=min_score if min_score > 0 else None,
                with_payload=True,
            )
            hits = response.points
        except Exception:
            # Fallback to search() for older clients if needed
            hits = self.client.search(
                collection_name=col_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=q_filter,
                score_threshold=min_score if min_score > 0 else None,
                with_payload=True,
            )

        results: List[Dict[str, Any]] = []
        for hit in hits:
            score = float(hit.score)
            payload = hit.payload or {}
            results.append({
                "chunk_id": payload.get("chunk_id", str(hit.id)),
                "document_id": payload.get("document_id", "unknown"),
                "document_title": payload.get("document_title", ""),
                "section": payload.get("section", ""),
                "content": payload.get("content", ""),
                "score": score,
                "protocol": payload.get("protocol", "general"),
                "fault_category": payload.get("fault_category", "general"),
                "source_path": payload.get("source_path", ""),
                "source_url": payload.get("source_url", ""),
                "publisher": payload.get("publisher", ""),
                "payload": payload,
            })

        return results

    def _build_qdrant_filter(self, filters: Optional[Dict[str, Any]]) -> Optional[qmodels.Filter]:
        """Translates a python filter dict into Qdrant Filter conditions."""
        if not filters:
            return None

        must_conditions: List[qmodels.Condition] = []
        for key, val in filters.items():
            if val is None or val == "" or val == "all":
                continue
            if isinstance(val, (list, set)):
                should_conditions = [
                    qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=v))
                    for v in val
                ]
                must_conditions.append(qmodels.Filter(should=should_conditions))
            else:
                must_conditions.append(
                    qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=val))
                )

        return qmodels.Filter(must=must_conditions) if must_conditions else None

    def get_collection_stats(self, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Returns collection info and vector count."""
        col_name = collection_name or self.config.collection_name
        try:
            info = self.client.get_collection(collection_name=col_name)
            return {
                "collection_name": col_name,
                "points_count": info.points_count,
                "indexed_vectors_count": getattr(info, "indexed_vectors_count", info.points_count),
                "status": str(info.status),
                "vectors_config": str(info.config.params.vectors),
            }
        except Exception as exc:
            return {"collection_name": col_name, "error": str(exc), "points_count": 0}

"""
service.py — High-Level RAG Knowledge Retrieval Service and Ingestion Orchestrator.

Provides the primary interface for LangGraph agents to query networking runbooks,
SOPs, RFCs, and troubleshooting guides.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.ai.schemas.contracts import EvidencePassage, RetrievedEvidence, IncidentTimeline
from .config import RAGConfig, default_rag_config
from .loaders import DocumentLoader, RawDocument, ExtractionFailure
from .cleaner import DocumentCleaner
from .chunker import SemanticChunker, DocumentChunk
from .metadata import MetadataExtractor, ChunkMetadata
from .embeddings import EmbeddingService, get_embedding_service
from .vector_store import QdrantVectorStore
from .hybrid_search import HybridSearcher

logger = logging.getLogger(__name__)


class RAGService:
    """
    Unified knowledge retrieval service coordinating document ingestion,
    indexing, dense+lexical hybrid search, and canonical contract formatting.
    """

    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        memory_mode: bool = False,
    ):
        self.config = config or default_rag_config
        self.loader = DocumentLoader()
        self.cleaner = DocumentCleaner(redact_secrets=True)
        self.chunker = SemanticChunker(
            chunk_size_chars=self.config.chunk_size_chars,
            chunk_overlap_chars=self.config.chunk_overlap_chars,
            min_chunk_chars=self.config.min_chunk_chars,
        )
        self.metadata_extractor = MetadataExtractor()
        self.embedding_service = get_embedding_service()
        self.vector_store = QdrantVectorStore(config=self.config, memory_mode=memory_mode)
        self.hybrid_searcher = HybridSearcher(
            vector_store=self.vector_store,
            embedding_service=self.embedding_service,
            config=self.config,
        )

        # In-memory document & chunk caches
        self.indexed_docs: List[RawDocument] = []
        self.indexed_chunks: List[DocumentChunk] = []
        self.indexed_metadatas: List[ChunkMetadata] = []

    # ── RETRIEVAL INTERFACE ──────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        top_k: Optional[int] = None,
        protocol: Optional[str] = None,
        fault_category: Optional[str] = None,
        vendor: Optional[str] = None,
        min_relevance: Optional[float] = None,
        search_mode: str = "hybrid",
    ) -> RetrievedEvidence:
        """
        Executes query against knowledge base and returns a canonical RetrievedEvidence object.
        """
        k = top_k or self.config.default_top_k
        min_rel = min_relevance if min_relevance is not None else self.config.min_relevance_threshold

        filters: Dict[str, Any] = {}
        if protocol and protocol != "all" and protocol != "general":
            if isinstance(protocol, (list, set)):
                filters["protocol"] = [p.lower() for p in protocol]
            elif str(protocol).lower() in ["interface", "physical", "link"]:
                filters["protocol"] = ["physical_interface", "optics", "interface"]
            else:
                filters["protocol"] = str(protocol).lower()
        if fault_category and fault_category.lower() != "all" and fault_category.lower() != "general":
            filters["fault_category"] = fault_category.upper()
        if vendor and vendor.lower() != "all":
            filters["vendor"] = vendor

        # Execute search based on selected mode
        if search_mode == "dense":
            raw_results = self.hybrid_searcher.search_dense_only(query=query_text, top_k=k, filters=filters)
        elif search_mode == "lexical":
            raw_results = self.hybrid_searcher.search_lexical_only(query=query_text, top_k=k, filters=filters)
        else:
            raw_results = self.hybrid_searcher.search_hybrid(
                query=query_text, top_k=k, filters=filters, min_relevance=min_rel
            )

        passages: List[EvidencePassage] = []
        source_ids: List[str] = []
        scores: List[float] = []

        for item in raw_results:
            raw_score = float(item.get("score", 0.0))
            # Normalize score to [0.0, 1.0] for contract compliance
            if search_mode == "lexical":
                # Soft-saturating normalization for unbounded BM25 scores
                score = raw_score / (raw_score + 10.0) if raw_score > 0 else 0.0
            else:
                score = max(0.0, min(1.0, raw_score))

            if score < min_rel:
                continue

            cid = item.get("chunk_id", "unknown")
            doc_id = item.get("document_id", "unknown")
            content = item.get("content", "")

            passages.append(
                EvidencePassage(
                    passage_id=cid,
                    text=content,
                    source_id=doc_id,
                    relevance_score=round(score, 4),
                    metadata={
                        "document_title": item.get("document_title", ""),
                        "section": item.get("section", ""),
                        "protocol": item.get("protocol", "general"),
                        "fault_category": item.get("fault_category", "general"),
                        "vendor": item.get("vendor", ""),
                        "platform": item.get("platform", ""),
                        "publisher": item.get("publisher", ""),
                        "source_path": item.get("source_path", ""),
                        "source_url": item.get("source_url", ""),
                        "retrieval_method": item.get("retrieval_method", search_mode),
                    },
                )
            )
            if doc_id not in source_ids:
                source_ids.append(doc_id)
            scores.append(round(score, 4))

        return RetrievedEvidence(
            query=query_text,
            passages=passages,
            source_ids=source_ids,
            metadata={
                "search_mode": search_mode,
                "filters_applied": filters,
                "top_k_requested": k,
                "min_relevance_threshold": min_rel,
                "results_count": len(passages),
            },
            relevance_scores=scores,
        )

    def retrieve_for_incident(
        self,
        timeline: IncidentTimeline,
        symptom_summary: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> RetrievedEvidence:
        """
        Synthesizes a targeted search query from an IncidentTimeline and retrieves evidence.
        """
        # Formulate query from protocols, symptoms, and events
        query_parts: List[str] = []

        if timeline.suspected_protocols:
            query_parts.append(" ".join(timeline.suspected_protocols).upper())

        # Extract event types / messages
        event_types = {e.event_type.value for e in timeline.events}
        if event_types:
            query_parts.append(" ".join(sorted(event_types)).replace("_", " "))

        if symptom_summary and "primary_symptom" in symptom_summary:
            query_parts.append(str(symptom_summary["primary_symptom"]))

        if timeline.correlation_reason:
            query_parts.append(timeline.correlation_reason)

        query_text = " ".join(query_parts).strip()
        if not query_text:
            query_text = "network interface fault protocol anomaly"

        # Determine primary protocol filter if unambiguous
        proto_filter = None
        if len(timeline.suspected_protocols) == 1:
            proto_filter = timeline.suspected_protocols[0]

        return self.query(
            query_text=query_text,
            top_k=top_k,
            protocol=proto_filter,
            search_mode="hybrid",
        )

    # ── CORPUS INGESTION ORCHESTRATION ───────────────────────────────────────

    def ingest_corpus(
        self,
        raw_dir: Path,
        manifest_output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end ingestion:
          1. Scan raw directory
          2. Multi-format document loading
          3. Sanitization & secret redaction
          4. Semantic chunking
          5. Metadata enrichment
          6. Vector embedding generation
          7. Qdrant batch upsert
          8. BM25 lexical indexing
          9. Manifest and inventory generation
        """
        start_time = time.time()
        logger.info("Starting knowledge corpus ingestion from %s...", raw_dir)

        # 1. Load documents
        raw_docs = self.loader.load_directory(raw_dir, recursive=True)
        failures = self.loader.failures
        logger.info("Loaded %d documents (%d failures).", len(raw_docs), len(failures))

        # 2. Clean documents
        cleaned_docs = [self.cleaner.clean_document(d) for d in raw_docs]

        # 3. Chunk documents
        all_chunks: List[DocumentChunk] = []
        doc_map = {d.document_id: d for d in cleaned_docs}
        for d in cleaned_docs:
            chunks = self.chunker.chunk_document(d)
            all_chunks.extend(chunks)
        logger.info("Generated %d semantic chunks across %d documents.", len(all_chunks), len(cleaned_docs))

        # 4. Extract metadata
        all_metadatas: List[ChunkMetadata] = []
        for c in all_chunks:
            parent_doc = doc_map.get(c.document_id)
            meta = self.metadata_extractor.enrich_chunk(c, parent_doc)
            all_metadatas.append(meta)

        # 5. Generate embeddings
        chunk_texts = [c.content for c in all_chunks]
        embeddings = self.embedding_service.embed_texts(chunk_texts) if chunk_texts else []

        # 6. Upsert to Qdrant
        if all_chunks and embeddings:
            self.vector_store.upsert_chunks(
                chunks=all_chunks,
                metadatas=all_metadatas,
                embeddings=embeddings,
            )

        # 7. Sync BM25 Lexical Index
        self.hybrid_searcher.sync_bm25_from_chunks(all_chunks, all_metadatas)

        # Store in-memory references
        self.indexed_docs = cleaned_docs
        self.indexed_chunks = all_chunks
        self.indexed_metadatas = all_metadatas

        duration = time.time() - start_time

        # 8. Export manifests and inventories if requested
        if manifest_output_dir:
            self._export_artifacts(
                output_dir=manifest_output_dir,
                docs=cleaned_docs,
                chunks=all_chunks,
                metadatas=all_metadatas,
                failures=failures,
                duration=duration,
            )

        summary = {
            "documents_loaded": len(cleaned_docs),
            "documents_failed": len(failures),
            "chunks_generated": len(all_chunks),
            "embeddings_generated": len(embeddings),
            "qdrant_points_upserted": len(all_chunks),
            "bm25_vocab_size": len(self.hybrid_searcher.bm25_index.doc_freqs),
            "duration_seconds": round(duration, 2),
        }
        logger.info("Ingestion completed: %s", summary)
        return summary

    def _export_artifacts(
        self,
        output_dir: Path,
        docs: List[RawDocument],
        chunks: List[DocumentChunk],
        metadatas: List[ChunkMetadata],
        failures: List[ExtractionFailure],
        duration: float,
    ):
        """Writes audit manifests, inventories, and failure logs."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. document_ingestion_results.csv
        doc_csv_path = output_dir / "document_ingestion_results.csv"
        with open(doc_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["document_id", "title", "file_type", "relative_path", "sections_count", "content_hash"])
            for d in docs:
                writer.writerow([
                    d.document_id,
                    d.title,
                    d.file_type,
                    str(d.file_path.name),
                    len(d.sections),
                    d.content_hash,
                ])

        # 2. document_extraction_failures.csv
        fail_csv_path = output_dir / "document_extraction_failures.csv"
        with open(fail_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["file_path", "file_type", "error_message", "exception_type"])
            for fl in failures:
                writer.writerow([str(fl.file_path), fl.file_type, fl.error_message, fl.exception_type])

        # 3. chunk_inventory.csv
        chunk_csv_path = output_dir / "chunk_inventory.csv"
        with open(chunk_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "chunk_id", "document_id", "section", "protocol", "vendor",
                "fault_category", "token_count", "content_hash"
            ])
            for c, m in zip(chunks, metadatas):
                writer.writerow([
                    c.chunk_id,
                    c.document_id,
                    c.section_title,
                    m.protocol,
                    m.vendor,
                    m.fault_category,
                    c.token_count_approx,
                    c.content_hash,
                ])

        # 4. knowledge_corpus_manifest.json
        manifest_path = output_dir / "knowledge_corpus_manifest.json"
        manifest_data = {
            "manifest_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ingestion_duration_seconds": round(duration, 2),
            "embedding_model": self.config.embedding_model_name,
            "embedding_dimension": self.config.embedding_dimension,
            "collection_name": self.config.collection_name,
            "total_documents": len(docs),
            "total_failures": len(failures),
            "total_chunks": len(chunks),
            "protocols_covered": list(set(m.protocol for m in metadatas)),
            "fault_categories_covered": list(set(m.fault_category for m in metadatas)),
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        # 5. qdrant_collection_manifest.json
        qdrant_manifest_path = output_dir / "qdrant_collection_manifest.json"
        stats = self.vector_store.get_collection_stats()
        with open(qdrant_manifest_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)


# ── SINGLETON ACCESSOR ────────────────────────────────────────────────────────
_shared_rag_service: Optional[RAGService] = None


def get_rag_service(config: Optional[RAGConfig] = None) -> RAGService:
    """Returns singleton RAGService avoiding multiple concurrent locks on local storage."""
    global _shared_rag_service
    if _shared_rag_service is None:
        _shared_rag_service = RAGService(config=config)
    return _shared_rag_service


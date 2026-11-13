"""
hybrid_search.py — Dense + Lexical (BM25) Hybrid Search with Reciprocal Rank Fusion.

Combines semantic embedding similarity with exact keyword matching for network
protocols, interfaces, and syslog tokens.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import RAGConfig, default_rag_config
from .chunker import DocumentChunk
from .vector_store import QdrantVectorStore
from .embeddings import EmbeddingService, get_embedding_service

logger = logging.getLogger(__name__)


class BM25Index:
    """In-memory BM25 lexical index for fast keyword matching across chunks."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_chunks: List[Dict[str, Any]] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: Dict[str, int] = defaultdict(int)
        self.num_docs: int = 0
        self.tokenized_corpus: List[List[str]] = []

    def tokenize(self, text: str) -> List[str]:
        """Tokenizes text preserving network identifiers and syntax."""
        # Split on whitespace and non-alphanumeric except hyphen, underscore, slash, percent
        tokens = re.findall(r"[\w\-\/\%]+", text.lower())
        return [t for t in tokens if len(t) > 1]

    def build_index(self, chunks: List[Dict[str, Any]]):
        """Indexes a list of chunk payload dictionaries."""
        self.corpus_chunks = chunks
        self.num_docs = len(chunks)
        self.doc_lengths = []
        self.doc_freqs = defaultdict(int)
        self.tokenized_corpus = []

        total_len = 0
        for chunk in chunks:
            tokens = self.tokenize(chunk.get("content", ""))
            self.tokenized_corpus.append(tokens)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            unique_tokens = set(tokens)
            for t in unique_tokens:
                self.doc_freqs[t] += 1

        self.avg_doc_len = (total_len / self.num_docs) if self.num_docs > 0 else 0.0
        logger.info("Built BM25 index over %d chunks (vocab size: %d).", self.num_docs, len(self.doc_freqs))

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Scores all indexed chunks against query using BM25."""
        if not self.corpus_chunks:
            return []

        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        scores: List[Tuple[int, float]] = []

        for idx, tokens in enumerate(self.tokenized_corpus):
            chunk = self.corpus_chunks[idx]

            # Apply metadata filters if provided
            if filters:
                mismatch = False
                for f_key, f_val in filters.items():
                    if f_val and f_val != "all":
                        chunk_val = chunk.get(f_key)
                        if isinstance(f_val, (list, set)):
                            if chunk_val not in f_val:
                                mismatch = True
                                break
                        elif chunk_val != f_val:
                            mismatch = True
                            break
                if mismatch:
                    continue

            # Compute BM25 score
            score = 0.0
            doc_len = self.doc_lengths[idx]
            token_counts = Counter(tokens)

            for qt in query_tokens:
                if qt not in self.doc_freqs:
                    continue
                df = self.doc_freqs[qt]
                # Standard Lucene/BM25 IDF formula
                idf = math.log(1.0 + (self.num_docs - df + 0.5) / (df + 0.5))
                tf = token_counts[qt]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / (self.avg_doc_len or 1.0)))
                score += idf * (numerator / denominator)

            if score > 0.0:
                scores.append((idx, score))

        # Sort descending by score
        scores.sort(key=lambda x: x[1], reverse=True)

        results: List[Dict[str, Any]] = []
        for idx, score in scores[:top_k]:
            chunk_copy = dict(self.corpus_chunks[idx])
            chunk_copy["score"] = score
            chunk_copy["retrieval_method"] = "lexical_bm25"
            results.append(chunk_copy)

        return results


class HybridSearcher:
    """
    Combines dense vector retrieval and BM25 lexical retrieval using Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        embedding_service: Optional[EmbeddingService] = None,
        config: Optional[RAGConfig] = None,
    ):
        self.vector_store = vector_store
        self.embedding_service = embedding_service or get_embedding_service()
        self.config = config or default_rag_config
        self.bm25_index = BM25Index()

    def sync_bm25_from_chunks(self, chunks: List[DocumentChunk], metadatas: List[Any]):
        """Populates BM25 index from ingested chunks and metadata."""
        bm25_data = []
        for c, m in zip(chunks, metadatas):
            item = {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "document_title": c.document_title,
                "section": c.section_title,
                "content": c.content,
                "protocol": getattr(m, "protocol", "general"),
                "vendor": getattr(m, "vendor", "general"),
                "platform": getattr(m, "platform", "any"),
                "fault_category": getattr(m, "fault_category", "general"),
                "source_path": getattr(m, "source_path", ""),
                "source_url": getattr(m, "source_url", ""),
                "publisher": getattr(m, "publisher", "Unknown"),
            }
            bm25_data.append(item)
        self.bm25_index.build_index(bm25_data)

    def search_dense_only(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Executes dense vector search alone."""
        query_vec = self.embedding_service.embed_query(query)
        results = self.vector_store.search_dense(
            query_vector=query_vec,
            top_k=top_k,
            filters=filters,
        )
        for r in results:
            r["retrieval_method"] = "dense_vector"
        return results

    def search_lexical_only(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Executes BM25 lexical search alone."""
        return self.bm25_index.search(query=query, top_k=top_k, filters=filters)

    def search_hybrid(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        min_relevance: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes both dense and lexical searches, fusing rankings with Reciprocal Rank Fusion (RRF).
        """
        threshold = min_relevance if min_relevance is not None else self.config.min_relevance_threshold
        candidate_k = max(top_k * 3, 15)

        # 1. Dense Search
        dense_results = self.search_dense_only(query=query, top_k=candidate_k, filters=filters)

        # 2. Lexical Search
        lexical_results = self.search_lexical_only(query=query, top_k=candidate_k, filters=filters)

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF Score = w_dense / (k + rank_dense) + w_lex / (k + rank_lex)
        rrf_k = self.config.rrf_k
        w_dense = self.config.dense_weight
        w_lex = self.config.lexical_weight

        rrf_scores: Dict[str, float] = defaultdict(float)
        merged_chunks: Dict[str, Dict[str, Any]] = {}
        dense_ranks: Dict[str, int] = {}
        lexical_ranks: Dict[str, int] = {}

        for rank, item in enumerate(dense_results, start=1):
            cid = item["chunk_id"]
            dense_ranks[cid] = rank
            rrf_scores[cid] += w_dense / (rrf_k + rank)
            if cid not in merged_chunks:
                merged_chunks[cid] = dict(item)

        for rank, item in enumerate(lexical_results, start=1):
            cid = item["chunk_id"]
            lexical_ranks[cid] = rank
            rrf_scores[cid] += w_lex / (rrf_k + rank)
            if cid not in merged_chunks:
                merged_chunks[cid] = dict(item)

        if not rrf_scores:
            return []

        # Normalize RRF scores to [0.0, 1.0]
        max_possible_rrf = (w_dense / (rrf_k + 1)) + (w_lex / (rrf_k + 1))
        fused_items: List[Dict[str, Any]] = []

        for cid, raw_score in rrf_scores.items():
            norm_score = min(raw_score / max_possible_rrf, 1.0)
            if norm_score >= threshold:
                item = merged_chunks[cid]
                item["score"] = round(norm_score, 4)
                item["rrf_score"] = round(raw_score, 6)
                item["dense_rank"] = dense_ranks.get(cid)
                item["lexical_rank"] = lexical_ranks.get(cid)
                item["retrieval_method"] = (
                    "hybrid_fusion"
                    if cid in dense_ranks and cid in lexical_ranks
                    else ("dense_only" if cid in dense_ranks else "lexical_only")
                )
                fused_items.append(item)

        # Sort descending by fused score, stable tie-breaking by chunk_id
        fused_items.sort(key=lambda x: (x["score"], x["chunk_id"]), reverse=True)

        return fused_items[:top_k]


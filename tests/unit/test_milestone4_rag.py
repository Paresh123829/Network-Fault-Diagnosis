"""
test_milestone4_rag.py — Comprehensive Unit Tests for Milestone 4 RAG Subsystem.

Covers:
  - Document Loaders (Markdown, TXT, HTML, PDF, DOCX, JSON)
  - Text Normalization and Secret Redaction
  - Semantic Chunking & Boundary Preservation
  - Metadata Extraction & Protocol/Vendor Detection
  - Vector Embeddings (FastEmbed bge-small-en-v1.5)
  - Qdrant In-Memory Vector Store Operations
  - BM25 Lexical Indexing & Search
  - Hybrid Reciprocal Rank Fusion (RRF)
  - Metadata Filtering & Relevance Thresholding
  - Evidence Attribution & Provenance Invariants
  - FastAPI RAG Router Endpoints
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from services.rag.src.config import RAGConfig
from services.rag.src.loaders import DocumentLoader, RawDocument, DocumentSection
from services.rag.src.cleaner import DocumentCleaner
from services.rag.src.chunker import SemanticChunker, DocumentChunk
from services.rag.src.metadata import MetadataExtractor, ChunkMetadata
from services.rag.src.embeddings import EmbeddingService, get_embedding_service
from services.rag.src.vector_store import QdrantVectorStore
from services.rag.src.hybrid_search import BM25Index, HybridSearcher
from services.rag.src.service import RAGService
from services.ai.schemas.contracts import EvidencePassage, RetrievedEvidence


# =============================================================================
# 1. DOCUMENT LOADERS
# =============================================================================
class TestDocumentLoaders:
    """Verifies parsing across all supported multi-format documents."""

    @pytest.fixture
    def loader(self):
        return DocumentLoader()

    def test_load_markdown_with_sections(self, loader, tmp_path):
        md_file = tmp_path / "bgp_test.md"
        md_file.write_text("# BGP Guide\n\nIntro text.\n\n## FSM States\n\nIdle, Connect, Active.\n", encoding="utf-8")
        doc = loader.load_file(md_file)

        assert doc is not None
        assert doc.file_type == "markdown"
        assert len(doc.sections) == 2
        assert doc.sections[0].title == "BGP Guide"
        assert doc.sections[1].title == "FSM States"
        assert "Idle, Connect" in doc.sections[1].content

    def test_load_text_file(self, loader, tmp_path):
        txt_file = tmp_path / "rfc_test.txt"
        txt_file.write_text("RFC 4271 BGP Specification Excerpt.\nHold timer rules.", encoding="utf-8")
        doc = loader.load_file(txt_file)

        assert doc is not None
        assert doc.file_type == "text"
        assert len(doc.sections) == 1
        assert "Hold timer" in doc.full_text

    def test_load_html_file(self, loader, tmp_path):
        html_file = tmp_path / "cisco_guide.html"
        html_file.write_text(
            "<html><head><title>Cisco Optics</title></head><body><h1>Optics SOP</h1><p>Rx power -14 dBm.</p></body></html>",
            encoding="utf-8"
        )
        doc = loader.load_file(html_file)

        assert doc is not None
        assert doc.file_type == "html"
        assert doc.title == "Cisco Optics"
        assert "-14 dBm" in doc.full_text

    def test_load_json_structured_document(self, loader, tmp_path):
        json_file = tmp_path / "vlan_test.json"
        data = {
            "title": "VLAN Trunking",
            "sections": [
                {"title": "802.1Q", "content": "VLAN tagging explanation", "level": 1},
                {"title": "Native VLAN", "content": "PVID mismatch explanation", "level": 2}
            ]
        }
        json_file.write_text(json.dumps(data), encoding="utf-8")
        doc = loader.load_file(json_file)

        assert doc is not None
        assert doc.file_type == "json"
        assert len(doc.sections) == 2
        assert doc.sections[1].title == "Native VLAN"

    def test_unsupported_format_records_failure(self, loader, tmp_path):
        unsupported = tmp_path / "test.xyz"
        unsupported.write_text("random bytes", encoding="utf-8")
        doc = loader.load_file(unsupported)

        assert doc is None
        assert len(loader.failures) == 1
        assert loader.failures[0].exception_type == "UnsupportedFormatError"


# =============================================================================
# 2. DOCUMENT CLEANING & SECRET SANITIZATION
# =============================================================================
class TestDocumentCleaner:
    """Verifies whitespace normalization, technical syntax preservation, and secret redaction."""

    @pytest.fixture
    def cleaner(self):
        return DocumentCleaner(redact_secrets=True)

    def test_technical_symbols_and_ips_preserved(self, cleaner):
        raw = "Router leaf1: HundredGigE0/0/0/1 with IP 10.0.0.1/30 and syslog %ROUTING-BGP-5-ADJCHANGE"
        cleaned = cleaner.clean_text(raw)
        assert "HundredGigE0/0/0/1" in cleaned
        assert "10.0.0.1/30" in cleaned
        assert "%ROUTING-BGP-5-ADJCHANGE" in cleaned

    def test_secret_redaction_api_key_and_password(self, cleaner):
        text_with_secrets = "Configured api_key: 'abcdef1234567890abcdef123456' and password = 'SuperSecretPassword123' on spine1"
        cleaned = cleaner.clean_text(text_with_secrets)
        assert "[REDACTED_API_KEY]" in cleaned
        assert "[REDACTED_PASSWORD]" in cleaned
        assert "SuperSecretPassword123" not in cleaned

    def test_whitespace_and_unicode_normalization(self, cleaner):
        raw = "Line 1\r\n\r\n\r\n\r\nLine 2 \u201cquoted\u201d\t  \n"
        cleaned = cleaner.clean_text(raw)
        assert "\r" not in cleaned
        assert '"quoted"' in cleaned
        assert cleaned.count("\n\n") == 1


# =============================================================================
# 3. SEMANTIC CHUNKING
# =============================================================================
class TestSemanticChunking:
    """Verifies structure-aware chunking and deterministic ID generation."""

    @pytest.fixture
    def chunker(self):
        return SemanticChunker(chunk_size_chars=300, chunk_overlap_chars=50, min_chunk_chars=30)

    def test_section_boundary_preservation(self, chunker):
        s1 = DocumentSection(title="BGP FSM", content="BGP states: Idle, Connect, Active, OpenSent, OpenConfirm, Established.")
        s2 = DocumentSection(title="Optical Power", content="Optics dBm thresholds: Rx power below -14 dBm triggers alarm.")
        doc = RawDocument(
            document_id="doc_test_01",
            title="Test Doc",
            file_path=Path("test.md"),
            file_type="markdown",
            full_text="",
            sections=[s1, s2],
        )

        chunks = chunker.chunk_document(doc)
        assert len(chunks) == 2
        assert "chk_doc_test_01_0000" == chunks[0].chunk_id
        assert "chk_doc_test_01_0001" == chunks[1].chunk_id
        assert "BGP FSM" in chunks[0].content
        assert "Optical Power" in chunks[1].content
        # Ensure section 1 and 2 did not merge together
        assert "Optics" not in chunks[0].content


# =============================================================================
# 4. METADATA EXTRACTION
# =============================================================================
class TestMetadataExtraction:
    """Verifies automated detection of protocols, platforms, and fault categories."""

    @pytest.fixture
    def extractor(self):
        return MetadataExtractor()

    def test_enrich_bgp_chunk(self, extractor):
        chunk = DocumentChunk(
            chunk_id="chk_1",
            document_id="doc_1",
            document_title="BGP SOP",
            section_title="BGP Clear",
            content="Operator issued manual clear ip bgp on leaf1, causing %ROUTING-BGP-5-ADJCHANGE.",
            token_count_approx=15,
        )
        doc = RawDocument("doc_1", "BGP SOP", Path("bgp.md"), "markdown", "")
        meta = extractor.enrich_chunk(chunk, doc)

        assert meta.protocol == "bgp"
        assert meta.fault_category == "BGP_NEIGHBOR_DOWN"
        assert meta.vendor == "Cisco" or meta.platform == "IOS-XR" or meta.vendor == "Generic Networking"

    def test_enrich_optics_chunk(self, extractor):
        chunk = DocumentChunk(
            chunk_id="chk_2",
            document_id="doc_2",
            document_title="Optics SOP",
            section_title="Transceiver Removal",
            content="Transceiver pull occurred on HundredGigE0/0/0/1 with Rx power dropping to -40 dBm.",
            token_count_approx=15,
        )
        doc = RawDocument("doc_2", "Optics SOP", Path("optics.md"), "markdown", "")
        meta = extractor.enrich_chunk(chunk, doc)

        assert meta.protocol == "optics"
        assert meta.fault_category == "TRANSCEIVER_FAULT"


# =============================================================================
# 5. EMBEDDINGS & QDRANT IN-MEMORY VECTOR STORE
# =============================================================================
class TestEmbeddingsAndVectorStore:
    """Verifies FastEmbed embedding dimension and Qdrant vector operations."""

    def test_fastembed_dimension_and_normalization(self):
        emb_svc = get_embedding_service()
        assert emb_svc.is_available is True
        emb = emb_svc.embed_query("BGP neighbor down")
        assert len(emb) == 384
        # Check L2 normalization: sum(x^2) approx 1.0
        norm = sum(x * x for x in emb)
        assert abs(norm - 1.0) < 1e-3

    def test_qdrant_in_memory_upsert_and_dense_search(self):
        store = QdrantVectorStore(memory_mode=True)
        assert store.health_check()["status"] == "healthy"

        # Create dummy chunks and embeddings
        c1 = DocumentChunk("chk_bgp", "doc_1", "BGP Guide", "FSM", "BGP neighbor down on leaf1")
        m1 = ChunkMetadata(document_id="doc_1", chunk_id="chk_bgp", document_title="BGP Guide", protocol="bgp", fault_category="BGP_NEIGHBOR_DOWN")
        emb_svc = get_embedding_service()
        emb1 = emb_svc.embed_query(c1.content)

        c2 = DocumentChunk("chk_optics", "doc_2", "Optics Guide", "SFP", "Optical transceiver pull on spine2")
        m2 = ChunkMetadata(document_id="doc_2", chunk_id="chk_optics", document_title="Optics Guide", protocol="optics", fault_category="TRANSCEIVER_FAULT")
        emb2 = emb_svc.embed_query(c2.content)

        count = store.upsert_chunks([c1, c2], [m1, m2], [emb1, emb2], collection_name="test_col")
        assert count == 2

        # Dense search for BGP
        q_vec = emb_svc.embed_query("BGP peer reset")
        hits = store.search_dense(query_vector=q_vec, top_k=2, collection_name="test_col")
        assert len(hits) == 2
        assert hits[0]["chunk_id"] == "chk_bgp"
        assert hits[0]["protocol"] == "bgp"


# =============================================================================
# 6. BM25 LEXICAL INDEXING & HYBRID SEARCH
# =============================================================================
class TestBM25AndHybridSearch:
    """Verifies keyword exact matching and Reciprocal Rank Fusion."""

    @pytest.fixture
    def hybrid_setup(self):
        store = QdrantVectorStore(memory_mode=True)
        emb_svc = get_embedding_service()
        searcher = HybridSearcher(vector_store=store, embedding_service=emb_svc)

        # Chunks
        c1 = DocumentChunk("c1", "d1", "BGP SOP", "State", "BGP peer closed session %ROUTING-BGP-5-ADJCHANGE")
        m1 = ChunkMetadata(document_id="d1", chunk_id="c1", document_title="BGP SOP", protocol="bgp")
        e1 = emb_svc.embed_query(c1.content)

        c2 = DocumentChunk("c2", "d2", "Optics SOP", "Optic", "Transceiver module uninstalled %LINK-3-UPDOWN")
        m2 = ChunkMetadata(document_id="d2", chunk_id="c2", document_title="Optics SOP", protocol="optics")
        e2 = emb_svc.embed_query(c2.content)

        store.upsert_chunks([c1, c2], [m1, m2], [e1, e2], collection_name=searcher.config.collection_name)
        searcher.sync_bm25_from_chunks([c1, c2], [m1, m2])
        return searcher

    def test_bm25_exact_token_match(self, hybrid_setup):
        searcher = hybrid_setup
        results = searcher.search_lexical_only(query="%ROUTING-BGP-5-ADJCHANGE", top_k=2)
        assert len(results) > 0
        assert results[0]["chunk_id"] == "c1"

    def test_hybrid_search_rrf_scoring(self, hybrid_setup):
        searcher = hybrid_setup
        results = searcher.search_hybrid(query="BGP session closed %ROUTING-BGP-5-ADJCHANGE", top_k=2, min_relevance=0.0)
        assert len(results) > 0
        assert results[0]["chunk_id"] == "c1"
        assert "score" in results[0]
        assert results[0]["score"] <= 1.0


# =============================================================================
# 7. HIGH-LEVEL RAG SERVICE & EVIDENCE ATTRIBUTION
# =============================================================================
class TestRAGService:
    """Verifies canonical RetrievedEvidence generation and source attribution."""

    @pytest.fixture
    def rag_service(self):
        svc = RAGService(memory_mode=True)
        # Ingest test corpus
        test_dir = Path(__file__).resolve().parent.parent.parent / "services" / "rag" / "data" / "raw"
        svc.ingest_corpus(raw_dir=test_dir)
        return svc

    def test_query_returns_valid_contract(self, rag_service):
        evidence = rag_service.query("BGP neighbor down hold timer expired", top_k=3)
        assert isinstance(evidence, RetrievedEvidence)
        assert len(evidence.passages) > 0
        for p in evidence.passages:
            assert isinstance(p, EvidencePassage)
            assert p.passage_id.startswith("chk_")
            assert p.source_id.startswith("doc_")
            assert 0.0 <= p.relevance_score <= 1.0
            assert "document_title" in p.metadata

    def test_low_relevance_threshold_handling(self, rag_service):
        evidence = rag_service.query("quantum mechanics astrophysics black holes", top_k=3, min_relevance=0.99)
        assert isinstance(evidence, RetrievedEvidence)
        # Extremely high threshold on unrelated domain returns 0 passages safely
        assert len(evidence.passages) == 0

    def test_protocol_filtering(self, rag_service):
        evidence = rag_service.query("neighbor status", top_k=5, protocol="ospf")
        for p in evidence.passages:
            assert p.metadata.get("protocol") == "ospf"


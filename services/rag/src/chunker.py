"""
chunker.py — Structure-Aware Semantic Chunker for Network Knowledge Base.

Splits documents by logical sections, preserving headings, lists, tables,
and CLI blocks, avoiding arbitrary text truncation.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .loaders import RawDocument, DocumentSection

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """A semantic chunk ready for embedding and indexing."""
    chunk_id: str
    document_id: str
    document_title: str
    section_title: str
    content: str
    section_level: int = 1
    page_number: Optional[int] = None
    chunk_index: int = 0
    token_count_approx: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""


class SemanticChunker:
    """
    Structure-aware chunker that respects section boundaries and technical formatting.
    """

    def __init__(
        self,
        chunk_size_chars: int = 800,
        chunk_overlap_chars: int = 150,
        min_chunk_chars: int = 80,
    ):
        self.chunk_size_chars = chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars
        self.min_chunk_chars = min_chunk_chars

    def chunk_document(self, doc: RawDocument) -> List[DocumentChunk]:
        """Chunks a RawDocument into an ordered list of DocumentChunks."""
        all_chunks: List[DocumentChunk] = []
        global_idx = 0

        # Chunk each section independently to prevent cross-topic bleeding
        for section in doc.sections:
            sec_text = section.content.strip()
            if not sec_text:
                continue

            sec_chunks = self._chunk_section_text(
                doc_id=doc.document_id,
                doc_title=doc.title,
                section=section,
                start_index=global_idx,
            )
            all_chunks.extend(sec_chunks)
            global_idx += len(sec_chunks)

        # Fallback if no sections or all sections were empty
        if not all_chunks and doc.full_text.strip():
            fallback_section = DocumentSection(title=doc.title, content=doc.full_text)
            all_chunks = self._chunk_section_text(
                doc_id=doc.document_id,
                doc_title=doc.title,
                section=fallback_section,
                start_index=0,
            )

        return all_chunks

    def _chunk_section_text(
        self,
        doc_id: str,
        doc_title: str,
        section: DocumentSection,
        start_index: int,
    ) -> List[DocumentChunk]:
        """Splits a single section's text into size-bounded chunks."""
        text = section.content.strip()
        chunks: List[DocumentChunk] = []

        # If section is small enough, keep as single chunk with heading prefix
        if len(text) <= self.chunk_size_chars:
            header_prefix = f"[{doc_title} > {section.title}]\n" if section.title != doc_title else f"[{doc_title}]\n"
            content = f"{header_prefix}{text}" if not text.startswith("[") else text
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunk_id = f"chk_{doc_id}_{start_index:04d}"
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    document_title=doc_title,
                    section_title=section.title,
                    content=content,
                    section_level=section.section_level,
                    page_number=section.page_number,
                    chunk_index=start_index,
                    token_count_approx=len(content.split()),
                    metadata=dict(section.metadata),
                    content_hash=content_hash,
                )
            )
            return chunks

        # Break section by double-newlines (paragraphs / blocks)
        paragraphs = text.split("\n\n")
        current_paragraphs: List[str] = []
        current_len = 0
        local_idx = start_index

        for p in paragraphs:
            p_str = p.strip()
            if not p_str:
                continue

            # If adding this paragraph exceeds limit and we already have content
            if current_len + len(p_str) > self.chunk_size_chars and current_paragraphs:
                chunk_body = "\n\n".join(current_paragraphs)
                header_prefix = f"[{doc_title} > {section.title}]\n"
                full_chunk_text = f"{header_prefix}{chunk_body}"
                content_hash = hashlib.sha256(full_chunk_text.encode("utf-8")).hexdigest()
                chunk_id = f"chk_{doc_id}_{local_idx:04d}"

                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        document_title=doc_title,
                        section_title=section.title,
                        content=full_chunk_text,
                        section_level=section.section_level,
                        page_number=section.page_number,
                        chunk_index=local_idx,
                        token_count_approx=len(full_chunk_text.split()),
                        metadata=dict(section.metadata),
                        content_hash=content_hash,
                    )
                )
                local_idx += 1

                # Carry overlap
                overlap_chars = 0
                overlap_paras: List[str] = []
                for prev_p in reversed(current_paragraphs):
                    if overlap_chars + len(prev_p) <= self.chunk_overlap_chars:
                        overlap_paras.insert(0, prev_p)
                        overlap_chars += len(prev_p)
                    else:
                        break
                current_paragraphs = overlap_paras
                current_len = sum(len(x) for x in current_paragraphs)

            current_paragraphs.append(p_str)
            current_len += len(p_str)

        # Flush remaining paragraphs
        if current_paragraphs:
            chunk_body = "\n\n".join(current_paragraphs)
            if len(chunk_body) >= self.min_chunk_chars or not chunks:
                header_prefix = f"[{doc_title} > {section.title}]\n"
                full_chunk_text = f"{header_prefix}{chunk_body}"
                content_hash = hashlib.sha256(full_chunk_text.encode("utf-8")).hexdigest()
                chunk_id = f"chk_{doc_id}_{local_idx:04d}"

                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        document_id=doc_id,
                        document_title=doc_title,
                        section_title=section.title,
                        content=full_chunk_text,
                        section_level=section.section_level,
                        page_number=section.page_number,
                        chunk_index=local_idx,
                        token_count_approx=len(full_chunk_text.split()),
                        metadata=dict(section.metadata),
                        content_hash=content_hash,
                    )
                )

        return chunks


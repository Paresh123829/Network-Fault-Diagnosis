"""
loaders.py — Multi-format Document Loaders for Network Knowledge Base.

Supported formats:
  - Markdown (.md, .markdown)
  - Plain text (.txt)
  - HTML (.html, .htm)
  - PDF (.pdf) via pypdf
  - Microsoft Word (.docx) via docx
  - JSON (.json) structured documents
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DocumentSection:
    """Represents a structured section within a raw document."""
    title: str
    content: str
    page_number: Optional[int] = None
    section_level: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RawDocument:
    """Standardized extracted document container."""
    document_id: str
    title: str
    file_path: Path
    file_type: str
    full_text: str
    sections: List[DocumentSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""


@dataclass
class ExtractionFailure:
    """Record of a failed document extraction."""
    file_path: Path
    file_type: str
    error_message: str
    exception_type: str


class DocumentLoader:
    """
    Extensible document loader supporting Markdown, TXT, HTML, PDF, DOCX, and JSON.
    """

    SUPPORTED_EXTENSIONS = {
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "text",
        ".html": "html",
        ".htm": "html",
        ".pdf": "pdf",
        ".docx": "docx",
        ".json": "json",
    }

    def __init__(self):
        self.failures: List[ExtractionFailure] = []

    def compute_deterministic_id(self, path: Path, content: bytes) -> str:
        """Generates a stable deterministic document ID based on relative path and content hash."""
        hasher = hashlib.sha256()
        hasher.update(path.as_posix().lower().encode("utf-8"))
        hasher.update(content)
        return f"doc_{hasher.hexdigest()[:16]}"

    def load_file(self, path: Path) -> Optional[RawDocument]:
        """Loads a single file into a RawDocument or records an extraction failure."""
        if not path.is_file():
            self.failures.append(
                ExtractionFailure(
                    file_path=path,
                    file_type="unknown",
                    error_message=f"File not found: {path}",
                    exception_type="FileNotFoundError",
                )
            )
            return None

        ext = path.suffix.lower()
        file_type = self.SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            self.failures.append(
                ExtractionFailure(
                    file_path=path,
                    file_type=ext,
                    error_message=f"Unsupported file format: {ext}",
                    exception_type="UnsupportedFormatError",
                )
            )
            return None

        try:
            raw_bytes = path.read_bytes()
            content_hash = hashlib.sha256(raw_bytes).hexdigest()
            doc_id = self.compute_deterministic_id(path, raw_bytes)

            if file_type == "markdown":
                return self._load_markdown(path, raw_bytes, doc_id, content_hash)
            elif file_type == "text":
                return self._load_text(path, raw_bytes, doc_id, content_hash)
            elif file_type == "html":
                return self._load_html(path, raw_bytes, doc_id, content_hash)
            elif file_type == "pdf":
                return self._load_pdf(path, raw_bytes, doc_id, content_hash)
            elif file_type == "docx":
                return self._load_docx(path, raw_bytes, doc_id, content_hash)
            elif file_type == "json":
                return self._load_json(path, raw_bytes, doc_id, content_hash)
            else:
                raise ValueError(f"Unhandled file type: {file_type}")

        except Exception as exc:
            logger.error("Failed to extract document from %s: %s", path, exc, exc_info=True)
            self.failures.append(
                ExtractionFailure(
                    file_path=path,
                    file_type=file_type,
                    error_message=str(exc),
                    exception_type=type(exc).__name__,
                )
            )
            return None

    def load_directory(self, directory: Path, recursive: bool = True) -> List[RawDocument]:
        """Loads all supported files from a directory."""
        docs: List[RawDocument] = []
        if not directory.exists() or not directory.is_dir():
            logger.warning("Directory does not exist: %s", directory)
            return docs

        pattern = "**/*" if recursive else "*"
        for path in sorted(directory.glob(pattern)):
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                doc = self.load_file(path)
                if doc:
                    docs.append(doc)

        return docs

    # ── FORMAT-SPECIFIC LOADERS ──────────────────────────────────────────────

    def _load_text(self, path: Path, raw_bytes: bytes, doc_id: str, content_hash: str) -> RawDocument:
        text = raw_bytes.decode("utf-8", errors="replace")
        title = path.stem.replace("_", " ").title()
        section = DocumentSection(title=title, content=text, section_level=1)
        return RawDocument(
            document_id=doc_id,
            title=title,
            file_path=path,
            file_type="text",
            full_text=text,
            sections=[section],
            content_hash=content_hash,
            metadata={"filename": path.name},
        )

    def _load_markdown(self, path: Path, raw_bytes: bytes, doc_id: str, content_hash: str) -> RawDocument:
        text = raw_bytes.decode("utf-8", errors="replace")
        lines = text.splitlines()

        title = path.stem.replace("_", " ").title()
        sections: List[DocumentSection] = []
        current_title = title
        current_level = 1
        current_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                # Header line
                if current_lines:
                    sections.append(
                        DocumentSection(
                            title=current_title,
                            content="\n".join(current_lines).strip(),
                            section_level=current_level,
                        )
                    )
                    current_lines = []
                # Determine header level and text
                level = len(stripped) - len(stripped.lstrip("#"))
                header_text = stripped.lstrip("#").strip()
                if level == 1 and not title:
                    title = header_text
                current_title = header_text
                current_level = level
            else:
                current_lines.append(line)

        if current_lines:
            sections.append(
                DocumentSection(
                    title=current_title,
                    content="\n".join(current_lines).strip(),
                    section_level=current_level,
                )
            )

        return RawDocument(
            document_id=doc_id,
            title=title,
            file_path=path,
            file_type="markdown",
            full_text=text,
            sections=sections if sections else [DocumentSection(title=title, content=text)],
            content_hash=content_hash,
            metadata={"filename": path.name},
        )

    def _load_html(self, path: Path, raw_bytes: bytes, doc_id: str, content_hash: str) -> RawDocument:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError("beautifulsoup4 is required for HTML loading.")

        html_str = raw_bytes.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_str, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else path.stem.replace("_", " ").title()

        # Remove scripts and style
        for tag in soup(["script", "style", "noscript", "meta", "header", "footer"]):
            tag.decompose()

        # Extract sections by headers
        sections: List[DocumentSection] = []
        full_text_parts: List[str] = []

        headers = soup.find_all(["h1", "h2", "h3", "h4", "p", "table", "pre", "code"])
        current_title = title
        current_level = 1
        current_section_text: List[str] = []

        for elem in headers:
            text = elem.get_text(separator=" ", strip=True)
            if not text:
                continue

            if elem.name in ["h1", "h2", "h3", "h4"]:
                if current_section_text:
                    sections.append(
                        DocumentSection(
                            title=current_title,
                            content="\n".join(current_section_text),
                            section_level=current_level,
                        )
                    )
                    current_section_text = []
                current_title = text
                current_level = int(elem.name[1])
            else:
                current_section_text.append(text)
                full_text_parts.append(text)

        if current_section_text:
            sections.append(
                DocumentSection(
                    title=current_title,
                    content="\n".join(current_section_text),
                    section_level=current_level,
                )
            )

        full_text = "\n".join(full_text_parts) if full_text_parts else soup.get_text(separator="\n", strip=True)

        return RawDocument(
            document_id=doc_id,
            title=title,
            file_path=path,
            file_type="html",
            full_text=full_text,
            sections=sections if sections else [DocumentSection(title=title, content=full_text)],
            content_hash=content_hash,
            metadata={"filename": path.name},
        )

    def _load_pdf(self, path: Path, raw_bytes: bytes, doc_id: str, content_hash: str) -> RawDocument:
        try:
            import io
            import pypdf
        except ImportError:
            raise ImportError("pypdf is required for PDF loading.")

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        sections: List[DocumentSection] = []
        full_text_parts: List[str] = []

        title = path.stem.replace("_", " ").title()
        if reader.metadata and reader.metadata.title:
            title = reader.metadata.title

        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                full_text_parts.append(page_text)
                sections.append(
                    DocumentSection(
                        title=f"{title} - Page {page_idx + 1}",
                        content=page_text.strip(),
                        page_number=page_idx + 1,
                        section_level=1,
                    )
                )

        full_text = "\n\n".join(full_text_parts)
        return RawDocument(
            document_id=doc_id,
            title=title,
            file_path=path,
            file_type="pdf",
            full_text=full_text,
            sections=sections,
            content_hash=content_hash,
            metadata={"filename": path.name, "page_count": len(reader.pages)},
        )

    def _load_docx(self, path: Path, raw_bytes: bytes, doc_id: str, content_hash: str) -> RawDocument:
        try:
            import io
            import docx
        except ImportError:
            raise ImportError("python-docx is required for DOCX loading.")

        doc = docx.Document(io.BytesIO(raw_bytes))
        sections: List[DocumentSection] = []
        full_text_parts: List[str] = []

        title = path.stem.replace("_", " ").title()
        current_title = title
        current_level = 1
        current_lines: List[str] = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            full_text_parts.append(text)

            if p.style and p.style.name.startswith("Heading"):
                if current_lines:
                    sections.append(
                        DocumentSection(
                            title=current_title,
                            content="\n".join(current_lines),
                            section_level=current_level,
                        )
                    )
                    current_lines = []
                current_title = text
                try:
                    current_level = int(p.style.name.replace("Heading", "").strip())
                except ValueError:
                    current_level = 1
            else:
                current_lines.append(text)

        # Include tables
        for table in doc.tables:
            table_rows = []
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells)
                table_rows.append(row_text)
            if table_rows:
                table_content = "\n".join(table_rows)
                full_text_parts.append(table_content)
                current_lines.append(table_content)

        if current_lines:
            sections.append(
                DocumentSection(
                    title=current_title,
                    content="\n".join(current_lines),
                    section_level=current_level,
                )
            )

        full_text = "\n\n".join(full_text_parts)
        return RawDocument(
            document_id=doc_id,
            title=title,
            file_path=path,
            file_type="docx",
            full_text=full_text,
            sections=sections,
            content_hash=content_hash,
            metadata={"filename": path.name},
        )

    def _load_json(self, path: Path, raw_bytes: bytes, doc_id: str, content_hash: str) -> RawDocument:
        data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        title = data.get("title", path.stem.replace("_", " ").title())
        content = data.get("content") or data.get("body") or data.get("text") or ""

        sections: List[DocumentSection] = []
        if "sections" in data and isinstance(data["sections"], list):
            for s in data["sections"]:
                sections.append(
                    DocumentSection(
                        title=s.get("title", title),
                        content=s.get("content", ""),
                        page_number=s.get("page"),
                        section_level=s.get("level", 1),
                        metadata=s.get("metadata", {}),
                    )
                )

        if not content and sections:
            content = "\n\n".join(f"## {s.title}\n{s.content}" for s in sections)
        elif not content:
            content = json.dumps(data, indent=2)

        if not sections:
            sections = [DocumentSection(title=title, content=content)]

        return RawDocument(
            document_id=doc_id,
            title=title,
            file_path=path,
            file_type="json",
            full_text=content,
            sections=sections,
            content_hash=content_hash,
            metadata={"filename": path.name, **data.get("metadata", {})},
        )


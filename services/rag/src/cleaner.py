"""
cleaner.py — Document Normalization, Sanitization, and Secret Detection.

Cleans extracted text while strictly preserving:
  - Technical protocol symbols and state machines (e.g. %ROUTING-BGP-5-ADJCHANGE)
  - Network interface designations (e.g. HundredGigE0/0/0/1, eth1, br0)
  - IPv4/IPv6 CIDR addresses
  - Configuration snippets and CLI command text
Redacts:
  - Hardcoded passwords, API keys, tokens, and private keys
"""

from __future__ import annotations

import re
from typing import List, Tuple
from .loaders import RawDocument, DocumentSection


class DocumentCleaner:
    """Normalizes document text and redacts sensitive credentials."""

    # Regex patterns for secret detection
    SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
        ("API_KEY", re.compile(r"(?i)\b(?:api[_-]?key|apikey|secret[_-]?key)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?")),
        ("BEARER_TOKEN", re.compile(r"(?i)\b(?:bearer\s+[a-zA-Z0-9_\-\.]{25,})")),
        ("PASSWORD", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{6,})['\"]?")),
        ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC )?PRIVATE KEY-----")),
        ("GENERIC_TOKEN", re.compile(r"\b(?:ghp_[a-zA-Z0-9]{36}|glpat-[a-zA-Z0-9_\-]{20,}|xox[baprs]-[0-9a-zA-Z]{10,})")),
    ]

    # Regex to clean weird unicode artifacts while keeping network punctuation
    UNICODE_REPLACEMENTS = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
        "\u2026": "...",
        "\xa0": " ",  # non-breaking space
    }

    def __init__(self, redact_secrets: bool = True):
        self.redact_secrets = redact_secrets

    def clean_text(self, text: str) -> str:
        """Cleans and sanitizes raw text string."""
        if not text:
            return ""

        # Replace non-standard unicode quotes / dashes
        for char, repl in self.UNICODE_REPLACEMENTS.items():
            text = text.replace(char, repl)

        # Remove null bytes and carriage returns
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")

        # Normalize multiple blank lines (3+ down to 2)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Normalize trailing horizontal whitespace per line
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)

        # Redact secrets if enabled
        if self.redact_secrets:
            text = self.sanitize_secrets(text)

        return text.strip()

    def sanitize_secrets(self, text: str) -> str:
        """Replaces detected secrets with safe placeholder."""
        sanitized = text
        for secret_type, pattern in self.SECRET_PATTERNS:
            def replacer(match: re.Match) -> str:
                # Keep keyword prefix, replace sensitive payload
                full_match = match.group(0)
                if match.groups():
                    val = match.group(1)
                    return full_match.replace(val, f"[REDACTED_{secret_type}]")
                return f"[REDACTED_{secret_type}]"

            sanitized = pattern.sub(replacer, sanitized)
        return sanitized

    def clean_document(self, doc: RawDocument) -> RawDocument:
        """Cleans all sections and full text of a RawDocument."""
        cleaned_sections: List[DocumentSection] = []
        for s in doc.sections:
            cleaned_content = self.clean_text(s.content)
            if cleaned_content:
                cleaned_sections.append(
                    DocumentSection(
                        title=self.clean_text(s.title),
                        content=cleaned_content,
                        page_number=s.page_number,
                        section_level=s.section_level,
                        metadata=s.metadata,
                    )
                )

        cleaned_full_text = self.clean_text(doc.full_text)
        doc.full_text = cleaned_full_text
        doc.sections = cleaned_sections
        doc.title = self.clean_text(doc.title)
        return doc


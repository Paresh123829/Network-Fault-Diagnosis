"""
metadata.py — Document & Chunk Metadata Extraction and Enrichment.

Derives protocol, vendor, platform, fault category, and licensing attributes
from actual document content and structured manifest entries.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .chunker import DocumentChunk
from .loaders import RawDocument


class ChunkMetadata(BaseModel):
    """Enriched metadata payload for each indexed vector point in Qdrant."""
    document_id: str
    chunk_id: str
    document_title: str
    source_url: str = ""
    source_path: str = ""
    publisher: str = "Unknown"
    protocol: str = "general"
    vendor: str = "general"
    platform: str = "any"
    software_version: str = "general"
    fault_category: str = "general"
    section: str = ""
    subsection: str = ""
    page_number: Optional[int] = None
    document_type: str = "guide"
    source_license: str = "Informational"
    publication_date: str = ""
    content_hash: str = ""
    token_count_approx: int = 0


class MetadataExtractor:
    """Extracts and enriches metadata for RawDocuments and DocumentChunks."""

    PROTOCOL_KEYWORDS = {
        "bgp": ["bgp", "border gateway protocol", "fsm", "keepalive", "as-path", "route-reflector", "adjchange"],
        "ospf": ["ospf", "open shortest path first", "lsa", "lsdb", "area 0", "exstart", "hello/dead"],
        "bfd": ["bfd", "bidirectional forwarding detection", "control packet", "multiplier", "echo function"],
        "fib": ["fib", "forwarding information base", "hardware drop", "rib", "forwarding table", "prefix route"],
        "optics": ["transceiver", "optic", "sfp", "qsfp", "dbm", "rx power", "tx power", "laser", "carrier transition"],
        "physical_interface": ["interface flap", "carrier transition", "crc error", "fcs error", "admin shutdown", "line protocol"],
        "vlan": ["vlan", "802.1q", "trunk", "access port", "native vlan", "spanning tree", "stp", "bridge"],
        "telemetry": ["yang", "telemetry", "model-driven telemetry", "mdt", "sensor path", "subscription", "encoding-path"],
    }

    FAULT_CATEGORY_PATTERNS = {
        "BGP_NEIGHBOR_DOWN": [r"bgp.*(?:down|reset|idle|active|notification|cease|teardown)", r"%routing-bgp-5-adjchange"],
        "PHYSICAL_LINK_DOWN": [r"(?:link|interface).*(?:down|failed|flapping|carrier)", r"%link-3-updown"],
        "TRANSCEIVER_FAULT": [r"(?:transceiver|optic|sfp|qsfp).*(?:pull|removed|degradation|alarm|low power)"],
        "PORT_ADMIN_SHUTDOWN": [r"(?:admin(?:istratively)?\s+down|shutdown|disabled by admin)"],
        "OSPF_ADJACENCY_FAILURE": [r"ospf.*(?:down|exstart|deadlock|mismatch|adjacency)"],
        "BFD_SESSION_FAILURE": [r"bfd.*(?:down|timeout|expired|failure)"],
        "FIB_DROP": [r"(?:fib.*drop|hardware drop|packet-drops|blackhole)"],
        "VLAN_MISMATCH": [r"(?:vlan mismatch|pvid mismatch|untagged frame drop|802\.1q drop)"],
    }

    VENDOR_PLATFORM_KEYWORDS = {
        ("Cisco", "IOS-XR"): ["cisco", "ios-xr", "ios xr", "xr", "rp0", "lc0", "hundredgige"],
        ("FRRouting", "FRR"): ["frr", "frrouting", "vtysh", "zebra", "bgpd", "ospfd"],
        ("Linux", "Linux Kernel"): ["linux bridge", "ip link", "sysctl", "netlink", "ip route", "nftables"],
        ("IETF", "Standards Track"): ["rfc", "internet engineering task force", "ietf", "standards track"],
    }

    def enrich_chunk(self, chunk: DocumentChunk, doc: RawDocument) -> ChunkMetadata:
        """Derives full ChunkMetadata from document metadata and chunk content."""
        doc_meta = doc.metadata or {}
        text_lower = chunk.content.lower()

        # 1. Detect Protocol
        protocol = doc_meta.get("protocol")
        if not protocol:
            detected_proto = "general"
            max_matches = 0
            for proto_name, kw_list in self.PROTOCOL_KEYWORDS.items():
                matches = sum(1 for kw in kw_list if kw in text_lower)
                if matches > max_matches:
                    max_matches = matches
                    detected_proto = proto_name
            protocol = detected_proto

        # 2. Detect Fault Category
        fault_category = doc_meta.get("fault_category")
        if not fault_category:
            detected_fc = "general"
            for fc_name, patterns in self.FAULT_CATEGORY_PATTERNS.items():
                if any(re.search(pat, text_lower) for pat in patterns):
                    detected_fc = fc_name
                    break
            fault_category = detected_fc

        # 3. Detect Vendor & Platform
        vendor = doc_meta.get("vendor")
        platform = doc_meta.get("platform")
        if not vendor or not platform:
            for (v_cand, p_cand), kws in self.VENDOR_PLATFORM_KEYWORDS.items():
                if any(kw in text_lower for kw in kws):
                    vendor = vendor or v_cand
                    platform = platform or p_cand
                    break

        vendor = vendor or "Generic Networking"
        platform = platform or "Any"

        return ChunkMetadata(
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            document_title=chunk.document_title,
            source_url=doc_meta.get("source_url", ""),
            source_path=str(doc.file_path.as_posix()),
            publisher=doc_meta.get("publisher", vendor),
            protocol=protocol,
            vendor=vendor,
            platform=platform,
            software_version=doc_meta.get("software_version", "general"),
            fault_category=fault_category,
            section=chunk.section_title,
            subsection=doc_meta.get("subsection", ""),
            page_number=chunk.page_number,
            document_type=doc_meta.get("document_type", "troubleshooting_sop"),
            source_license=doc_meta.get("source_license", "Informational"),
            publication_date=doc_meta.get("publication_date", "2024-01-01"),
            content_hash=chunk.content_hash,
            token_count_approx=chunk.token_count_approx,
        )


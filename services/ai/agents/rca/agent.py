"""
agent.py — Executable Root Cause Analysis (RCA) Agent.

Weighs candidate hypotheses against extracted symptoms and topology context,
penalizes contradictory evidence, calibrates confidence, and produces canonical DiagnosisResult.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.ai.schemas.contracts import (
    IncidentTimeline,
    DiagnosisResult,
    Hypothesis,
    TopologyContext,
)
from services.ai.agents.symptom.models import SymptomAnalysisReport
from .hypotheses import RCAHypothesisEngine

logger = logging.getLogger(__name__)


class RCAgent:
    """
    Executable Root Cause Analysis Agent.
    """

    def __init__(self):
        self.engine = RCAHypothesisEngine()

    def diagnose(
        self,
        timeline: IncidentTimeline,
        symptom_report: SymptomAnalysisReport,
        topology_context: Optional[TopologyContext] = None,
        retrieved_evidence: Optional[Any] = None,
    ) -> DiagnosisResult:
        logger.info(f"RCAgent diagnosing incident {timeline.incident_id}...")

        # 1. Evaluate candidate hypotheses
        hypotheses = self.engine.evaluate_all(timeline, symptom_report, topology_context)

        # 2. If no strong hypothesis generated, create a conservative fallback hypothesis
        if not hypotheses:
            primary_dev = timeline.affected_devices[0] if timeline.affected_devices else "unknown"
            primary_intf = timeline.affected_interfaces[0] if timeline.affected_interfaces else ""
            default_cat = "anomaly"
            if "bgp" in timeline.suspected_protocols:
                default_cat = "bgp_clear"
            elif "interface" in timeline.suspected_protocols:
                default_cat = "link_down"

            fallback = Hypothesis(
                hypothesis_id=f"hyp_fallback_{timeline.incident_id}",
                root_cause_category=default_cat,
                description=f"Network anomaly observed on {primary_dev}:{primary_intf}",
                supporting_evidence_ids=[e.event_id for e in timeline.events[:2]],
                confidence=0.50,
                supporting_evidence=[f"Timeline correlation reason: {timeline.correlation_reason}"],
                contradictory_evidence=[],
                affected_devices=timeline.affected_devices,
                affected_interfaces=timeline.affected_interfaces,
                explanation=f"Correlated events indicate abnormal state on {primary_dev}.",
                missing_evidence=["Detailed device debug diagnostics missing."]
            )
            hypotheses.append(fallback)

        # 3. Select top hypothesis
        top_hyp = hypotheses[0]
        probable_cause = top_hyp.description
        overall_confidence = top_hyp.confidence

        # 4. Gather evidence IDs and integrate retrieved knowledge citations
        all_evidence_ids = []
        for h in hypotheses:
            all_evidence_ids.extend(h.supporting_evidence_ids)

        # Incorporate retrieved RAG passage IDs into evidence_ids without altering telemetry facts
        rag_citations = []
        if retrieved_evidence and getattr(retrieved_evidence, "passages", None):
            for passage in retrieved_evidence.passages:
                all_evidence_ids.append(passage.passage_id)
                doc_title = passage.metadata.get("document_title", "Knowledge Base")
                rag_citations.append(f"Retrieved SOP [{doc_title}]: {passage.text[:120].strip()}...")

            if rag_citations and top_hyp:
                top_hyp.supporting_evidence.extend(rag_citations[:2])

        all_evidence_ids = sorted(list(set(all_evidence_ids)))

        # 5. Affected components
        affected_comps = sorted(list(set(
            timeline.affected_devices +
            timeline.affected_interfaces +
            top_hyp.affected_devices +
            top_hyp.affected_interfaces
        )))
        affected_comps = [c for c in affected_comps if c]

        logger.info(f"RCAgent selected probable cause: '{probable_cause}' (conf={overall_confidence:.2f})")

        provenance = {
            "agent": "RCAgent",
            "incident_id": timeline.incident_id,
            "hypotheses_evaluated_count": len(hypotheses)
        }
        if retrieved_evidence and getattr(retrieved_evidence, "passages", None):
            provenance["retrieved_passages_count"] = len(retrieved_evidence.passages)
            provenance["retrieved_source_ids"] = retrieved_evidence.source_ids

        return DiagnosisResult(
            hypotheses=hypotheses,
            probable_root_cause=probable_cause,
            evidence_ids=all_evidence_ids,
            confidence=overall_confidence,
            affected_components=affected_comps,
            symptom_summary={
                "symptoms_count": len(symptom_report.symptoms),
                "primary_category": symptom_report.primary_symptom.category.value if symptom_report.primary_symptom else "none",
                "missing_evidence_count": len(symptom_report.missing_evidence)
            },
            topology_summary={
                "nodes_in_context": len(topology_context.nodes) if topology_context else 0,
                "links_in_context": len(topology_context.links) if topology_context else 0
            },
            provenance=provenance
        )


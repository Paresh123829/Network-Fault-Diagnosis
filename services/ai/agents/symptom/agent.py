"""
agent.py — Executable Symptom Contextualization Agent.

Processes IncidentTimeline into structured, sequenced, evidence-backed SymptomAnalysisReport.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.ai.schemas.contracts import IncidentTimeline, TopologyContext
from .models import SymptomAnalysisReport
from .analyzer import SymptomAnalyzer

logger = logging.getLogger(__name__)


class SymptomAgent:
    """
    Executable Symptom Contextualization Agent.
    """

    def __init__(self):
        self.analyzer = SymptomAnalyzer()

    def process(
        self,
        timeline: IncidentTimeline,
        topology_context: Optional[TopologyContext] = None
    ) -> SymptomAnalysisReport:
        logger.info(f"SymptomAgent processing incident {timeline.incident_id} with {len(timeline.events)} events.")
        report = self.analyzer.analyze(timeline, topology_context)
        logger.info(
            f"SymptomAgent completed: {len(report.symptoms)} symptoms found. Primary: "
            f"{report.primary_symptom.category.value if report.primary_symptom else 'None'}"
        )
        return report


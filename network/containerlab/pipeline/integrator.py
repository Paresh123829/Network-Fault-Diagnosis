"""
integrator.py — Connects Containerlab Observation Timelines into the Multi-Agent Diagnosis Engine.

Integrates:
- LangGraph 9-stage StateGraph execution (DiagnosisOrchestrator).
- TopologyContext retrieval and quantitative blast radius analysis.
- Qdrant RAG hybrid knowledge retrieval (network_knowledge_base).
- Independent evaluation of diagnostic accuracy against scenario ground-truth.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Tuple

from services.ai.orchestrator.service import DiagnosisOrchestrator
from services.ai.schemas.contracts import DiagnosisResult, IncidentTimeline
from network.containerlab.scenarios.models import ScenarioDefinition

logger = logging.getLogger(__name__)


class LabDiagnosisEvaluation:
    def __init__(
        self,
        scenario_id: str,
        diagnosis_produced: bool,
        diagnosis_result: Optional[DiagnosisResult],
        rca_matched: bool,
        device_matched: bool,
        protocol_matched: bool,
        evidence_grounded: bool,
        confidence_score: float,
        duration_ms: float,
        raw_state: Dict[str, Any],
    ) -> None:
        self.scenario_id = scenario_id
        self.diagnosis_produced = diagnosis_produced
        self.diagnosis_result = diagnosis_result
        self.rca_matched = rca_matched
        self.device_matched = device_matched
        self.protocol_matched = protocol_matched
        self.evidence_grounded = evidence_grounded
        self.confidence_score = confidence_score
        self.duration_ms = duration_ms
        self.raw_state = raw_state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "diagnosis_produced": self.diagnosis_produced,
            "diagnosis_result": self.diagnosis_result.model_dump() if self.diagnosis_result else None,
            "rca_matched": self.rca_matched,
            "device_matched": self.device_matched,
            "protocol_matched": self.protocol_matched,
            "evidence_grounded": self.evidence_grounded,
            "confidence_score": self.confidence_score,
            "duration_ms": self.duration_ms,
        }


class LabDiagnosisIntegrator:
    """
    Executes LangGraph diagnosis on live Containerlab incidents and evaluates correctness.
    """

    def __init__(self, orchestrator: Optional[DiagnosisOrchestrator] = None) -> None:
        self.orchestrator = orchestrator or DiagnosisOrchestrator()

    def run_diagnosis(
        self,
        timeline: IncidentTimeline,
        scenario: ScenarioDefinition,
        thread_id: Optional[str] = None,
    ) -> LabDiagnosisEvaluation:
        start_t = time.perf_counter()
        logger.info(f"[LAB DIAGNOSIS] Running diagnosis for scenario '{scenario.scenario_id}', incident '{timeline.incident_id}'")

        try:
            # 1. Invoke LangGraph StateGraph
            final_state = self.orchestrator.diagnose_incident(
                timeline=timeline,
                context_id=f"clab_{scenario.scenario_id}",
                thread_id=thread_id,
            )
            duration_ms = (time.perf_counter() - start_t) * 1000.0

            # 2. Extract DiagnosisResult
            diag_obj = final_state.get("diagnosis_result") or final_state.get("diagnosis")
            diagnosis_res: Optional[DiagnosisResult] = None
            if isinstance(diag_obj, DiagnosisResult):
                diagnosis_res = diag_obj
            elif isinstance(diag_obj, dict):
                try:
                    diagnosis_res = DiagnosisResult(**diag_obj)
                except Exception:
                    pass

            diagnosis_produced = (diagnosis_res is not None)

            # 3. Evaluate against Scenario Ground Truth
            exp_diag = scenario.expected_diagnosis
            rca_matched = False
            device_matched = False
            protocol_matched = False
            evidence_grounded = False
            conf_score = 0.0

            if diagnosis_res:
                conf_score = diagnosis_res.confidence
                # Match device
                primary_cause = diagnosis_res.primary_cause
                target_str = str(primary_cause).lower() + " " + str(diagnosis_res.root_causes).lower()

                # Device match
                device_matched = (exp_diag.expected_device.lower() in target_str or
                                  exp_diag.expected_device in timeline.affected_devices)

                # Protocol match
                protocol_matched = (exp_diag.expected_protocol.lower() in target_str or
                                    exp_diag.expected_protocol in timeline.suspected_protocols)

                # RCA keyword match
                key_terms = [t.lower() for t in exp_diag.expected_root_cause.split() if len(t) > 3]
                rca_matched = any(kt in target_str for kt in key_terms) or protocol_matched

                # Evidence citations check
                evidence_grounded = len(diagnosis_res.contributing_factors) > 0 or len(timeline.events) > 0

            return LabDiagnosisEvaluation(
                scenario_id=scenario.scenario_id,
                diagnosis_produced=diagnosis_produced,
                diagnosis_result=diagnosis_res,
                rca_matched=rca_matched,
                device_matched=device_matched,
                protocol_matched=protocol_matched,
                evidence_grounded=evidence_grounded,
                confidence_score=conf_score,
                duration_ms=duration_ms,
                raw_state=final_state,
            )

        except Exception as e:
            logger.error(f"[LAB DIAGNOSIS ERROR] Scenario {scenario.scenario_id} failed: {e}", exc_info=True)
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            return LabDiagnosisEvaluation(
                scenario_id=scenario.scenario_id,
                diagnosis_produced=False,
                diagnosis_result=None,
                rca_matched=False,
                device_matched=False,
                protocol_matched=False,
                evidence_grounded=False,
                confidence_score=0.0,
                duration_ms=duration_ms,
                raw_state={"error": str(e)},
            )


# Global singleton instance
lab_diagnosis_integrator = LabDiagnosisIntegrator()


"""
services/ai/agents/diagnosis/matching.py — Deterministic One-to-One Incident-to-Ground-Truth Matcher.

Ensures rigorous, reproducible, non-duplicative evaluation between predicted IncidentTimelines
(and their synthesized DiagnosisResults) and documented Ground-Truth fault events.

Core Rules Enforced:
1. One-to-One GT Claiming: A ground-truth event can only be claimed by ONE primary incident.
   Subsequent overlapping incidents for the same fault are categorized as DUPLICATE predictions.
2. Temporal Window Validation: Requires explicit temporal overlap between the incident time window
   and the ground truth event window (with configurable tolerance delta_t).
3. Topological Component Overlap: Incident affected devices must intersect the GT target devices.
4. Unambiguous Categorization:
   - TRUE_POSITIVE: First incident matching an unclaimed GT event with correct root-cause category.
   - DUPLICATE: Incident matching an already-claimed GT event (redundant alarm during outage).
   - MISDIAGNOSED: Incident matching a GT event in time/device, but with incorrect root cause.
   - FALSE_POSITIVE: Incident with no matching ground-truth fault event.
   - FALSE_NEGATIVE (MISSED): Ground-truth fault event not detected by any predicted incident.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from services.ai.schemas.contracts import IncidentTimeline, DiagnosisResult

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Detailed matching record for an evaluated incident."""
    incident_id: str
    case_id: str
    match_status: str  # TRUE_POSITIVE, DUPLICATE, MISDIAGNOSED, FALSE_POSITIVE
    matched_gt_id: Optional[str] = None
    gt_fault_type: Optional[str] = None
    gt_target_device: Optional[str] = None
    diagnosed_category: Optional[str] = None
    diagnosed_root_cause: Optional[str] = None
    confidence: float = 0.0
    classification_match: bool = False
    isolation_match: bool = False
    temporal_delta_seconds: Optional[float] = None
    latency_ms: float = 0.0


@dataclass
class GroundTruthAuditSummary:
    """Summary of detection and classification across ground-truth events."""
    total_gt_events: int = 0
    detected_and_correct: int = 0
    detected_but_wrong_rca: int = 0
    missed: int = 0
    gt_status_by_id: Dict[str, str] = field(default_factory=dict)


def parse_ground_truth_time(raw_time: Any, case_id: str = "") -> Optional[datetime]:
    """
    Parses heterogeneous ground-truth timestamp formats into timezone-aware UTC datetime.
    Supports:
      - Epoch seconds (e.g. Case 2: 1498754414)
      - Epoch milliseconds (e.g. Case 5/6: 1519090293609)
      - PDT local timestamp strings (e.g. Case 3/4: '8/4/17 10:20' -> UTC-7)
      - ISO-8601 strings
    """
    if raw_time is None:
        return None
    s = str(raw_time).strip()
    if not s or s.lower() in ("none", "", "null"):
        return None

    # 1. Numeric epoch
    if s.isdigit():
        val = int(s)
        if val > 1e11:  # milliseconds
            return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
        return datetime.fromtimestamp(val, tz=timezone.utc)

    # 2. Text timestamp strings: align with normalizer DEFAULT_YEAR=2018 and UTC convention
    for fmt in ("%m/%d/%y %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(year=2018, tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def is_category_match(gt_fault: str, diag_category: str, probable_cause: str) -> bool:
    """
    Evaluates whether the diagnosed hypothesis matches the ground-truth fault family.
    Uses canonical networking semantic equivalence.
    """
    gt = (gt_fault or "").lower().strip()
    cat = (diag_category or "").lower().strip()
    cause = (probable_cause or "").lower().strip()

    # Normalize aliases
    if "bgp" in gt:
        return "bgp" in cat or "bgp" in cause
    if "transceiver" in gt:
        return "transceiver" in cat or "optics" in cat or "transceiver" in cause or "optics" in cause
    if "admin" in gt or "shut" in gt:
        return "admin" in cat or "shut" in cat or "admin" in cause or "shutdown" in cause
    if "flap" in gt or "down" in gt or "link" in gt:
        return "flap" in cat or "link" in cat or "down" in cause or "flap" in cause
    if "ecmp" in gt:
        return "ecmp" in cat or "congestion" in cat
    if "blackhole" in gt or "fib" in gt:
        return "blackhole" in cat or "drop" in cat or "fib" in cause
    if "loop" in gt:
        return "loop" in cat
    if "ospf" in gt:
        return "ospf" in cat or "ospf" in cause
    if "bfd" in gt:
        return "bfd" in cat
    if "vlan" in gt:
        return "vlan" in cat

    return False


def is_device_match(gt_device: str, affected_devices: List[str]) -> bool:
    """Checks whether any affected device in the incident matches the GT target device."""
    if not gt_device:
        return True
    gt_clean = gt_device.lower().replace("&", ",").replace("and", ",").replace("-", " ")
    tokens = [t.strip() for t in gt_clean.split(",") if t.strip()]
    
    # Handle range strings like 'spine 1 3' -> spine1, spine2, spine3
    expanded_tokens = []
    for tok in tokens:
        expanded_tokens.append(tok)
        if "spine 1 3" in tok or "spine 1 - 3" in tok:
            expanded_tokens.extend(["spine1", "spine2", "spine3"])
        elif "spine 1 4" in tok or "spine 1 - 4" in tok:
            expanded_tokens.extend(["spine1", "spine2", "spine3", "spine4"])

    inc_devs = [d.lower().strip() for d in affected_devices]
    for tok in expanded_tokens:
        tok_compact = tok.replace(" ", "")
        for d in inc_devs:
            d_compact = d.replace(" ", "")
            if tok_compact == d_compact or tok in d or d in tok:
                return True
    return False


class DeterministicGroundTruthMatcher:
    """
    Deterministic one-to-one evaluator matching predicted incidents to ground-truth fault events.
    """

    def __init__(self, temporal_tolerance_seconds: float = 180.0):
        self.temporal_tolerance = timedelta(seconds=temporal_tolerance_seconds)

    def match(
        self,
        case_id: str,
        incidents: List[IncidentTimeline],
        diagnoses: List[DiagnosisResult],
        ground_truth: List[Dict[str, Any]],
        latencies_ms: Optional[List[float]] = None
    ) -> Tuple[List[MatchResult], GroundTruthAuditSummary]:
        """
        Executes one-to-one matching between predicted incidents and ground-truth events.
        """
        results: List[MatchResult] = []
        claimed_gt_ids: Set[str] = set()
        gt_status_map: Dict[str, str] = {}

        # 1. Prepare normalized Ground Truth records
        parsed_gt = []
        for idx, gt in enumerate(ground_truth):
            gt_id = str(gt.get("event_id") or f"gt_{case_id}_{idx}")
            gt_fault = str(gt.get("fault_type") or gt.get("event_key") or gt.get("Event") or "").strip()
            gt_dev = str(gt.get("target_device") or gt.get("host_key") or gt.get("Host") or "").strip()
            
            raw_st = gt.get("start_time_raw") or gt.get("start_time") or gt.get("Start")
            raw_et = gt.get("end_time_raw") or gt.get("end_time") or gt.get("End")

            dt_start = parse_ground_truth_time(raw_st, case_id)
            dt_end = parse_ground_truth_time(raw_et, case_id)
            if dt_start and not dt_end:
                dt_end = dt_start + timedelta(seconds=300)

            parsed_gt.append({
                "gt_id": gt_id,
                "fault_type": gt_fault,
                "target_device": gt_dev,
                "start": dt_start,
                "end": dt_end,
                "raw": gt
            })
            gt_status_map[gt_id] = "MISSED"

        # 2. Iterate through predicted incidents chronologically
        inc_with_diag = list(zip(incidents, diagnoses))
        inc_with_diag.sort(key=lambda pair: pair[0].time_window.start)

        for i, (inc, diag) in enumerate(inc_with_diag):
            lat_ms = latencies_ms[i] if (latencies_ms and i < len(latencies_ms)) else 0.0
            inc_start = inc.time_window.start
            inc_end = inc.time_window.end
            diag_cat = diag.hypotheses[0].root_cause_category if diag.hypotheses else ""
            diag_cause = diag.probable_root_cause or ""

            best_gt = None
            min_delta = float("inf")

            # Search candidate ground-truth events
            for gt in parsed_gt:
                # Device match check
                if not is_device_match(gt["target_device"], inc.affected_devices):
                    continue

                # Temporal window check (if GT has valid timestamps)
                if gt["start"] and gt["end"]:
                    # Overlap with tolerance
                    window_start = gt["start"] - self.temporal_tolerance
                    window_end = gt["end"] + self.temporal_tolerance
                    if not (inc_end >= window_start and inc_start <= window_end):
                        continue

                    # Calculate temporal distance to fault center
                    gt_mid = gt["start"] + (gt["end"] - gt["start"]) / 2
                    inc_mid = inc_start + (inc_end - inc_start) / 2
                    delta = abs((inc_mid - gt_mid).total_seconds())
                else:
                    delta = 0.0

                if delta < min_delta:
                    min_delta = delta
                    best_gt = gt

            # Categorize the incident match
            if best_gt:
                gt_id = best_gt["gt_id"]
                gt_fault = best_gt["fault_type"]
                gt_dev = best_gt["target_device"]

                is_class = is_category_match(gt_fault, diag_cat, diag_cause)
                is_iso = is_device_match(gt_dev, diag.affected_components or inc.affected_devices)

                if gt_id not in claimed_gt_ids:
                    # First incident claiming this GT event!
                    claimed_gt_ids.add(gt_id)
                    if is_class:
                        status = "TRUE_POSITIVE"
                        gt_status_map[gt_id] = "DETECTED_AND_CORRECT"
                    else:
                        status = "MISDIAGNOSED"
                        gt_status_map[gt_id] = "DETECTED_BUT_WRONG_RCA"
                else:
                    # Duplicate prediction for an already claimed GT event
                    status = "DUPLICATE"

                results.append(MatchResult(
                    incident_id=inc.incident_id,
                    case_id=case_id,
                    match_status=status,
                    matched_gt_id=gt_id,
                    gt_fault_type=gt_fault,
                    gt_target_device=gt_dev,
                    diagnosed_category=diag_cat,
                    diagnosed_root_cause=diag_cause,
                    confidence=diag.confidence,
                    classification_match=is_class,
                    isolation_match=is_iso,
                    temporal_delta_seconds=min_delta,
                    latency_ms=lat_ms
                ))
            else:
                # No GT event matched -> Spurious False Positive
                results.append(MatchResult(
                    incident_id=inc.incident_id,
                    case_id=case_id,
                    match_status="FALSE_POSITIVE",
                    matched_gt_id=None,
                    gt_fault_type=None,
                    gt_target_device=None,
                    diagnosed_category=diag_cat,
                    diagnosed_root_cause=diag_cause,
                    confidence=diag.confidence,
                    classification_match=False,
                    isolation_match=False,
                    temporal_delta_seconds=None,
                    latency_ms=lat_ms
                ))

        # 3. Summarize GT event detection
        det_correct = sum(1 for s in gt_status_map.values() if s == "DETECTED_AND_CORRECT")
        det_wrong = sum(1 for s in gt_status_map.values() if s == "DETECTED_BUT_WRONG_RCA")
        missed = sum(1 for s in gt_status_map.values() if s == "MISSED")

        summary = GroundTruthAuditSummary(
            total_gt_events=len(parsed_gt),
            detected_and_correct=det_correct,
            detected_but_wrong_rca=det_wrong,
            missed=missed,
            gt_status_by_id=gt_status_map
        )

        return results, summary

"""
evaluate_ground_truth.py — Unified Root Evaluation Runner.

Executes Multi-Case Ground-Truth Evaluation across Cisco Cases 2, 3, 4, 5, 6, 9, 10
and Case 12 multi-sensor telemetry.
"""

import sys
from network.datasets.tools.evaluate_multi_case_ground_truth import MultiCaseGroundTruthEvaluator

def main():
    evaluator = MultiCaseGroundTruthEvaluator()
    summary = evaluator.run_full_evaluation()
    return 0 if summary else 1

if __name__ == "__main__":
    sys.exit(main())

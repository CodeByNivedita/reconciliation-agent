"""
Implements the 7 axes from ../../BENCHMARK_SPEC.md §4. Each function takes
one predicted Case and its matching ground_truth.csv row (as a dict) and
returns a bool or a small dict — never an aggregate; aggregation happens in
evaluator.py so these stay unit-testable in isolation.
"""

from backend.models import Case
from backend.rules_engine.action_policy import is_less_cautious


def category_correct(predicted: Case, gt_row: dict) -> bool:
    return predicted.category == gt_row["expected_category"]


def record_ids_correct(predicted: Case, gt_row: dict) -> bool:
    expected = set(filter(None, gt_row["expected_txn_ids"].split(";"))) if gt_row["expected_txn_ids"] else set()
    predicted_ids = set(predicted.matched_txn_ids())
    if gt_row["expected_category"] == "multiple_possible_matches":
        # Correct behavior here is reporting ALL plausible candidates while
        # abstaining, not narrowing to one — so "correct" means the true
        # settlement is among what was reported, not set-equality.
        return expected.issubset(predicted_ids)
    return predicted_ids == expected


def numeric_correct(predicted: Case, gt_row: dict, eps: float = 0.01) -> bool:
    expected_total = gt_row["expected_total_settled"]
    if expected_total in ("", None):
        return predicted.total_settled() == 0
    return abs(predicted.total_settled() - float(expected_total)) <= eps


def hallucinated(predicted: Case, valid_txn_ids: set[str]) -> bool:
    return any(tid not in valid_txn_ids for tid in predicted.matched_txn_ids())


def action_policy_miss(predicted: Case) -> bool:
    if predicted.action is None:
        return True
    return is_less_cautious(predicted.action, predicted.category)


def abstained_correctly(predicted: Case, gt_row: dict) -> bool | None:
    """Returns True/False only when the ground truth category IS
    multiple_possible_matches; None (not applicable) otherwise."""
    if gt_row["expected_category"] != "multiple_possible_matches":
        return None
    return predicted.action == "abstain"

"""
Runs the rules engine against the full 1,000-case ground_truth.csv. This is
a regression guard, not a benchmark report — see backend/evaluation/benchmark.py
for the human-readable version. The thresholds below reflect the known,
documented state (see BENCHMARK_SPEC.md / RULES_ENGINE_SPEC.md): remaining
misses are concentrated in orders whose reference typo happens to collide
with another real order's id, which needs cross-order arbitration the
current per-order engine doesn't attempt.
"""

from backend.evaluation.evaluator import evaluate


def test_overall_category_accuracy_floor():
    result = evaluate()
    assert result["category_accuracy"] >= 0.97


def test_zero_hallucination():
    result = evaluate()
    assert result["hallucination_rate"] == 0.0


def test_zero_action_policy_misses():
    result = evaluate()
    assert result["action_policy_miss_rate"] == 0.0


def test_easy_categories_are_perfect():
    result = evaluate()
    for cat in ["exact_match", "date_issue", "duplicate_record",
                "missing_record", "multiple_possible_matches", "partial_settlement"]:
        assert result["per_category_accuracy"][cat] == 1.0, cat


def test_consistent_across_splits():
    """No split should be wildly out of line with the others — a big gap
    would suggest overfitting or a split-construction bug, not just noise."""
    scores = [evaluate(s)["category_accuracy"] for s in ("dev", "validation", "test_holdout")]
    assert max(scores) - min(scores) < 0.03

import csv
from collections import Counter, defaultdict
from pathlib import Path

from backend.models import Case
from backend.rules_engine.engine import run_reconciliation
from backend.tools.order_tools import load_orders
from backend.tools.settlement_tools import load_settlements
from backend.evaluation import metrics

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_ground_truth(path: Path = DATA_DIR / "ground_truth.csv") -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _index_cases_by_order_id(cases: list[Case]) -> dict:
    """Ground truth is keyed by order_id (blank for orphan-settlement cases,
    which we instead key by their sole txn_id)."""
    by_order, by_orphan_txn = {}, {}
    for c in cases:
        if c.order_id:
            by_order[c.order_id] = c
        elif c.txns:
            by_orphan_txn[c.txns[0].txn_id] = c
    return by_order, by_orphan_txn


def evaluate(split: str | None = None) -> dict:
    """Runs the full rules engine and scores it against ground_truth.csv.
    Pass split='dev' / 'validation' / 'test_holdout' to score a subset —
    but see BENCHMARK_SPEC.md §1: don't tune against test_holdout."""
    orders = load_orders()
    settlements = load_settlements()
    gt_rows = load_ground_truth()
    if split:
        gt_rows = [r for r in gt_rows if r["split"] == split]

    cases = run_reconciliation(orders, settlements)
    by_order, by_orphan_txn = _index_cases_by_order_id(cases)
    valid_txn_ids = {s.txn_id for s in settlements}

    totals = Counter()
    per_category = defaultdict(Counter)
    mismatches = []

    for row in gt_rows:
        if row["order_id"]:
            predicted = by_order.get(row["order_id"])
        else:
            first_expected_txn = row["expected_txn_ids"].split(";")[0] if row["expected_txn_ids"] else None
            predicted = by_orphan_txn.get(first_expected_txn)

        if predicted is None:
            totals["no_prediction"] += 1
            continue

        cat_ok = metrics.category_correct(predicted, row)
        rec_ok = metrics.record_ids_correct(predicted, row)
        num_ok = metrics.numeric_correct(predicted, row)
        hallucinated = metrics.hallucinated(predicted, valid_txn_ids)
        action_miss = metrics.action_policy_miss(predicted)

        totals["n"] += 1
        totals["category_correct"] += cat_ok
        totals["record_ids_correct"] += rec_ok
        totals["numeric_correct"] += num_ok
        totals["hallucinated"] += hallucinated
        totals["action_policy_miss"] += action_miss

        gt_cat = row["expected_category"]
        per_category[gt_cat]["n"] += 1
        per_category[gt_cat]["category_correct"] += cat_ok
        per_category[gt_cat]["record_ids_correct"] += rec_ok

        if not cat_ok:
            mismatches.append({
                "case_id": row["case_id"], "order_id": row["order_id"],
                "expected": gt_cat, "predicted": predicted.category,
                "predicted_reason": predicted.reason,
            })

    n = max(totals["n"], 1)
    return {
        "split": split or "all",
        "n_cases": totals["n"],
        "no_prediction": totals["no_prediction"],
        "category_accuracy": round(totals["category_correct"] / n, 4),
        "record_id_accuracy": round(totals["record_ids_correct"] / n, 4),
        "numeric_accuracy": round(totals["numeric_correct"] / n, 4),
        "hallucination_rate": round(totals["hallucinated"] / n, 4),
        "action_policy_miss_rate": round(totals["action_policy_miss"] / n, 4),
        "per_category_accuracy": {
            cat: round(c["category_correct"] / max(c["n"], 1), 4) for cat, c in per_category.items()
        },
        "mismatches": mismatches,
    }

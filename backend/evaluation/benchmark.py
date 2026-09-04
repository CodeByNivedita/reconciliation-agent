"""
Run with:  python -m backend.evaluation.benchmark [dev|validation|test_holdout]
No argument scores all 1,000 cases at once.
"""

import sys
import json
from backend.evaluation.evaluator import evaluate


def main():
    split = sys.argv[1] if len(sys.argv) > 1 else None
    result = evaluate(split)

    print(f"\n=== Rules engine benchmark — split: {result['split']} ===")
    print(f"Cases scored:            {result['n_cases']}  (unmatched: {result['no_prediction']})")
    print(f"Category accuracy:       {result['category_accuracy']:.1%}")
    print(f"Record-ID accuracy:      {result['record_id_accuracy']:.1%}")
    print(f"Numeric accuracy:        {result['numeric_accuracy']:.1%}")
    print(f"Hallucination rate:      {result['hallucination_rate']:.1%}")
    print(f"Action-policy miss rate: {result['action_policy_miss_rate']:.1%}")
    print("\nPer-category accuracy:")
    for cat, acc in sorted(result["per_category_accuracy"].items()):
        print(f"  {cat:<28} {acc:.1%}")

    if result["mismatches"]:
        print(f"\n{len(result['mismatches'])} mismatches (showing up to 10):")
        for m in result["mismatches"][:10]:
            print(f"  {m['case_id']} ({m['order_id']}): expected {m['expected']}, "
                  f"got {m['predicted']} — {m['predicted_reason']}")

    with open("benchmark_result.json", "w") as f:
        json.dump(result, f, indent=2)
    print("\nFull result written to benchmark_result.json")


if __name__ == "__main__":
    main()

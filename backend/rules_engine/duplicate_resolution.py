

from itertools import combinations
from backend.config import CONFIG
from backend.models import Settlement


def group_by_amount(candidates: list[Settlement], dp: int = 2) -> dict[float, list[Settlement]]:
    groups: dict[float, list[Settlement]] = {}
    for c in candidates:
        key = round(c.gross_amount, dp)
        groups.setdefault(key, []).append(c)
    return groups


def resolve_genuine_legs(candidates: list[Settlement], order_amount: float):
    """Returns (genuine_legs, extra_legs). `extra_legs` are the duplicate(s)
    to flag for exclusion/reversal."""
    eps = CONFIG["AMOUNT_MATCH_EPS"]

    for r in range(1, len(candidates) + 1):
        for combo in combinations(candidates, r):
            if abs(sum(c.gross_amount for c in combo) - order_amount) <= eps:
                genuine = list(combo)
                return genuine, [c for c in candidates if c not in genuine]

    # No exact partition exists (e.g. duplicate + shortfall combo case):
    # fall back to the subset closest to the order amount and flag the rest.
    all_subsets = [combo for r in range(1, len(candidates) + 1) for combo in combinations(candidates, r)]
    best_subset = min(all_subsets, key=lambda combo: abs(sum(c.gross_amount for c in combo) - order_amount))
    return list(best_subset), [c for c in candidates if c not in best_subset]

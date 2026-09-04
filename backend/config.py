"""
Single source of truth for every threshold the rules engine uses.
Nothing in rules_engine/ should hardcode a number that belongs here.
See ../BENCHMARK_SPEC.md and ../RULES_ENGINE_SPEC.md for the reasoning
behind each value.
"""

CONFIG = {
    "DATE_TOLERANCE_DAYS": 2,

    # All monetary comparisons happen after round(x, AMOUNT_ROUND_DP)
    "AMOUNT_ROUND_DP": 2,
    "AMOUNT_MATCH_EPS": 0.01,
    "GENERIC_REF_NET": 5.00,

    # Tier-2 (generic/blank reference) search window, in days
    "GENERIC_REF_DATE_WINDOW": 5,

    # Top-2 candidate scores closer than this = genuinely ambiguous
    "AMBIGUITY_SCORE_GAP": 0.08,

    # No FX feed wired up -> any cross-currency case is other_conflicting,
    # never auto-converted
    "TRUSTED_FX_SOURCE": None,

    "DEFAULT_ACTIONS": {
        "exact_match": "auto_close",
        "amount_issue": "review",
        "date_issue": "review",
        "missing_record": "review",
        "partial_settlement": "review",
        "duplicate_record": "review",
        "multiple_possible_matches": "abstain",
        "other_conflicting": "escalate",
    },

    "PRECEDENCE": [
        "missing_record", "duplicate_record", "partial_settlement",
        "multiple_possible_matches", "amount_issue", "date_issue",
        "exact_match", "other_conflicting",
    ],

    "STATUS_CONFLICTS": {
        ("cancelled", "settled"),
        ("refunded", "settled"),
    },
}

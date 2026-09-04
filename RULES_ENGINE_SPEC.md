# Rules Engine Specification

This is the deterministic layer the agent calls *before* it does any free-form
reasoning. Its job: given one order and the full settlements table, return a
category, the matched transaction(s), and a default action — with every
decision traceable to a rule, never to model judgment. The LLM's job starts
where this spec explicitly says "hand to the agent" — everywhere else, if
the rules engine can't decide deterministically, that itself is the answer
(`multiple_possible_matches` / `abstain`), not a cue to guess.

## 0. Input schemas (exact columns)

```
orders:       order_id, customer_name, order_date, order_amount, currency,
              payment_method, order_status
settlements:  txn_id, reference_order_id, settlement_date, gross_amount,
              currency, fee, net_amount, settlement_status
```

Note `settlements.reference_order_id` can be: a well-formed id, a
cosmetically-off id, a corrupted/typo'd id, a generic placeholder
(`"UNSPECIFIED"`), or blank.

## 1. Configuration constants (single source of truth)

```python
CONFIG = {
    "DATE_TOLERANCE_DAYS": 2,          # 0-2 days late settlement still exact_match
    "AMOUNT_ROUND_DP": 2,              # round before EVERY comparison
    "AMOUNT_MATCH_EPS": 0.01,          # <= this diff after rounding = "same amount"
    "GENERIC_REF_DATE_WINDOW": 5,      # tier-2 search window for blank/"UNSPECIFIED" refs
    "AMBIGUITY_SCORE_GAP": 0.08,       # top-2 candidate scores closer than this = ambiguous
    "TRUSTED_FX_SOURCE": None,         # no FX feed wired up -> cross-currency is always other_conflicting
}
```

Every threshold in this document is a name from this dict, not a magic
number — tune them here, nowhere else.

## 2. Reference normalization

Handles hyphen/case/leading-zero cosmetics. Deliberately does **not**
special-case a corrupted digit — a reference that's genuinely wrong should
normalize to whatever real order it now spells, if any, not be forced back
onto the order it was probably supposed to say.

```python
import re

def normalize_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    s = ref.strip().upper().replace(" ", "")
    m = re.match(r'^([A-Z]+)-?0*(\d+)$', s)
    if not m:
        return None            # unparseable — never participates in a normalized match
    prefix, digits = m.group(1), m.group(2)
    return f"{prefix}-{int(digits)}"    # int() strips leading zeros regardless of style
```

`normalize_ref("ORD-000123") == normalize_ref("ord000123") == normalize_ref("ORD-00123") == "ORD-123"`.

## 3. Candidate retrieval (three tiers, tried in order)

```python
def get_candidates(order, settlements):
    order_key = normalize_ref(order.order_id)

    # Tier 1 — normalized reference match (covers exact + cosmetic variants)
    tier1 = [s for s in settlements if normalize_ref(s.reference_order_id) == order_key]
    if tier1:
        return tier1, "reference_match", []

    # Tier 2 — generic/blank reference, disambiguated by amount + date proximity
    tier2 = [
        s for s in settlements
        if normalize_ref(s.reference_order_id) is None
        and s.reference_order_id in (None, "", "UNSPECIFIED")
        and abs(round(s.gross_amount, 2) - round(order.order_amount, 2)) <= 500  # loose net; scoring narrows it
        and abs((s.settlement_date - order.order_date).days) <= CONFIG["GENERIC_REF_DATE_WINDOW"]
    ]
    if tier2:
        return tier2, "generic_reference", []

    # Tier 3 — fallback distractor search: nothing referenced THIS order, but something
    # references a DIFFERENT real order while superficially matching amount+date exactly.
    # This never returns a usable candidate — it exists only so the engine can explicitly
    # name and reject a lookalike instead of silently reporting "nothing found."
    tier3 = [
        s for s in settlements
        if normalize_ref(s.reference_order_id) not in (None, order_key)
        and abs(round(s.gross_amount, 2) - round(order.order_amount, 2)) <= CONFIG["AMOUNT_MATCH_EPS"]
        and abs((s.settlement_date - order.order_date).days) <= CONFIG["DATE_TOLERANCE_DAYS"]
    ]
    return [], "none", tier3
```

**Open design decision (flagging, not deciding for you):** Tier 3 is what
turns the "same customer/amount/date, wrong reference" trap into
`other_conflicting` instead of a plain `missing_record`. Without it, a
reference-first engine correctly ignores the lookalike settlement and the
case is indistinguishable from an ordinary unsettled order — which is
arguably *fine* operationally, but throws away the signal that a distractor
existed. Worth deciding deliberately: do you want the engine to actively
surface and log rejected lookalikes (more auditable, more code), or is
"missing, nothing matched" an acceptable answer for that case (simpler)?
The benchmark's ground truth assumes the former.

## 4. Candidate scoring (only reached when Tier 1/2 returns 2+ candidates)

```python
def score(order, s):
    amt_diff = abs(round(s.gross_amount, 2) - round(order.order_amount, 2))
    amt_score = max(0, 1 - amt_diff / max(order.order_amount, 1))
    day_diff = abs((s.settlement_date - order.order_date).days)
    date_score = max(0, 1 - day_diff / 10)
    return 0.6 * amt_score + 0.4 * date_score
```

## 5. Classification procedure (implements the precedence order directly)

```python
def classify(order, all_settlements):
    candidates, tier, distractors = get_candidates(order, all_settlements)

    # --- Rule 1: missing_record ---
    if not candidates:
        if distractors:
            return Case("other_conflicting", txns=[], action="escalate",
                         reason=f"{len(distractors)} settlement(s) match customer/amount/date "
                                f"but reference a different real order — rejected as lookalikes.")
        return Case("missing_record", txns=[], action="review")

    # --- Rule 2: duplicate_record ---
    # Any gross_amount value repeated across 2+ candidates is a duplicate leg, regardless of
    # whether that amount equals the full order_amount or a partial leg.
    by_amount = group_by(candidates, key=lambda c: round(c.gross_amount, 2))
    if any(len(g) >= 2 for g in by_amount.values()):
        genuine, extra = resolve_genuine_legs(candidates, order.order_amount)  # §5a
        return Case("duplicate_record", txns=genuine, action="review",
                     reason=f"{len(extra)} duplicate leg(s) excluded: {[c.txn_id for c in extra]}")

    total = round(sum(c.gross_amount for c in candidates), 2)

    # --- Rule 3: partial_settlement ---
    if len(candidates) >= 2 and total < round(order.order_amount, 2) - CONFIG["AMOUNT_MATCH_EPS"]:
        return Case("partial_settlement", txns=candidates, action="review",
                     reason=f"Legs sum to {total}, order is {order.order_amount} "
                            f"(short by {round(order.order_amount - total, 2)}).")

    # --- Rule 4: multiple_possible_matches (checked BEFORE any single-candidate scoring) ---
    scored = sorted(((score(order, c), c) for c in candidates), key=lambda x: -x[0])
    if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < CONFIG["AMBIGUITY_SCORE_GAP"]:
        return Case("multiple_possible_matches", txns=[c for _, c in scored], action="abstain",
                     reason=f"Top {len(scored)} candidates score within "
                            f"{CONFIG['AMBIGUITY_SCORE_GAP']} of each other.")

    best = scored[0][1]

    # --- Rule 8 (checked here, applies across the board): other_conflicting gates ---
    if best.currency != order.currency:
        return Case("other_conflicting", txns=[best], action="escalate", reason="currency_mismatch")
    if status_conflict(order.order_status, best.settlement_status):     # §6 table
        return Case("other_conflicting", txns=[best], action="escalate", reason="status_conflict")
    if best.gross_amount < 0:
        return Case("other_conflicting", txns=[best], action="escalate", reason="negative_amount")

    amt_diff = round(best.gross_amount, 2) - round(order.order_amount, 2)
    day_diff = (best.settlement_date - order.order_date).days

    # --- Rule 5: amount_issue ---
    if abs(amt_diff) > CONFIG["AMOUNT_MATCH_EPS"]:
        return Case("amount_issue", txns=[best], action="review", reason=f"diff={amt_diff}")

    # --- Rule 6: date_issue ---
    if not (0 <= day_diff <= CONFIG["DATE_TOLERANCE_DAYS"]):
        return Case("date_issue", txns=[best], action="review", reason=f"offset={day_diff:+d}d")

    # --- Rule 7: exact_match ---
    return Case("exact_match", txns=[best], action="auto_close")
```

### 5a. `resolve_genuine_legs` (duplicate vs. partial disambiguation)

```python
def resolve_genuine_legs(candidates, order_amount, eps=CONFIG["AMOUNT_MATCH_EPS"]):
    # Try every subset size; the first subset that sums to order_amount is "genuine",
    # everything else is a duplicate/extra leg to flag for exclusion.
    from itertools import combinations
    for r in range(1, len(candidates) + 1):
        for combo in combinations(candidates, r):
            if abs(sum(c.gross_amount for c in combo) - order_amount) <= eps:
                genuine = list(combo)
                return genuine, [c for c in candidates if c not in genuine]
    # No exact partition exists (e.g. duplicate + shortfall): fall back to the
    # single best-scoring subset and flag the rest — hand the residual to the agent
    # to describe in `reason` rather than silently picking one.
    best_subset = max(
        (combo for r in range(1, len(candidates) + 1) for combo in combinations(candidates, r)),
        key=lambda combo: -abs(sum(c.gross_amount for c in combo) - order_amount),
    )
    return list(best_subset), [c for c in candidates if c not in best_subset]
```

This is a brute-force subset search — fine at the scale of a handful of
candidates per order (this dataset never has more than 3-4), but note it for
what it is if you ever feed it an order with dozens of candidate legs.

## 6. Status compatibility table

```python
STATUS_CONFLICTS = {
    ("cancelled", "settled"),
    ("refunded", "settled"),
    # ("completed", "chargeback") is caught separately by the negative_amount check
}

def status_conflict(order_status, settlement_status):
    return (order_status, settlement_status) in STATUS_CONFLICTS
```

## 7. Orphan-settlement pass (second, settlement-side loop)

After classifying every order, any settlement never selected as a candidate
by any order (i.e. never appears in a `Case.txns` list, including rejected
Tier-3 distractors) is an orphan:

```python
def find_orphans(all_orders, all_settlements, cases):
    claimed = {txn.txn_id for case in cases for txn in case.txns}
    return [s for s in all_settlements if s.txn_id not in claimed]

# each orphan -> Case("missing_record", txns=[orphan], action="review",
#                      reason="Settlement with no matching order (orphan credit).")
```

## 8. Action policy (default per category)

| Category | Default action |
|---|---|
| `exact_match` | `auto_close` |
| `amount_issue` | `review` |
| `date_issue` | `review` |
| `missing_record` | `review` |
| `partial_settlement` | `review` |
| `duplicate_record` | `review` |
| `multiple_possible_matches` | `abstain` |
| `other_conflicting` | `escalate` |

More-cautious substitutions are free; a *less*-cautious action than the
default is an action-policy miss (see `BENCHMARK_SPEC.md` §5).

## 9. Where the LLM takes over

The rules engine above should resolve every case in `ground_truth.csv`
deterministically — that's the point of the benchmark. The agent's actual
job, layered on top, is:

1. **Call this engine as a tool**, not reimplement its logic in a prompt.
2. **Write the `reason` into natural language** the engine's `reason` field
   already gives structured evidence; the agent's value-add is phrasing it
   for a human reviewer, not re-deriving the number.
3. **Handle what the engine can't**: cases the engine flags `abstain` or
   `escalate` are exactly the ones that need a human-legible explanation of
   *why* it's ambiguous/conflicting, since no downstream human will re-run
   the algorithm to find out.
4. **Sanity-check engine output against the raw rows before reporting it** —
   this is your hallucination-rate defense (§4.6 of `BENCHMARK_SPEC.md`):
   never state a txn id, amount, or date the engine didn't actually return.

## 10. Validating this spec

Before writing the agent, run this engine (once implemented) directly
against `ground_truth.csv` and diff its output against `expected_category` /
`expected_txn_ids` per `case_id`. Any mismatch is either a bug in the engine
or a genuine gap in this spec — worth resolving before the LLM is anywhere
near the decision, since it's much cheaper to fix a rule here than to debug
why an agent disagreed with a rule it never had access to.

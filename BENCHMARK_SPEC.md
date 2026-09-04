# Reconciliation Benchmark — Rules & Evaluation Spec

This document is the single source of truth for how `source_orders.csv` and
`source_settlements.csv` should be reconciled, and how an agent's output on
`ground_truth.csv` should be scored. If the agent's answer and the ground
truth ever disagree, check this file before assuming the agent is wrong —
and if the agent's reasoning contradicts a rule below, that's a real miss.

## 1. Files

| File | Rows | Role |
|---|---|---|
| `source_orders.csv` | 975 | Source A — merchant/internal ledger |
| `source_settlements.csv` | 1,267 | Source B — payment gateway / bank settlement feed |
| `ground_truth.csv` | 1,000 cases | Answer key: one row per reconciliation case |

`ground_truth.csv` columns:

- `case_id` — unique case identifier (`C0001` …)
- `order_id` — the order under test (blank for orphan-settlement cases)
- `expected_category` — the correct label (see §3)
- `expected_txn_ids` — semicolon-separated list of the settlement(s) that
  actually belong to this order (blank if none)
- `expected_amount`, `expected_currency` — from the order. **Blank for
  orphan-settlement `missing_record` cases** (§2 defines the full field
  behavior for those).
- `expected_settlement_date` — the (latest) genuine settlement date, blank if none
- `expected_total_settled` — sum of `gross_amount` across `expected_txn_ids`
- `expected_difference` — `expected_amount - expected_total_settled`, **blank
  for orphan-settlement cases** since there is no order amount to diff against
- `split` — `dev` (700) / `validation` (150) / `test_holdout` (150)
- `note` — human-readable explanation of the case

**Do not develop or tune the agent against `test_holdout` rows.** Build and
iterate on `dev`, sanity-check on `validation`, and only score `test_holdout`
once, at the end, for a final unbiased number.

## 2. Reconciliation rules (apply these, don't infer your own)

**Amount comparison** — compare `order_amount` (Source A) to `gross_amount`
(Source B), *not* `net_amount`. `fee` and `net_amount` are informational;
gateway fees are never, by themselves, an `amount_issue`. An agent that flags
every settlement with a nonzero fee as an amount mismatch is wrong.

**Missing-record field rules** — `missing_record` covers two distinct
shapes, with different blank/populated fields:

| Field | Unsettled order (order exists, no settlement) | Orphan settlement (settlement exists, no order) |
|---|---|---|
| `order_id` | the order's id | blank |
| `expected_txn_ids` | blank | the orphan settlement's txn id |
| `expected_amount` / `expected_currency` | from the order | blank |
| `expected_settlement_date` | blank | the settlement's date |
| `expected_total_settled` | `0` | the settlement's `gross_amount` |
| `expected_difference` | full `order_amount` (nothing settled) | blank — no order amount to diff against |

**Monetary precision** — all monetary values are compared after rounding to
2 decimal places. `expected_difference = round(expected_amount -
expected_total_settled, 2)`. Don't fail a case over floating-point noise
like `999.999999` vs `1000.00`.

**Date tolerance** — a settlement dated 0–2 days after the order date is
still `exact_match` (real settlement lag). Only an offset of 3+ days, or a
settlement dated *before* the order (likely a data error), is `date_issue`.

**Currency** — only compare amounts directly when `orders.currency ==
settlements.currency`. A currency mismatch can never be silently netted
against an FX rate the agent invents; without a trusted FX source it must be
flagged as `other_conflicting`, not auto-converted.

**Identifiers** — some `reference_order_id` values are cosmetically
different from the true `order_id` (missing hyphen, different case, a
trimmed leading zero) and *should* be normalized to a match (still
`exact_match`). Others are genuinely corrupted or point to a *different real
order* — these must **not** be normalized into a false match
(`other_conflicting`). The dataset contains both on purpose; an agent that
normalizes everything, or normalizes nothing, will get a chunk of these wrong.

**Superficial-similarity trap** — a few cases have a settlement whose
customer name, amount, and date all match an order, but whose
`reference_order_id` actually belongs to a *different real* order. This is
`other_conflicting`, not `multiple_possible_matches` — the reference check
resolves it with certainty (to the wrong order), so there is no genuine
ambiguity, only a wrong-looking-right candidate that must be deterministically
rejected. (Compare this to the `date_issue` combo case below, where a
distractor's reference resolves to *no* real order at all — that one stays
cleanly `date_issue` because there's no real competing order to conflict
with.) The reference id is the ground truth's tie-breaker.

**Order/settlement status compatibility** — statuses appearing in the
dataset:

| Order status | Settlement status | Interpretation |
|---|---|---|
| `completed` | `settled` | compatible |
| `completed` | `partially_settled` | compatible (see `partial_settlement`) |
| `completed` | (no settlement) | compatible (see `missing_record`) |
| `completed` | `chargeback` (negative amount) | conflict — unflagged chargeback |
| `cancelled` | `settled` | conflict — cancelled order shouldn't have settled |
| `refunded` | `settled` | conflict — refunded order shouldn't still show as settled |
| `cancelled` / `refunded` | (no settlement) | compatible — nothing to reconcile |

## 3. Category precedence (deterministic — use this order)

Some cases satisfy more than one category's description at once (e.g. a
two-part partial settlement that also falls short of the order total). Apply
the **first** matching rule in this list, top to bottom:

1. `missing_record` — no settlement exists at all (or a settlement has no matching order)
2. `duplicate_record` — more settlement legs exist than the order requires, with at least two identical/near-identical legs
3. `partial_settlement` — genuine settlement(s) exist but total less than the order amount, and there's no exact/duplicate/missing condition
4. `multiple_possible_matches` — **check this before evaluating any single candidate's discrepancy.** If, after identifier normalization and all deterministic matching rules (§2), more than one candidate settlement remains equally plausible, classify as `multiple_possible_matches` rather than picking one candidate and scoring it as `amount_issue` or `exact_match`. This must come before amount/date/exact checks — otherwise the same underlying ambiguous case gets a different label depending on which candidate the agent happens to pick (e.g. TXN1=₹1000 vs TXN2=₹950 against a ₹1000 order: picking TXN1 looks like `exact_match`, picking TXN2 looks like `amount_issue`, but the true state is ambiguity).
5. `amount_issue` — a single, uniquely-identified settlement's gross amount doesn't match the order amount
6. `date_issue` — amount matches, but settlement date is outside the tolerance window
7. `exact_match` — amount and date (within tolerance) and reference all agree
8. `other_conflicting` — currency mismatch, status conflict, corrupted/lookalike reference that deterministically resolves to a *different real* order, negative amount, or anything else not covered above

Example: an order with two settlement legs summing to *less* than the order
amount is `partial_settlement`, not `amount_issue` — rule 3 fires before
rule 5 even though "the amount doesn't add up" is technically also true.

## 4. Evaluation rubric

Score an agent's run on each case along independent axes — a case can be
"half right":

1. **Category accuracy** — `predicted_category == expected_category`
2. **Record identification** — predicted transaction id(s) == `expected_txn_ids` (set comparison)
3. **Numerical accuracy** — predicted total settled / difference matches `expected_total_settled` / `expected_difference`
4. **Reasoning quality** — does the stated reason actually cite the evidence that justifies the label (spot-check against `note`)?
5. **Tool efficiency** — number of tool calls / lookups used to reach the answer; flag excessive or redundant searches
6. **Hallucination rate** — did the agent reference an order id, txn id, or amount that doesn't exist in the source files?
7. **Abstention** — for `multiple_possible_matches`, correctly saying "cannot confidently determine the unique settlement" (with a confidence score) counts as a *good* outcome, not a failure to answer

## 5. Expected agent output schema

The agent should emit structured output per case, not free text, so scoring
can be automated:

```json
{
  "case_id": "C0001",
  "predicted_category": "amount_issue",
  "matched_txn_ids": ["TXN-0000123"],
  "order_amount": 1000.00,
  "settled_amount": 950.00,
  "difference": 50.00,
  "confidence": 0.94,
  "reason": "Gross settlement amount is ₹50 lower than the order amount.",
  "action": "review"
}
```

`action` should be one of: `auto_close` (confident exact match),
`review` (needs a human look), `escalate` (conflicting/negative/high-value
discrepancy), or `abstain` (ambiguous — multiple equally-likely candidates).

**Default action per category:**

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

Agents may choose a *more* conservative action than the default (e.g.
`escalate` instead of `review`) without penalty. An action *less* cautious
than the category's default — e.g. `auto_close` on an `amount_issue`, or
`review` on something that should `escalate` — counts as an action-policy
miss, scored separately from category accuracy (§4.1).

## 6. Category distribution

Deliberately kept at **8 categories** — difficulty comes from combinations
and distractors layered *within* a category, not from adding new labels.

| Category | Count | Notes |
|---|---|---|
| exact_match | 400 | incl. 40 needing identifier normalization, and 10 that are the true owner of a settlement that also happens to look like a match for a different order (see `other_conflicting`'s lookalike case) |
| amount_issue | 130 | 65 small-variance, 45 material mismatch, **20 combo: amount mismatch + malformed/lookalike reference** |
| date_issue | 100 | 80 plain (offset 3–8 days, or pre-order date), **20 combo: the genuine settlement is dated outside the tolerance window (still date_issue) while a distractor shares the order's amount and lands exactly ON the order date — but the distractor's reference resolves to no real order, so it's rejected outright and doesn't change the label** |
| missing_record | 100 | 75 unsettled orders, 25 orphan settlements |
| partial_settlement | 80 | 50 clean two-leg sums, **30 combo: partial + shortfall** (settles less than even the intended partial split) |
| duplicate_record | 70 | 25 exact, 25 near (date+1), **20 combo: duplicate + partial** (two genuine legs sum correctly, one extra duplicate leg) |
| multiple_possible_matches | 70 | 1–3 decoys per case; ~40% also add a same-order/wrong-amount distractor |
| other_conflicting | 50 | 10 each: currency mismatch, status conflict, **combo: same customer + same amount + same date + wrong reference — `other_conflicting` rather than `multiple_possible_matches` because the reference deterministically resolves to a different real order (no genuine ambiguity, just a wrong-looking-right candidate)**, corrupted reference, negative amount/chargeback |

Combo cases by design (~100 total, spread across categories above):
- amount issue + wrong-looking reference — 20 (`amount_issue`)
- partial settlement + shortfall — 30 (`partial_settlement`)
- duplicate + partial — 20 (`duplicate_record`)
- same amount + wrong date (genuine settlement is late/early and outside tolerance; a same-amount distractor lands exactly on the order date but its reference is invalid) — 20 (`date_issue`)
- same customer + same amount + same date + wrong reference (deterministically resolves to a different real order) — 10 (`other_conflicting`)

**Split:** 700 `dev` / 150 `validation` / 150 `test_holdout`, stratified so
every category is proportionally represented in all three.

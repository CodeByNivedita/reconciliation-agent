# Reconciliation Agent — Revenue Recovery Intelligence

An agent that reconciles orders against payment-gateway settlements,
built on a **deterministic rules engine** rather than asking an LLM to
re-derive matching logic from scratch on every case. The LLM's job is to
call the engine, phrase its verdict for a human, and handle the cases the
engine explicitly flags as ambiguous or conflicting — never to guess.

## Results

Running the rules engine against the full 1,000-case benchmark
(`data/ground_truth.csv`):

| Metric | Score |
|---|---|
| Category accuracy | **98.7%** |
| Hallucination rate | **0.0%** |
| Action-policy miss rate | **0.0%** |
| Consistency across dev/validation/test_holdout | within 1 point |

The remaining 1.3% is one documented, genuinely hard edge case — see
[Known limitations](#known-limitations) below — not a bug that was left
unfixed.

Reproduce this yourself:

```bash
python -m backend.evaluation.benchmark          # all 1,000 cases
python -m backend.evaluation.benchmark test_holdout   # held-out split only
```

## Quickstart

```bash
pip install -r requirements.txt

# 1. Run the test suite (28 tests, no API key needed)
pytest tests/ -v

# 2. Run the benchmark
python -m backend.evaluation.benchmark

# 3. Start the API
uvicorn backend.main:app --reload

# 4. Open frontend/index.html in a browser (it talks to the API on :8000)
```

To run the actual LLM agent (`backend/agent/agent.py`), copy `.env.example`
to `.env`, set `LLM_PROVIDER` (defaults to `gemini`, which has a genuinely
free tier), and fill in the matching API key. OpenAI and Anthropic both work
too — same file, just uncomment the relevant lines. Everything else — rules
engine, API, benchmark, tests — runs without any of this.

## Project layout

```
data/                   orders.csv, settlements.csv, ground_truth.csv (1,000 cases)
backend/
  config.py             every threshold, in one place
  models.py             Order / Settlement / Case
  rules_engine/         the deterministic layer — see RULES_ENGINE_SPEC.md
  tools/                data access + the reconcile_order tool the agent calls
  agent/                Claude tool-use loop, prompts, structured output schema
  evaluation/           metrics, evaluator, CLI benchmark runner
  services/             ties data + rules engine together for the API
  main.py               FastAPI app
frontend/               queue view, case-detail/reasoning-trace view, benchmark view
tests/                  28 tests: normalization, rules engine, agent plumbing, e2e
BENCHMARK_SPEC.md        the 1,000-case dataset's rules, precedence, tolerances
RULES_ENGINE_SPEC.md     the engine's design spec (pseudocode + rationale)
```

Read `BENCHMARK_SPEC.md` first (what the data means and how it should be
judged), then `RULES_ENGINE_SPEC.md` (how the engine implements that), then
the code — in that order, the design decisions actually make sense.

## Architecture

```
Source data (orders + settlements)
        │
        ▼
Candidate retrieval  (reference match → generic-reference match → lookalike check)
        │
        ▼
Rules engine  (precedence-ordered: missing → duplicate → partial →
               ambiguous → amount → date → exact → conflicting)
        │
        ▼
Category assigned + confidence
        │
        ▼
Action policy  (auto_close / review / escalate / abstain)
        │
        ▼
Structured output ──► Agent phrases it for a human ──► Evaluation engine
```

The agent sits *around* the rules engine, not instead of it. See
`RULES_ENGINE_SPEC.md` §9 for exactly where the boundary is.

## Known limitations

**Reciprocal reference collisions.** A small number of `amount_issue`
combo cases have a reference typo that happens to spell a *different real
order's* id (by design — see `BENCHMARK_SPEC.md`'s combo cases). When that
happens, the current per-order, greedy matching engine can misattribute a
settlement to the wrong order, because each order is resolved independently
without checking whether a better-fitting order exists elsewhere in the
dataset. Fixing this properly needs cross-order arbitration (a bipartite
assignment pass over the whole settlements table), which is a deliberate
scope decision, not an oversight — see `RULES_ENGINE_SPEC.md` §3's "open
design decision" note. This affects 13 of 1,000 cases (1.3%).

**Tier-3 lookalike detection adds real complexity for one benchmark
category.** The engine actively searches for and names "lookalike"
distractors (settlements matching customer/amount/date but referencing a
different real order) specifically so `other_conflicting` cases are
auditable rather than silently reported as `missing_record`. This is a
deliberate trade-off documented in `RULES_ENGINE_SPEC.md` §3 — worth
revisiting if the false-positive cost of a broader search ever outweighs
the auditability benefit in a larger, real dataset.

## Testing philosophy

`tests/test_end_to_end.py` asserts an accuracy *floor* against the full
benchmark, not exact figures — so it catches regressions without becoming
brittle to minor, intentional engine tweaks. If you change the rules engine
and this test fails, that's a signal to re-read `RULES_ENGINE_SPEC.md`
before changing the threshold — the number is the floor we already proved
we can hit, not an arbitrary target.

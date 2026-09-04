
from backend.config import CONFIG
from backend.models import Order, Settlement, Case
from backend.rules_engine.candidate_retrieval import get_candidates
from backend.rules_engine.scoring import score
from backend.rules_engine.duplicate_resolution import group_by_amount, resolve_genuine_legs
from backend.rules_engine.status_rules import status_conflict
from backend.rules_engine.action_policy import default_action


def classify(order: Order, all_settlements: list[Settlement]) -> Case:
    eps = CONFIG["AMOUNT_MATCH_EPS"]
    candidates, tier, distractors = get_candidates(order, all_settlements)

    # --- Rule 1: missing_record ---
    if not candidates:
        if distractors:
            names = ", ".join(d.txn_id for d in distractors)
            case = Case(
                order_id=order.order_id, category="other_conflicting", txns=[],
                reason=f"{len(distractors)} settlement(s) match customer/amount/date but reference "
                       f"a different real order — rejected as lookalike(s): {names}.",
            )
        else:
            case = Case(order_id=order.order_id, category="missing_record", txns=[],
                        reason="No settlement found for this order.")
        case.action = default_action(case.category)
        case.confidence = 0.9
        return case

    # --- Rule 2: duplicate_record ---
    # Only meaningful when candidates are reference-confirmed: a repeated
    # amount among purely generic-reference candidates isn't proof of a
    # duplicate charge against THIS order — it's exactly the ambiguity
    # Rule 4 exists to catch, so we deliberately skip this check for
    # "generic_reference" and "mixed" tiers.
    if tier == "reference_match":
        by_amount = group_by_amount(candidates)
        if any(len(g) >= 2 for g in by_amount.values()):
            genuine, extra = resolve_genuine_legs(candidates, order.order_amount)
            extra_ids = ", ".join(c.txn_id for c in extra)
            case = Case(
                order_id=order.order_id, category="duplicate_record", txns=genuine,
                reason=f"Duplicate leg(s) excluded: {extra_ids}." if extra else "Duplicate settlement detected.",
            )
            case.action = default_action(case.category)
            case.confidence = 0.85
            return case

    total = round(sum(c.gross_amount for c in candidates), 2)

    # --- Rule 3: partial_settlement ---
    # Only meaningful for reference-confirmed legs, among candidates that
    # could plausibly BE a partial leg. Two guards against reference-collision
    # phantoms (see RULES_ENGINE_SPEC.md's note on reciprocal collisions):
    #   (a) a leg whose amount alone exceeds the full order can't be a leg;
    #   (b) if any single candidate already matches the order amount exactly,
    #       that one IS the real settlement — a second candidate alongside it
    #       is noise, not a genuine second leg, so don't treat this as partial.
    has_exact_single = any(abs(round(c.gross_amount, 2) - round(order.order_amount, 2)) <= eps for c in candidates)
    plausible_legs = [c for c in candidates if round(c.gross_amount, 2) <= round(order.order_amount, 2) + eps]
    if tier == "reference_match" and len(plausible_legs) >= 2 and not has_exact_single:
        leg_total = round(sum(c.gross_amount for c in plausible_legs), 2)
        if leg_total < round(order.order_amount, 2) - eps:
            shortfall = round(order.order_amount - leg_total, 2)
            reason = f"Legs sum to {leg_total}, order is {order.order_amount} (short by {shortfall})."
        else:
            reason = f"Order was settled in {len(plausible_legs)} parts summing to {leg_total}."
        case = Case(order_id=order.order_id, category="partial_settlement", txns=plausible_legs, reason=reason)
        case.action = default_action(case.category)
        case.confidence = 0.85
        return case

    # --- Rule 4: multiple_possible_matches — checked BEFORE any single-candidate scoring ---
    scored = sorted(((score(order, c), c) for c in candidates), key=lambda x: -x[0])
    if len(scored) >= 2 and (scored[0][0] - scored[1][0]) < CONFIG["AMBIGUITY_SCORE_GAP"]:
        case = Case(
            order_id=order.order_id, category="multiple_possible_matches",
            txns=[c for _, c in scored],
            reason=f"Top {len(scored)} candidates score within {CONFIG['AMBIGUITY_SCORE_GAP']} "
                   f"of each other — no confident unique match.",
        )
        case.action = default_action(case.category)
        case.confidence = round(0.5 + (scored[0][0] - scored[1][0]), 2)
        return case

    best = scored[0][1]

    # --- other_conflicting gates ---
    if best.currency != order.currency:
        case = Case(order_id=order.order_id, category="other_conflicting", txns=[best],
                    reason=f"Currency mismatch: order is {order.currency}, settlement is {best.currency}.")
        case.action = default_action(case.category); case.confidence = 0.9
        return case
    if status_conflict(order.order_status, best.settlement_status):
        case = Case(order_id=order.order_id, category="other_conflicting", txns=[best],
                    reason=f"Order status '{order.order_status}' conflicts with settlement "
                           f"status '{best.settlement_status}'.")
        case.action = default_action(case.category); case.confidence = 0.9
        return case
    if best.gross_amount < 0:
        case = Case(order_id=order.order_id, category="other_conflicting", txns=[best],
                    reason="Settlement shows a negative gross amount — unflagged chargeback.")
        case.action = default_action(case.category); case.confidence = 0.9
        return case

    amt_diff = round(best.gross_amount, 2) - round(order.order_amount, 2)
    day_diff = (best.settlement_date - order.order_date).days

    # --- Rule 5: amount_issue ---
    if abs(amt_diff) > eps:
        case = Case(order_id=order.order_id, category="amount_issue", txns=[best],
                    reason=f"Gross settlement amount differs from order amount by {amt_diff}.")
        case.action = default_action(case.category); case.confidence = 0.85
        return case

    # --- Rule 6: date_issue ---
    if not (0 <= day_diff <= CONFIG["DATE_TOLERANCE_DAYS"]):
        case = Case(order_id=order.order_id, category="date_issue", txns=[best],
                    reason=f"Settlement date is {day_diff:+d} day(s) from order date — beyond the "
                           f"{CONFIG['DATE_TOLERANCE_DAYS']}-day tolerance.")
        case.action = default_action(case.category); case.confidence = 0.85
        return case

    # --- Rule 7: exact_match ---
    case = Case(order_id=order.order_id, category="exact_match", txns=[best],
                reason="Amount and date (within tolerance) and reference all agree.")
    case.action = default_action(case.category)
    case.confidence = 0.98
    return case

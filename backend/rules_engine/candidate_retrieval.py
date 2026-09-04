

from backend.config import CONFIG
from backend.models import Order, Settlement
from backend.rules_engine.normalization import normalize_ref


def get_candidates(order: Order, settlements: list[Settlement]):
    order_key = normalize_ref(order.order_id)
    eps = CONFIG["AMOUNT_MATCH_EPS"]

    # Tier 1 — normalized reference match (covers exact + cosmetic variants).
    # A reference match is strong evidence but NOT proof on its own: a
    # correctly-referenced settlement with a wildly wrong amount doesn't
    # outrank a well-fitting generic-reference candidate elsewhere — it
    # just means both should be considered together (see "mixed" below).
    ref_matches = [s for s in settlements if normalize_ref(s.reference_order_id) == order_key]

    # Tier 2 — generic/blank reference, disambiguated by amount + date proximity
    generic_matches = [
        s for s in settlements
        if normalize_ref(s.reference_order_id) is None
        and s.reference_order_id in (None, "", "UNSPECIFIED")
        and abs(round(s.gross_amount, 2) - round(order.order_amount, 2)) <= CONFIG["GENERIC_REF_NET"]
        and abs((s.settlement_date - order.order_date).days) <= CONFIG["GENERIC_REF_DATE_WINDOW"]
    ]

    ref_matches_implausible = ref_matches and all(
        abs(round(s.gross_amount, 2) - round(order.order_amount, 2)) > eps for s in ref_matches
    )

    if ref_matches and generic_matches and ref_matches_implausible:
        # Every referenced candidate is amount-implausible, but a well-fitting
        # generic candidate also exists — don't let the reference match win
        # by default; pool both and let scoring/ambiguity sort it out.
        return ref_matches + generic_matches, "mixed", []
    if ref_matches:
        return ref_matches, "reference_match", []
    if generic_matches:
        return generic_matches, "generic_reference", []

    # Tier 3 — fallback distractor search: nothing references THIS order, but
    # something references a DIFFERENT real order while superficially
    # matching amount+date exactly. Never a usable candidate — exists only so
    # the engine can name and reject a lookalike instead of going silent.
    tier3 = [
        s for s in settlements
        if normalize_ref(s.reference_order_id) not in (None, order_key)
        and abs(round(s.gross_amount, 2) - round(order.order_amount, 2)) <= eps
        and abs((s.settlement_date - order.order_date).days) <= CONFIG["DATE_TOLERANCE_DAYS"]
    ]
    return [], "none", tier3

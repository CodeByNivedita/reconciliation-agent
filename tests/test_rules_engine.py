from datetime import date
from backend.models import Order, Settlement
from backend.rules_engine.classification import classify


def make_order(**kw):
    defaults = dict(order_id="ORD-000001", customer_name="Test User", order_date=date(2026, 1, 1),
                     order_amount=1000.0, currency="INR", payment_method="UPI", order_status="completed")
    defaults.update(kw)
    return Order(**defaults)


def make_settlement(**kw):
    defaults = dict(txn_id="TXN-0000001", reference_order_id="ORD-000001", settlement_date=date(2026, 1, 1),
                     gross_amount=1000.0, currency="INR", fee=20.0, net_amount=980.0, settlement_status="settled")
    defaults.update(kw)
    return Settlement(**defaults)


def test_exact_match():
    order = make_order()
    settlement = make_settlement()
    case = classify(order, [settlement])
    assert case.category == "exact_match"
    assert case.action == "auto_close"


def test_exact_match_within_date_tolerance():
    order = make_order()
    settlement = make_settlement(settlement_date=date(2026, 1, 3))  # +2 days
    case = classify(order, [settlement])
    assert case.category == "exact_match"


def test_date_issue_beyond_tolerance():
    order = make_order()
    settlement = make_settlement(settlement_date=date(2026, 1, 4))  # +3 days
    case = classify(order, [settlement])
    assert case.category == "date_issue"


def test_amount_issue():
    order = make_order()
    settlement = make_settlement(gross_amount=950.0)
    case = classify(order, [settlement])
    assert case.category == "amount_issue"


def test_missing_record():
    order = make_order()
    case = classify(order, [])
    assert case.category == "missing_record"
    assert case.action == "review"


def test_duplicate_record():
    order = make_order()
    s1 = make_settlement(txn_id="TXN-0001")
    s2 = make_settlement(txn_id="TXN-0002")
    case = classify(order, [s1, s2])
    assert case.category == "duplicate_record"


def test_partial_settlement_clean_split():
    order = make_order(order_amount=1000.0)
    s1 = make_settlement(txn_id="TXN-0001", gross_amount=600.0)
    s2 = make_settlement(txn_id="TXN-0002", gross_amount=400.0)
    case = classify(order, [s1, s2])
    assert case.category == "partial_settlement"
    assert case.total_settled() == 1000.0


def test_partial_settlement_with_shortfall():
    order = make_order(order_amount=1000.0)
    s1 = make_settlement(txn_id="TXN-0001", gross_amount=500.0)
    s2 = make_settlement(txn_id="TXN-0002", gross_amount=300.0)
    case = classify(order, [s1, s2])
    assert case.category == "partial_settlement"
    assert case.total_settled() == 800.0


def test_multiple_possible_matches():
    order = make_order(order_amount=1000.0)
    s1 = make_settlement(txn_id="TXN-0001", reference_order_id="UNSPECIFIED")
    s2 = make_settlement(txn_id="TXN-0002", reference_order_id="UNSPECIFIED",
                          settlement_date=date(2026, 1, 2))
    case = classify(order, [s1, s2])
    assert case.category == "multiple_possible_matches"
    assert case.action == "abstain"


def test_currency_mismatch_is_other_conflicting():
    order = make_order(currency="INR")
    settlement = make_settlement(currency="USD", gross_amount=12.0)
    case = classify(order, [settlement])
    assert case.category == "other_conflicting"


def test_status_conflict_is_other_conflicting():
    order = make_order(order_status="cancelled")
    settlement = make_settlement(settlement_status="settled")
    case = classify(order, [settlement])
    assert case.category == "other_conflicting"


def test_negative_amount_is_other_conflicting():
    order = make_order()
    settlement = make_settlement(gross_amount=-500.0)
    case = classify(order, [settlement])
    assert case.category == "other_conflicting"


def test_action_never_less_cautious_than_default():
    from backend.rules_engine.action_policy import is_less_cautious
    assert is_less_cautious("auto_close", "amount_issue") is True
    assert is_less_cautious("escalate", "amount_issue") is False
    assert is_less_cautious("auto_close", "exact_match") is False

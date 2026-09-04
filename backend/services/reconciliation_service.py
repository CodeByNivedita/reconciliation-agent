from functools import lru_cache

from backend.models import Case
from backend.rules_engine.engine import run_reconciliation
from backend.rules_engine.action_policy import default_action
from backend.tools.order_tools import load_orders, get_order
from backend.tools.settlement_tools import load_settlements


@lru_cache(maxsize=1)
def _cached_data():
    return load_orders(), load_settlements()


@lru_cache(maxsize=1)
def get_all_cases() -> list[Case]:
    orders, settlements = _cached_data()
    return run_reconciliation(orders, settlements)


def get_queue_summary() -> dict:
    cases = get_all_cases()
    by_action = {}
    for c in cases:
        by_action[c.action] = by_action.get(c.action, 0) + 1
    total_at_risk = round(sum(
        o.order_amount for o in _cached_data()[0]
        if get_case_for_order(o.order_id) and get_case_for_order(o.order_id).action != "auto_close"
    ), 2)
    return {
        "total_cases": len(cases),
        "by_action": by_action,
        "value_in_exceptions": total_at_risk,
    }


def get_case_for_order(order_id: str) -> Case | None:
    for c in get_all_cases():
        if c.order_id == order_id:
            return c
    return None


def get_case_detail(order_id: str) -> dict | None:
    orders, settlements = _cached_data()
    order = get_order(order_id, orders)
    case = get_case_for_order(order_id)
    if not order or not case:
        return None
    return {
        "order": {
            "order_id": order.order_id, "customer_name": order.customer_name,
            "order_date": order.order_date.isoformat(), "order_amount": order.order_amount,
            "currency": order.currency, "order_status": order.order_status,
        },
        "settlements": [
            {
                "txn_id": t.txn_id, "reference_order_id": t.reference_order_id,
                "settlement_date": t.settlement_date.isoformat(), "gross_amount": t.gross_amount,
                "currency": t.currency, "settlement_status": t.settlement_status,
            }
            for t in case.txns
        ],
        "verdict": case.to_dict(),
    }


def list_cases(action: str | None = None, category: str | None = None) -> list[dict]:
    cases = get_all_cases()
    if action:
        cases = [c for c in cases if c.action == action]
    if category:
        cases = [c for c in cases if c.category == category]
    return [c.to_dict() for c in cases]

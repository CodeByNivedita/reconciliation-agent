
from backend.models import Order, Settlement, Case
from backend.rules_engine.classification import classify
from backend.rules_engine.orphan_detection import find_orphans


def run_reconciliation(orders: list[Order], settlements: list[Settlement]) -> list[Case]:
    """Classifies every order, then appends orphan-settlement cases.
    Returns one Case per order plus one Case per orphan settlement — this
    matches ground_truth.csv's shape exactly (1 row per case_id)."""
    cases = [classify(order, settlements) for order in orders]
    cases.extend(find_orphans(settlements, cases))
    return cases


def classify_one(order_id: str, orders: list[Order], settlements: list[Settlement]) -> Case:
    """Convenience entry point for a single order lookup (used by the API and by agent tools)."""
    order = next((o for o in orders if o.order_id == order_id), None)
    if order is None:
        raise KeyError(f"No such order: {order_id}")
    return classify(order, settlements)

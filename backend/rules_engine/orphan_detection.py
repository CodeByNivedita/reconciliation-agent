

from backend.models import Case, Settlement
from backend.rules_engine.action_policy import default_action


def find_orphans(all_settlements: list[Settlement], cases: list[Case]) -> list[Case]:
    claimed = {txn_id for case in cases for txn_id in case.matched_txn_ids()}
    orphans = [s for s in all_settlements if s.txn_id not in claimed]
    out = []
    for o in orphans:
        c = Case(order_id=None, category="missing_record", txns=[o],
                 reason="Settlement with no matching order (orphan credit).")
        c.action = default_action(c.category)
        c.confidence = 0.9
        out.append(c)
    return out

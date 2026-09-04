"""
These tests mock the Anthropic client so the suite runs without a real
ANTHROPIC_API_KEY or network access. They check the plumbing (tool schema,
tool wiring), not model behavior — model behavior is what benchmark.py and
the live agent are for.
"""

from backend.tools.reconciliation_tools import reconcile_order_tool, RECONCILE_ORDER_TOOL_SCHEMA
from backend.tools.order_tools import load_orders
from backend.tools.settlement_tools import load_settlements


def test_tool_schema_has_required_fields():
    assert RECONCILE_ORDER_TOOL_SCHEMA["name"] == "reconcile_order"
    assert "order_id" in RECONCILE_ORDER_TOOL_SCHEMA["input_schema"]["properties"]
    assert RECONCILE_ORDER_TOOL_SCHEMA["input_schema"]["required"] == ["order_id"]


def test_reconcile_order_tool_returns_agent_output_shape():
    orders = load_orders()
    settlements = load_settlements()
    result = reconcile_order_tool(orders[0].order_id, orders, settlements)
    assert set(result.keys()) == {
        "order_id", "predicted_category", "matched_txn_ids",
        "settled_amount", "confidence", "reason", "action",
    }
    assert result["predicted_category"] in {
        "exact_match", "amount_issue", "date_issue", "missing_record",
        "partial_settlement", "duplicate_record", "multiple_possible_matches",
        "other_conflicting",
    }


def test_reconcile_order_tool_unknown_order_raises():
    orders = load_orders()
    settlements = load_settlements()
    try:
        reconcile_order_tool("ORD-DOES-NOT-EXIST", orders, settlements)
        assert False, "expected KeyError"
    except KeyError:
        pass

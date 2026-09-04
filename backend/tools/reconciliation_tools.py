"""
This is the tool definition an LLM agent should be given — a thin wrapper
around rules_engine.engine so the model calls the deterministic logic
instead of re-deriving it in a prompt. See RULES_ENGINE_SPEC.md §9.
"""

from backend.models import Order, Settlement
from backend.rules_engine.engine import classify_one


def reconcile_order_tool(order_id: str, orders: list[Order], settlements: list[Settlement]) -> dict:
    """Tool the agent calls with a single order_id. Returns the engine's
    structured verdict — the agent should report this, not second-guess it,
    except to phrase `reason` for a human reader."""
    case = classify_one(order_id, orders, settlements)
    return case.to_dict()


# Anthropic tool-use schema for this function, for agent/agent.py to register.
RECONCILE_ORDER_TOOL_SCHEMA = {
    "name": "reconcile_order",
    "description": (
        "Runs the deterministic reconciliation rules engine for a single order_id "
        "and returns its category, matched transaction id(s), settled amount, "
        "confidence, reason, and default action. Always call this before stating "
        "a reconciliation verdict — never classify a case from memory or from the "
        "raw CSV rows alone."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "The order_id to reconcile, e.g. 'ORD-000123'."},
        },
        "required": ["order_id"],
    },
}

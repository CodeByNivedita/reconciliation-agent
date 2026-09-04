"""
Typed models shared across the rules engine, tools, agent, and evaluation
layers. Field names match the CSV columns exactly — see ../BENCHMARK_SPEC.md §1.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Order:
    order_id: str
    customer_name: str
    order_date: date
    order_amount: float
    currency: str
    payment_method: str
    order_status: str


@dataclass
class Settlement:
    txn_id: str
    reference_order_id: Optional[str]
    settlement_date: date
    gross_amount: float
    currency: str
    fee: float
    net_amount: float
    settlement_status: str


@dataclass
class Case:
    """Output of the rules engine for a single order (or a single orphan settlement)."""
    order_id: Optional[str]
    category: str
    txns: list[Settlement] = field(default_factory=list)
    action: Optional[str] = None          # filled in by action_policy.py if not set explicitly
    confidence: Optional[float] = None
    reason: str = ""

    def matched_txn_ids(self) -> list[str]:
        return [t.txn_id for t in self.txns]

    def total_settled(self) -> float:
        return round(sum(t.gross_amount for t in self.txns), 2)

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "predicted_category": self.category,
            "matched_txn_ids": self.matched_txn_ids(),
            "settled_amount": self.total_settled(),
            "confidence": self.confidence,
            "reason": self.reason,
            "action": self.action,
        }

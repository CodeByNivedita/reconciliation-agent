"""Matches ../../BENCHMARK_SPEC.md §5 exactly."""

from pydantic import BaseModel, Field
from typing import Literal, Optional


class AgentCaseOutput(BaseModel):
    case_id: str
    predicted_category: Literal[
        "exact_match", "amount_issue", "date_issue", "missing_record",
        "partial_settlement", "duplicate_record", "multiple_possible_matches",
        "other_conflicting",
    ]
    matched_txn_ids: list[str] = Field(default_factory=list)
    order_amount: Optional[float] = None
    settled_amount: Optional[float] = None
    difference: Optional[float] = None
    confidence: float
    reason: str
    action: Literal["auto_close", "review", "escalate", "abstain"]

"""
Data-access "tools" — these are the functions an LLM agent would call
(directly, or wrapped as tool definitions in agent/agent.py) to read the
source-of-truth tables. They never make a reconciliation decision
themselves; that's the rules engine's job.
"""

import csv
from datetime import date
from pathlib import Path
from backend.models import Order

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def load_orders(path: Path = DATA_DIR / "orders.csv") -> list[Order]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Order(
                order_id=row["order_id"],
                customer_name=row["customer_name"],
                order_date=_parse_date(row["order_date"]),
                order_amount=float(row["order_amount"]),
                currency=row["currency"],
                payment_method=row["payment_method"],
                order_status=row["order_status"],
            )
            for row in csv.DictReader(f)
        ]


def get_order(order_id: str, orders: list[Order]) -> Order | None:
    return next((o for o in orders if o.order_id == order_id), None)


def find_orders_by_customer(name_fragment: str, orders: list[Order]) -> list[Order]:
    frag = name_fragment.lower()
    return [o for o in orders if frag in o.customer_name.lower()]

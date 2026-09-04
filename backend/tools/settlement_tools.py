import csv
from datetime import date
from pathlib import Path
from backend.models import Settlement

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def load_settlements(path: Path = DATA_DIR / "settlements.csv") -> list[Settlement]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Settlement(
                txn_id=row["txn_id"],
                reference_order_id=row["reference_order_id"] or None,
                settlement_date=_parse_date(row["settlement_date"]),
                gross_amount=float(row["gross_amount"]),
                currency=row["currency"],
                fee=float(row["fee"]),
                net_amount=float(row["net_amount"]),
                settlement_status=row["settlement_status"],
            )
            for row in csv.DictReader(f)
        ]


def get_settlement(txn_id: str, settlements: list[Settlement]) -> Settlement | None:
    return next((s for s in settlements if s.txn_id == txn_id), None)


def find_settlements_by_amount(amount: float, settlements: list[Settlement], eps: float = 0.01) -> list[Settlement]:
    return [s for s in settlements if abs(s.gross_amount - amount) <= eps]

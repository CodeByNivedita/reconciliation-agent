

from backend.models import Order, Settlement


def score(order: Order, s: Settlement) -> float:
    amt_diff = abs(round(s.gross_amount, 2) - round(order.order_amount, 2))
    amt_score = max(0.0, 1 - amt_diff / max(order.order_amount, 1))
    day_diff = abs((s.settlement_date - order.order_date).days)
    date_score = max(0.0, 1 - day_diff / 10)
    return 0.6 * amt_score + 0.4 * date_score

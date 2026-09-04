

from backend.config import CONFIG


def status_conflict(order_status: str, settlement_status: str) -> bool:
    return (order_status, settlement_status) in CONFIG["STATUS_CONFLICTS"]

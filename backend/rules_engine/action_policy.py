from backend.config import CONFIG

CAUTION_ORDER = ["auto_close", "review", "escalate", "abstain"]


def default_action(category: str) -> str:
    return CONFIG["DEFAULT_ACTIONS"][category]


def is_less_cautious(predicted_action: str, category: str) -> bool:
    default = default_action(category)
    return CAUTION_ORDER.index(predicted_action) < CAUTION_ORDER.index(default)

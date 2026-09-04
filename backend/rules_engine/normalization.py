
import re
from typing import Optional

_PATTERN = re.compile(r'^([A-Z]+)-?0*(\d+)$')


def normalize_ref(ref: Optional[str]) -> Optional[str]:
    if not ref:
        return None
    s = ref.strip().upper().replace(" ", "")
    m = _PATTERN.match(s)
    if not m:
        return None  # unparseable — never participates in a normalized match
    prefix, digits = m.group(1), m.group(2)
    return f"{prefix}-{int(digits)}"

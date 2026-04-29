"""Input validation (same as A3 book service)."""
import re
from decimal import Decimal, InvalidOperation

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_price(value) -> bool:
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return False
    if d < Decimal("0"):
        return False
    _sign, _digits, exponent = d.as_tuple()
    return exponent >= -2


def check_required_fields(data: dict, required: list) -> list:
    missing = []
    for field in required:
        if field not in data or data[field] is None:
            missing.append(field)
    return missing

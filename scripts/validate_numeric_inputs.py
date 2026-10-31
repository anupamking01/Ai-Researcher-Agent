"""Validation helpers for reproducible experiment inputs.

These helpers deliberately fail closed: malformed measurements should stop an
analysis rather than silently enter a research table or statistical test.
"""
from __future__ import annotations

import math
from decimal import Decimal


def require_finite_number(value: str, field: str) -> float:
    """Parse a numeric value and reject missing, NaN, and infinite values."""
    if value is None or not str(value).strip():
        raise ValueError(f"missing numeric field: {field}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric value for {field}: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite value for {field}: {value!r}")
    return parsed


def require_nonnegative(value: str, field: str) -> float:
    """Reject negative and underflowed measurements before float conversion loses them."""
    parsed = require_finite_number(value, field)
    exact = Decimal(str(value).strip())
    if exact < 0:
        raise ValueError(f"negative value for {field}: {value!r}")
    if exact != 0 and parsed == 0.0:
        raise ValueError(f"underflow value for {field}: {value!r}")
    return parsed


def require_nonnegative_integer(value: str, field: str) -> int:
    """Require an exact non-negative integer count without rounding.

    Research count fields (claims, sources, calls, tokens) must not silently
    turn values such as ``3.6`` into ``4``. Scientific input validation should
    reject a malformed count rather than repair it implicitly.
    """
    # Keep the established finite-float input range, but never use float to
    # decide integrality or return a count: it rounds values above 2**53 and
    # can erase tiny fractional/negative CSV values through underflow.
    require_finite_number(value, field)
    parsed = Decimal(str(value).strip())
    if parsed < 0:
        raise ValueError(f"negative value for {field}: {value!r}")
    if parsed != parsed.to_integral_value():
        raise ValueError(f"non-integer value for {field}: {value!r}")
    return int(parsed)


def require_unit_interval(value: str, field: str) -> float:
    """Require exact [0, 1] bounds without float boundary rounding or underflow."""
    parsed = require_finite_number(value, field)
    exact = Decimal(str(value).strip())
    if not 0 <= exact <= 1:
        raise ValueError(f"value outside [0, 1] for {field}: {value!r}")
    if exact != 0 and parsed == 0.0:
        raise ValueError(f"underflow value for {field}: {value!r}")
    return parsed

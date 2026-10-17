"""Validation helpers for reproducible experiment inputs.

These helpers deliberately fail closed: malformed measurements should stop an
analysis rather than silently enter a research table or statistical test.
"""
from __future__ import annotations

import math


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
    """Parse a finite number and reject impossible negative measurements."""
    parsed = require_finite_number(value, field)
    if parsed < 0:
        raise ValueError(f"negative value for {field}: {parsed}")
    return parsed


def require_nonnegative_integer(value: str, field: str) -> int:
    """Require an exact non-negative integer count without rounding.

    Research count fields (claims, sources, calls, tokens) must not silently
    turn values such as ``3.6`` into ``4``. Scientific input validation should
    reject a malformed count rather than repair it implicitly.
    """
    parsed = require_nonnegative(value, field)
    if not parsed.is_integer():
        raise ValueError(f"non-integer value for {field}: {parsed}")
    return int(parsed)


def require_unit_interval(value: str, field: str) -> float:
    """Require a finite proportion in the closed interval [0, 1]."""
    parsed = require_finite_number(value, field)
    if not 0.0 <= parsed <= 1.0:
        raise ValueError(f"value outside [0, 1] for {field}: {parsed}")
    return parsed

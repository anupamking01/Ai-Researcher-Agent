"""Validation helpers for reproducible experiment inputs."""
from __future__ import annotations

import math


def require_finite_number(value: str, field: str) -> float:
    """Parse a numeric CSV value and reject missing, NaN, and infinite values."""
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

"""Independent source-to-summary audit for diagnostic pilot arm-level metrics.

Only schema-v3 pilot summaries assert this independent reconciliation. Earlier
summaries retain their historical schema rather than acquiring retroactive
verification claims. This uses selected trace records, never summarized rows,
the producer's _variant_summary(), or inferred missing measurements.
"""
from __future__ import annotations

import math

_ARMS = ("D6", "P6", "P6V")
_COUNTER_METRICS = {
    "avg_source_attempts": "source_count",
    "avg_successful_sources": "successful_source_count",
    "avg_failed_sources": "failed_source_count",
    "avg_search_calls": "search_call_count",
    "avg_model_calls": "model_call_count",
    "avg_prompt_tokens": "prompt_tokens",
    "avg_completion_tokens": "completion_tokens",
    "avg_total_tokens": "total_tokens",
    "avg_report_words": "report_words",
}
_AUDITED_METRICS = (
    "n_runs", "n_completed", "completion_rate",
    *_COUNTER_METRICS,
    "avg_latency_seconds", "avg_claim_support_rate_verified_only",
    "verified_runs", "provider_usage_complete_runs",
)


def _counter(trace: dict, field: str, label: str) -> int:
    # Match the producer's documented absent-legacy-counter convention, but
    # never coerce a supplied boolean, fractional, negative or string value.
    value = trace.get(field, 0)
    if type(value) is not int or value < 0:
        raise ValueError(f"{label}.{field} must be a nonnegative integer")
    return value


def _continuous(trace: dict, field: str, label: str, upper=None) -> float:
    value = trace.get(field, 0.0)
    if type(value) not in (int, float) or value < 0:
        raise ValueError(f"{label}.{field} must be a finite nonnegative measurement")
    try:
        valid = math.isfinite(value) and (upper is None or value <= upper)
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise ValueError(f"{label}.{field} must be a finite in-range measurement")
    return float(value)


def _mean(values: list[int | float]) -> float | None:
    if not values:
        return None
    try:
        result = math.fsum(values) / len(values)
    except (OverflowError, ValueError) as exc:
        raise ValueError("pilot source mean overflowed") from exc
    if not math.isfinite(result):
        raise ValueError("pilot source mean is nonfinite")
    return result


def _match(observed: dict, field: str, expected: int | float | None, label: str,
           errors: list[str]) -> None:
    key = f"{label}.{field}"
    if field not in observed:
        errors.append(f"{key} missing from version-3 arm summary")
        return
    actual = observed[field]
    if expected is None:
        if actual is not None:
            errors.append(f"{key} must be null for unavailable measurements")
    elif type(expected) is int:
        if type(actual) is not int or actual != expected:
            errors.append(f"{key} disagrees with selected pilot traces")
    elif type(actual) not in (int, float):
        errors.append(f"{key} must be a finite numeric mean")
    else:
        try:
            valid = math.isfinite(actual) and math.isclose(
                actual, expected, rel_tol=1e-12, abs_tol=1e-12,
            )
        except (OverflowError, ValueError):
            valid = False
        if not valid:
            errors.append(f"{key} disagrees with selected pilot traces")


def audit_pilot_variant_summary(
    summary: dict,
    traces: dict[tuple[str, str], dict],
    variants: list[str],
    task_ids: list[str],
) -> list[str]:
    """Reconstruct each reported arm's operational means and denominators.

    Cost and per-task paired deltas are independently audited elsewhere.
    An arm not selected for collection has n=0 and null means; it must not be
    represented as a zero-effect measured treatment.
    """
    errors: list[str] = []
    observed_arms = summary.get("variant_summary")
    if not isinstance(observed_arms, dict) or set(observed_arms) != set(_ARMS):
        return ["summary.variant_summary must include exactly the three pilot arms"]

    for arm in _ARMS:
        label = f"summary.variant_summary.{arm}"
        observed = observed_arms[arm]
        if not isinstance(observed, dict):
            errors.append(f"{label} must be an object")
            continue
        arm_traces = []
        if arm in variants:
            for task in task_ids:
                trace = traces.get((arm, task))
                if not isinstance(trace, dict):
                    errors.append(f"{label}: missing selected source cell {task!r}")
                    break
                arm_traces.append((task, trace))
            else:
                pass
            if len(arm_traces) != len(task_ids):
                continue

        try:
            complete = []
            collected = {key: [] for key in _COUNTER_METRICS}
            latencies, verified_scores = [], []
            provider_complete = 0
            for task, trace in arm_traces:
                source = f"{arm}/{task}"
                if type(trace.get("completed")) is not bool:
                    raise ValueError(f"{source}.completed must be a boolean")
                complete.append(1 if trace["completed"] else 0)
                for mean_key, field in _COUNTER_METRICS.items():
                    collected[mean_key].append(_counter(trace, field, source))
                latencies.append(_continuous(trace, "latency_seconds", source))
                checked = _counter(trace, "verified_claim_count", source)
                if checked > 0:
                    verified_scores.append(_continuous(
                        trace, "claim_support_rate", source, upper=1.0,
                    ))
                if trace.get("usage_accounting_status") == "provider_usage_complete":
                    provider_complete += 1

            expected = {
                "n_runs": len(arm_traces),
                "n_completed": sum(complete),
                "completion_rate": _mean(complete),
                "avg_latency_seconds": _mean(latencies),
                "avg_claim_support_rate_verified_only": _mean(verified_scores),
                "verified_runs": len(verified_scores),
                "provider_usage_complete_runs": provider_complete,
            }
            expected.update({
                field: _mean(values) for field, values in collected.items()
            })
        except ValueError as exc:
            errors.append(f"{label}: invalid selected source telemetry: {exc}")
            continue

        for field in _AUDITED_METRICS:
            _match(observed, field, expected[field], label, errors)
    return errors

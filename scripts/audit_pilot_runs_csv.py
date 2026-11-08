"""Independent diagnostic-pilot per-run CSV provenance audit (schema v5).

Reconstruct each exported row from the manifest-selected traces and frozen
pricing. The summary and CSV cannot authenticate each other: both are
downstream products, so every exported field is checked against source data.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

COLUMNS = (
    "variant_id", "task_set_id", "task_id", "run_id", "completed",
    "source_count", "successful_source_count", "failed_source_count",
    "search_call_count", "model_call_count", "prompt_tokens",
    "completion_tokens", "total_tokens", "estimated_cost_usd",
    "cost_accounting_status", "latency_seconds", "report_words",
    "claims_checked", "supported_claim_count",
    "partially_supported_claim_count", "unsupported_claim_count",
    "contradicted_claim_count", "claim_support_rate",
    "usage_accounting_status", "verification_status", "smart_model",
    "fast_model",
)
COUNTERS = {
    "source_count": "source_count",
    "successful_source_count": "successful_source_count",
    "failed_source_count": "failed_source_count",
    "search_call_count": "search_call_count",
    "model_call_count": "model_call_count",
    "prompt_tokens": "prompt_tokens",
    "completion_tokens": "completion_tokens",
    "total_tokens": "total_tokens",
    "report_words": "report_words",
    "claims_checked": "verified_claim_count",
    "supported_claim_count": "supported_claim_count",
    "partially_supported_claim_count": "partially_supported_claim_count",
    "unsupported_claim_count": "unsupported_claim_count",
    "contradicted_claim_count": "contradicted_claim_count",
}
FLOATS = {"latency_seconds", "claim_support_rate", "estimated_cost_usd"}
TEXT = ("usage_accounting_status", "verification_status", "smart_model", "fast_model")


def _source_counter(trace, field):
    value = trace.get(field, 0)
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid source counter {field}")
    return str(value)


def _source_float(trace, field):
    value = trace.get(field, 0.0)
    if type(value) not in (int, float) or value < 0:
        raise ValueError(f"invalid source measurement {field}")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"invalid source measurement {field}") from exc
    if not math.isfinite(value) or (field == "claim_support_rate" and value > 1):
        raise ValueError(f"invalid source measurement {field}")
    return value


def _source_cost(trace, prices):
    buckets = trace.get("provider_usage_by_model", {})
    if not isinstance(buckets, dict):
        raise ValueError("invalid source provider-usage buckets")
    total = 0.0
    any_tokens = False
    for model, counts in buckets.items():
        if type(model) is not str or not model or not isinstance(counts, dict):
            raise ValueError("invalid source provider-usage bucket")
        prompt, completion = counts.get("prompt_tokens"), counts.get("completion_tokens")
        if (type(prompt) is not int or prompt < 0
                or type(completion) is not int or completion < 0):
            raise ValueError("invalid source provider token counters")
        if prompt == completion == 0:
            continue
        any_tokens = True
        rate = prices.get(model)
        if rate is None:
            return None, f"unknown_model_price:{model}"
        if not isinstance(rate, dict):
            raise ValueError("invalid source model rate bucket")
        unit_rates = (rate.get("input"), rate.get("output"))
        for number in unit_rates:
            if (type(number) not in (int, float) or number < 0
                    or not math.isfinite(number)):
                raise ValueError("invalid source model rate")
        total += prompt / 1_000_000 * unit_rates[0]
        total += completion / 1_000_000 * unit_rates[1]
        if not math.isfinite(total):
            raise ValueError("nonfinite source cost")
    if not any_tokens:
        return None, "no_reported_tokens"
    return total, "estimated_from_frozen_uncached_rates"


def _expected_row(arm, task, trace, stem, task_set, prices):
    row = {
        "variant_id": arm, "task_set_id": task_set, "task_id": task,
        "run_id": trace.get("run_id", stem),
        "completed": "True" if trace.get("completed") is True else "False",
    }
    if type(row["run_id"]) is not str or row["run_id"] != stem:
        raise ValueError("invalid source run identity")
    for column, field in COUNTERS.items():
        row[column] = _source_counter(trace, field)
    for column in ("latency_seconds", "claim_support_rate"):
        row[column] = _source_float(trace, column)
    for column in TEXT:
        value = trace.get(column, "")
        if type(value) is not str:
            raise ValueError(f"invalid source string {column}")
        row[column] = value
    row["estimated_cost_usd"], row["cost_accounting_status"] = _source_cost(
        trace, prices
    )
    return row


def _value_matches(actual, expected, column):
    if column in FLOATS:
        if expected is None:
            return actual == ""
        try:
            number = float(actual)
            return math.isfinite(number) and math.isclose(
                number, expected, rel_tol=1e-12, abs_tol=1e-12
            )
        except (TypeError, ValueError, OverflowError):
            return False
    return actual == expected


def audit_pilot_runs_csv(
    csv_path: Path, traces: dict, stems: dict, variants: list,
    task_ids: list, task_set_id: str, pricing_path: Path,
) -> list[str]:
    """Reconcile exactly one complete CSV row per selected experimental cell.

    Earlier summary schemas do not acquire this gate retroactively. This
    checks internal trace-to-export consistency, NOT independent trace custody.
    """
    errors = []
    if csv_path.is_symlink() or not csv_path.is_file():
        return ["missing or symlinked pilot_runs.csv for schema v5"]
    try:
        pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
        prices = pricing["models"]
        if not isinstance(prices, dict):
            raise ValueError("pricing models must be an object")
        expected = {
            (arm, task): _expected_row(
                arm, task, traces[(arm, task)], stems[(arm, task)], task_set_id, prices
            )
            for arm in variants for task in task_ids
        }
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, OverflowError) as exc:
        return [f"pilot_runs.csv source reconciliation unavailable: {exc}"]
    seen = set()
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if reader.fieldnames != list(COLUMNS):
                return ["pilot_runs.csv header must match the frozen per-run column schema"]
            for position, row in enumerate(reader, start=2):
                if position > len(expected) + 1:
                    errors.append("pilot_runs.csv contains extra unselected rows")
                    break
                if None in row or any(row.get(column) is None for column in COLUMNS):
                    errors.append(f"pilot_runs.csv row {position}: malformed column count")
                    continue
                key = (row["variant_id"], row["task_id"])
                if key not in expected:
                    errors.append(f"pilot_runs.csv row {position}: unselected treatment/task cell {key}")
                    continue
                if key in seen:
                    errors.append(f"pilot_runs.csv row {position}: duplicate treatment/task cell {key}")
                    continue
                seen.add(key)
                for column in COLUMNS:
                    if not _value_matches(row[column], expected[key][column], column):
                        errors.append(
                            f"pilot_runs.csv row {position}: {column} disagrees with selected trace"
                        )
        missing = set(expected) - seen
        if missing:
            errors.append(f"pilot_runs.csv missing selected treatment/task cells: {sorted(missing)}")
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        errors.append(f"unreadable or malformed pilot_runs.csv: {exc}")
    return errors

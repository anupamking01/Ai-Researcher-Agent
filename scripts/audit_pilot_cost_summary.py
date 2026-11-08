"""Independent diagnostic-pilot frozen-price and cost-coverage reconciliation.

Read only selected traces and the committed price document; never impute unknown
model prices or treat this internal consistency check as provider bill custody.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

# Immutable byte identity of the original 2026-09-08 pricing document.
# This anchor is deliberately independent of the summary's self-reported hash;
# changing the rate table and recomputing every cost must not pass unnoticed.
FROZEN_PILOT_PRICING_SHA256 = "35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace"


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate frozen-price key {key!r}")
        result[key] = value
    return result


def _no_constant(value):
    raise ValueError(f"nonfinite frozen-price constant {value!r}")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite frozen-price number")
    return result


def audit_pilot_cost_summary(summary, traces, variants, task_ids, pricing_path: Path):
    """Return audit errors for schema-v2 cost fields without modifying evidence."""
    errors = []
    if pricing_path.is_symlink() or not pricing_path.is_file():
        return ["missing or symlinked frozen pilot pricing document"]
    try:
        pricing_bytes = pricing_path.read_bytes()
        pricing = json.loads(
            pricing_bytes.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_no_constant,
            parse_float=_finite_float,
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return [f"invalid frozen pilot pricing document: {exc}"]
    if (not isinstance(pricing, dict)
            or pricing.get("unit") != "per_1m_text_tokens"
            or not isinstance(pricing.get("models"), dict)):
        return ["frozen pilot pricing must contain per-million models mapping"]
    # Schema v4 binds the actual *bytes*, not just a reusable date/currency
    # label or a mutually edited summary digest. Earlier schemas retain their
    # precisely documented, weaker cost-audit scope.
    if summary.get("schema_version") == 4:
        actual_digest = hashlib.sha256(pricing_bytes).hexdigest()
        if actual_digest != FROZEN_PILOT_PRICING_SHA256:
            return errors + [
                "frozen pilot pricing bytes disagree with immutable SHA-256 pin"
            ]
        declared = summary.get("pricing_reference")
        if not isinstance(declared, dict) or declared.get("sha256") != actual_digest:
            errors.append(
                "summary.pricing_reference.sha256 disagrees with frozen pilot pricing bytes"
            )
    reference = summary.get("pricing_reference")
    expected_reference = {
        "file": "experiments/openai_pricing_2026-09-08.json",
        "effective_date": pricing.get("effective_date"),
        "currency": pricing.get("currency"),
        "method": (
            "provider-reported prompt/output tokens multiplied by "
            "frozen uncached text-token rates"
        ),
    }
    if not isinstance(reference, dict) or any(
        reference.get(field) != value for field, value in expected_reference.items()
    ):
        errors.append("summary.pricing_reference disagrees with frozen pilot pricing")

    def match(actual, expected, field):
        if expected is None:
            if actual is not None:
                errors.append(f"{field} must be null for an uncosted pair or arm")
        elif type(expected) is int:
            if type(actual) is not int or actual != expected:
                errors.append(f"{field} disagrees with source cost coverage")
        elif type(actual) not in (int, float):
            errors.append(f"{field} must be a finite numeric cost estimate")
        else:
            try:
                valid = math.isfinite(actual) and math.isclose(
                    actual, expected, rel_tol=1e-12, abs_tol=1e-12
                )
            except (ValueError, OverflowError):
                valid = False
            if not valid:
                errors.append(f"{field} disagrees with source cost accounting")

    def reprice(trace, label):
        buckets = trace.get("provider_usage_by_model")
        if not isinstance(buckets, dict):
            return None, "missing_usage_by_model"
        amount = 0.0
        saw_usage = False
        for model, usage in buckets.items():
            if type(model) is not str or not model or not isinstance(usage, dict):
                raise ValueError(f"{label}: invalid cost model usage bucket")
            prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if (type(prompt) is not int or prompt < 0
                    or type(completion) is not int or completion < 0):
                raise ValueError(f"{label}: invalid model token counters for cost")
            if not prompt and not completion:
                continue
            saw_usage = True
            rate = pricing["models"].get(model)
            if rate is None:
                return None, f"unknown_model_price:{model}"
            if not isinstance(rate, dict):
                raise ValueError(f"{label}: invalid frozen price bucket {model!r}")
            rates = (rate.get("input"), rate.get("output"))
            for value in rates:
                try:
                    valid = type(value) in (int, float) and value >= 0 and math.isfinite(value)
                except (ValueError, OverflowError):
                    valid = False
                if not valid:
                    raise ValueError(f"{label}: invalid frozen uncached rate for {model!r}")
            try:
                amount += prompt / 1_000_000 * rates[0] + completion / 1_000_000 * rates[1]
            except OverflowError as exc:
                raise ValueError(f"{label}: overflowing frozen cost") from exc
            if not math.isfinite(amount):
                raise ValueError(f"{label}: nonfinite frozen cost")
        if not saw_usage:
            return None, "no_reported_tokens"
        return amount, "estimated_from_frozen_uncached_rates"

    costs, statuses = {}, {}
    try:
        for arm in variants:
            for task in task_ids:
                key = (arm, task)
                costs[key], statuses[key] = reprice(traces[key], f"{arm}/{task}")
    except (ValueError, KeyError) as exc:
        return errors + [f"pilot cost source audit failed: {exc}"]

    arm_summary = summary.get("variant_summary", {})
    if not isinstance(arm_summary, dict):
        return errors + ["summary.variant_summary must be an object"]
    for arm in variants:
        label = f"summary.variant_summary.{arm}"
        observed = arm_summary.get(arm)
        if not isinstance(observed, dict):
            errors.append(f"{label} must be an object")
            continue
        present = [costs[(arm, task)] for task in task_ids if costs[(arm, task)] is not None]
        missing = sorted(task for task in task_ids if costs[(arm, task)] is None)
        counts = dict(sorted(Counter(statuses[(arm, task)] for task in task_ids).items()))
        match(observed.get("costed_runs"), len(present), f"{label}.costed_runs")
        match(observed.get("uncosted_runs"), len(missing), f"{label}.uncosted_runs")
        if observed.get("uncosted_task_ids") != missing:
            errors.append(f"{label}.uncosted_task_ids disagrees with source coverage")
        if observed.get("cost_accounting_status_counts") != counts:
            errors.append(f"{label}.cost_accounting_status_counts disagrees with source coverage")
        match(
            observed.get("avg_estimated_cost_usd"),
            math.fsum(present) / len(present) if present else None,
            f"{label}.avg_estimated_cost_usd",
        )

    comparisons = summary.get("paired_operational_differences", {})
    if not isinstance(comparisons, dict):
        return errors + ["summary.paired_operational_differences must be an object"]
    for name, left, right in (
        ("P6_minus_D6", "D6", "P6"), ("P6V_minus_P6", "P6", "P6V")
    ):
        label = f"summary.paired_operational_differences.{name}"
        observed = comparisons.get(name)
        if not isinstance(observed, dict):
            errors.append(f"{label} must be an object")
            continue
        tasks = sorted(task_ids) if left in variants and right in variants else []
        deltas, costed_ids, missing_details = [], [], []
        for task in tasks:
            a, b = costs[(left, task)], costs[(right, task)]
            if a is None or b is None:
                deltas.append(None)
                missing_details.append({
                    "task_id": task,
                    "left_cost_status": "costed" if a is not None else statuses[(left, task)],
                    "right_cost_status": "costed" if b is not None else statuses[(right, task)],
                })
            else:
                deltas.append(b - a)
                costed_ids.append(task)
        match(observed.get("n_costed_pairs"), len(costed_ids), f"{label}.n_costed_pairs")
        match(observed.get("n_uncosted_pairs"), len(missing_details), f"{label}.n_uncosted_pairs")
        if observed.get("costed_pair_task_ids") != costed_ids:
            errors.append(f"{label}.costed_pair_task_ids disagrees with source coverage")
        if observed.get("uncosted_pair_details") != missing_details:
            errors.append(f"{label}.uncosted_pair_details disagrees with source coverage")
        rows = observed.get("pairs")
        if not isinstance(rows, list) or len(rows) != len(deltas):
            errors.append(f"{label}.pairs missing or wrong length for cost reconciliation")
            continue
        for index, (task, delta, row) in enumerate(zip(tasks, deltas, rows)):
            if not isinstance(row, dict) or row.get("task_id") != task:
                errors.append(f"{label}.pairs[{index}].task_id inconsistent with cost source")
                continue
            match(
                row.get("estimated_cost_usd_delta"), delta,
                f"{label}.pairs[{index}].estimated_cost_usd_delta",
            )
        present = [delta for delta in deltas if delta is not None]
        match(
            observed.get("avg_estimated_cost_usd_delta"),
            math.fsum(present) / len(present) if present else None,
            f"{label}.avg_estimated_cost_usd_delta",
        )
    return errors

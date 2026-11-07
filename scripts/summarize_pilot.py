"""Summarize machine-readable D6/P6/P6V pilot traces.

This script is intentionally offline and dependency-free. It does not score
report quality; it summarizes operational metrics and verifier support labels
already present in the run traces. Estimated USD cost is calculated only from
a dated, frozen pricing table committed with the experiment.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
OUTPUT_JSON = REPO_ROOT / "outputs" / "pilot_summary.json"
OUTPUT_CSV = REPO_ROOT / "outputs" / "pilot_runs.csv"
PRICING_FILE = REPO_ROOT / "experiments" / "openai_pricing_2026-09-08.json"
VARIANT_ORDER = ("D6", "P6", "P6V")


def _mean(values):
    values = [value for value in values if value is not None]
    return statistics.mean(values) if values else None


def _load_pricing():
    payload = json.loads(PRICING_FILE.read_text(encoding="utf-8"))
    if payload.get("unit") != "per_1m_text_tokens":
        raise ValueError(f"Unsupported pricing unit in {PRICING_FILE}")
    return payload


def _nonnegative_token_count(value, *, model, field):
    """Fail closed on lossy coercions or negative provider usage counters."""
    if type(value) is not int or value < 0:
        raise ValueError(
            f"provider usage {model!r}.{field} must be a nonnegative integer"
        )
    return value


def _finite_uncached_rate(value, *, model, field):
    if type(value) not in (int, float) or value < 0:
        raise ValueError(
            f"frozen pricing {model!r}.{field} must be finite and nonnegative"
        )
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(
            f"frozen pricing {model!r}.{field} must be finite and nonnegative"
        )
    return value


def _verify_provider_usage_ledger(trace, by_model):
    """Reconcile reported token totals against model-level accounting.

    Only enforce the ledger contract when the detailed model map exists.
    Legacy missing maps remain visibly uncosted, not silently imputed.
    """
    if not isinstance(by_model, dict) or not by_model:
        return
    totals = {"prompt_tokens": 0, "completion_tokens": 0}
    for model, usage in by_model.items():
        if type(model) is not str or not model or not isinstance(usage, dict):
            raise ValueError("invalid provider usage model bucket")
        for field in totals:
            totals[field] += _nonnegative_token_count(
                usage.get(field, 0), model=model, field=field
            )
    totals["total_tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
    for field, expected in totals.items():
        recorded = trace.get(field)
        if type(recorded) is not int or recorded != expected:
            raise ValueError(
                f"provider usage ledger mismatch: trace.{field}={recorded!r} "
                f"but model buckets sum to {expected}"
            )


def _estimate_reported_token_cost(provider_usage_by_model, pricing):
    """Estimate only from intact provider counts and finite frozen rates.

    Unknown model rates retain the historical explicit uncosted status.
    Malformed token counts or price entries are errors, not zero-priced data.
    """
    if not isinstance(provider_usage_by_model, dict):
        return None, "missing_usage_by_model"
    models = pricing.get("models") if isinstance(pricing, dict) else None
    if not isinstance(models, dict):
        raise ValueError("frozen pricing must have a models mapping")

    total_cost = 0.0
    saw_usage = False
    for model, usage in provider_usage_by_model.items():
        if type(model) is not str or not model or not isinstance(usage, dict):
            raise ValueError("invalid provider usage model bucket")
        prompt_tokens = _nonnegative_token_count(
            usage.get("prompt_tokens", 0), model=model, field="prompt_tokens"
        )
        completion_tokens = _nonnegative_token_count(
            usage.get("completion_tokens", 0), model=model, field="completion_tokens"
        )
        if prompt_tokens == 0 and completion_tokens == 0:
            continue
        saw_usage = True
        rate = models.get(model)
        if rate is None:
            return None, f"unknown_model_price:{model}"
        if not isinstance(rate, dict):
            raise ValueError(f"invalid frozen pricing bucket for {model!r}")
        input_rate = _finite_uncached_rate(rate.get("input"), model=model, field="input")
        output_rate = _finite_uncached_rate(rate.get("output"), model=model, field="output")
        try:
            total_cost += (
                prompt_tokens / 1_000_000 * input_rate
                + completion_tokens / 1_000_000 * output_rate
            )
        except OverflowError as exc:
            raise ValueError("nonfinite frozen-price cost estimate") from exc
        if not math.isfinite(total_cost):
            raise ValueError("nonfinite frozen-price cost estimate")

    if not saw_usage:
        return None, "no_reported_tokens"
    return total_cost, "estimated_from_frozen_uncached_rates"

def _load_traces(pricing):
    rows = []
    for variant in VARIANT_ORDER:
        variant_dir = TRACE_ROOT / variant
        if not variant_dir.exists():
            continue
        for path in sorted(variant_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeError, json.JSONDecodeError, OSError) as exc:
                # Skipping a damaged run silently changes which pilot cells are
                # selected for a descriptive comparison. Fail before publication.
                raise ValueError(f"unreadable or malformed pilot trace: {path}") from exc
            if (not isinstance(payload, dict)
                    or not isinstance(payload.get("trace"), dict)
                    or not isinstance(payload.get("experiment"), dict)):
                raise ValueError(f"invalid pilot trace structure: {path}")
            trace, experiment = payload["trace"], payload["experiment"]
            for field in ("variant_id", "task_set_id", "task_id"):
                recorded = trace.get(field)
                declared = experiment.get(field)
                if recorded and declared and recorded != declared:
                    raise ValueError(
                        f"pilot trace/experiment {field} mismatch: {path}"
                    )
            declared_variant = (
                trace.get("variant_id") or experiment.get("variant_id") or variant
            )
            if declared_variant != variant:
                raise ValueError(
                    f"pilot trace variant disagrees with directory {variant}: {path}"
                )

            by_model = trace.get("provider_usage_by_model", {})
            _verify_provider_usage_ledger(trace, by_model)
            estimated_cost, cost_status = _estimate_reported_token_cost(
                by_model, pricing
            )
            rows.append(
                {
                    "variant_id": trace.get("variant_id") or experiment.get("variant_id") or variant,
                    "task_set_id": trace.get("task_set_id") or experiment.get("task_set_id", ""),
                    "task_id": trace.get("task_id") or experiment.get("task_id", ""),
                    "run_id": trace.get("run_id", path.stem),
                    "completed": bool(trace.get("completed", False)),
                    "source_count": int(trace.get("source_count", 0) or 0),
                    "successful_source_count": int(trace.get("successful_source_count", 0) or 0),
                    "failed_source_count": int(trace.get("failed_source_count", 0) or 0),
                    "search_call_count": int(trace.get("search_call_count", 0) or 0),
                    "model_call_count": int(trace.get("model_call_count", 0) or 0),
                    "prompt_tokens": int(trace.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(trace.get("completion_tokens", 0) or 0),
                    "total_tokens": int(trace.get("total_tokens", 0) or 0),
                    "estimated_cost_usd": estimated_cost,
                    "cost_accounting_status": cost_status,
                    "latency_seconds": float(trace.get("latency_seconds", 0.0) or 0.0),
                    "report_words": int(trace.get("report_words", 0) or 0),
                    "claims_checked": int(trace.get("verified_claim_count", 0) or 0),
                    "supported_claim_count": int(trace.get("supported_claim_count", 0) or 0),
                    "partially_supported_claim_count": int(trace.get("partially_supported_claim_count", 0) or 0),
                    "unsupported_claim_count": int(trace.get("unsupported_claim_count", 0) or 0),
                    "contradicted_claim_count": int(trace.get("contradicted_claim_count", 0) or 0),
                    "claim_support_rate": float(trace.get("claim_support_rate", 0.0) or 0.0),
                    "usage_accounting_status": trace.get("usage_accounting_status", ""),
                    "verification_status": trace.get("verification_status", ""),
                    "smart_model": trace.get("smart_model", ""),
                    "fast_model": trace.get("fast_model", ""),
                }
            )
    return rows


def _variant_summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["variant_id"]].append(row)

    summaries = {}
    for variant in VARIANT_ORDER:
        items = grouped.get(variant, [])
        verified = [item for item in items if item["claims_checked"] > 0]
        costed = [item for item in items if item["estimated_cost_usd"] is not None]
        summaries[variant] = {
            "n_runs": len(items),
            "n_completed": sum(1 for item in items if item["completed"]),
            "completion_rate": _mean(1.0 if item["completed"] else 0.0 for item in items),
            "avg_source_attempts": _mean(item["source_count"] for item in items),
            "avg_successful_sources": _mean(item["successful_source_count"] for item in items),
            "avg_failed_sources": _mean(item["failed_source_count"] for item in items),
            "avg_search_calls": _mean(item["search_call_count"] for item in items),
            "avg_model_calls": _mean(item["model_call_count"] for item in items),
            "avg_prompt_tokens": _mean(item["prompt_tokens"] for item in items),
            "avg_completion_tokens": _mean(item["completion_tokens"] for item in items),
            "avg_total_tokens": _mean(item["total_tokens"] for item in items),
            "avg_estimated_cost_usd": _mean(item["estimated_cost_usd"] for item in costed),
            "costed_runs": len(costed),
            "avg_latency_seconds": _mean(item["latency_seconds"] for item in items),
            "avg_report_words": _mean(item["report_words"] for item in items),
            "avg_claim_support_rate_verified_only": _mean(
                item["claim_support_rate"] for item in verified
            ),
            "verified_runs": len(verified),
            "provider_usage_complete_runs": sum(
                1
                for item in items
                if item["usage_accounting_status"] == "provider_usage_complete"
            ),
        }
    return summaries


def _index_pilot_rows(rows):
    """Reject ambiguous pilot selection rather than overwriting a run per cell.

    A pilot summary is diagnostic, but selecting the last row of a duplicated
    (variant, task) cell can silently prefer a retry. Mixed task sets can also
    produce false task-level pairs. Selection must happen explicitly upstream,
    before calling this summarizer; neither success nor score can pick a row.
    """
    by_key = {}
    run_ids = set()
    task_set_id = None
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"pilot row {position} is not a record")
        for field in ("variant_id", "task_set_id", "task_id", "run_id"):
            value = row.get(field)
            if type(value) is not str or not value or value != value.strip():
                raise ValueError(f"pilot row {position} has invalid {field}")
        if row["variant_id"] not in VARIANT_ORDER:
            raise ValueError(f"pilot row {position} has unexpected variant")
        if task_set_id is None:
            task_set_id = row["task_set_id"]
        elif row["task_set_id"] != task_set_id:
            raise ValueError("mixed pilot task_set_id values; refuse cross-study pairing")
        cell = (row["variant_id"], row["task_id"])
        if cell in by_key:
            raise ValueError(
                f"duplicate pilot treatment/task cell {cell}; "
                "do not silently select one attempted run"
            )
        if row["run_id"] in run_ids:
            raise ValueError(
                f"reused pilot run_id {row['run_id']!r}; "
                "independent cells require distinct runs"
            )
        by_key[cell] = row
        run_ids.add(row["run_id"])
    return by_key


def _paired_operational_differences(rows):
    by_key = _index_pilot_rows(rows)
    comparisons = {}
    for left, right, name in (
        ("D6", "P6", "P6_minus_D6"),
        ("P6", "P6V", "P6V_minus_P6"),
    ):
        pairs = []
        task_ids = sorted(
            {task_id for variant, task_id in by_key if variant in {left, right}}
        )
        missing_left_task_ids = []
        missing_right_task_ids = []
        for task_id in task_ids:
            a = by_key.get((left, task_id))
            b = by_key.get((right, task_id))
            if a is None:
                missing_left_task_ids.append(task_id)
            if b is None:
                missing_right_task_ids.append(task_id)
            if a is None or b is None:
                continue
            cost_delta = None
            if a["estimated_cost_usd"] is not None and b["estimated_cost_usd"] is not None:
                cost_delta = b["estimated_cost_usd"] - a["estimated_cost_usd"]
            pairs.append(
                {
                    "task_id": task_id,
                    "total_tokens_delta": b["total_tokens"] - a["total_tokens"],
                    "estimated_cost_usd_delta": cost_delta,
                    "latency_seconds_delta": b["latency_seconds"] - a["latency_seconds"],
                    "model_calls_delta": b["model_call_count"] - a["model_call_count"],
                    "successful_sources_delta": b["successful_source_count"] - a["successful_source_count"],
                }
            )
        comparisons[name] = {
            "n_tasks_union": len(task_ids),
            "n_pairs": len(pairs),
            "missing_left_task_ids": missing_left_task_ids,
            "missing_right_task_ids": missing_right_task_ids,
            "avg_total_tokens_delta": _mean(p["total_tokens_delta"] for p in pairs),
            "avg_estimated_cost_usd_delta": _mean(
                p["estimated_cost_usd_delta"] for p in pairs
            ),
            "avg_latency_seconds_delta": _mean(p["latency_seconds_delta"] for p in pairs),
            "avg_model_calls_delta": _mean(p["model_calls_delta"] for p in pairs),
            "avg_successful_sources_delta": _mean(
                p["successful_sources_delta"] for p in pairs
            ),
            "pairs": pairs,
        }
    return comparisons


def _write_csv(rows):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        OUTPUT_CSV.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    pricing = _load_pricing()
    rows = _load_traces(pricing)
    if not rows:
        raise SystemExit(
            f"No pilot traces found under {TRACE_ROOT}. Run scripts/run_pilot.py first."
        )
    # Check the complete source selection before summaries or output writes.
    _index_pilot_rows(rows)

    payload = {
        "n_trace_files": len(rows),
        "pricing_reference": {
            "file": str(PRICING_FILE.relative_to(REPO_ROOT)),
            "effective_date": pricing.get("effective_date"),
            "currency": pricing.get("currency"),
            "method": "provider-reported prompt/output tokens multiplied by frozen uncached text-token rates",
        },
        "variant_summary": _variant_summary(rows),
        "paired_operational_differences": _paired_operational_differences(rows),
        "limitations": [
            "This summary does not perform blinded human report-quality scoring.",
            "Verifier support rates are available only for verification variants.",
            "Estimated USD cost applies uncached input rates because cached-input tokens are not separately captured by the current usage ledger.",
            "Unknown model IDs are left uncosted rather than assigned an inferred price.",
            "Long-context pricing multipliers, if triggered, require separate review before publication claims.",
        ],
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_csv(rows)

    print(json.dumps(payload["variant_summary"], indent=2, sort_keys=True))
    print(f"pricing={PRICING_FILE}")
    print(f"summary_json={OUTPUT_JSON}")
    print(f"runs_csv={OUTPUT_CSV}")


if __name__ == "__main__":
    main()

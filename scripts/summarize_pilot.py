"""Summarize machine-readable D6/P6/P6V pilot traces.

This script is intentionally offline and dependency-free. It does not score
report quality; it summarizes operational metrics and verifier support labels
already present in the run traces.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
OUTPUT_JSON = REPO_ROOT / "outputs" / "pilot_summary.json"
OUTPUT_CSV = REPO_ROOT / "outputs" / "pilot_runs.csv"
VARIANT_ORDER = ("D6", "P6", "P6V")


def _mean(values):
    values = list(values)
    return statistics.mean(values) if values else None


def _load_traces():
    rows = []
    for variant in VARIANT_ORDER:
        variant_dir = TRACE_ROOT / variant
        if not variant_dir.exists():
            continue
        for path in sorted(variant_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                trace = payload.get("trace", {})
                experiment = payload.get("experiment", {})
            except (json.JSONDecodeError, OSError):
                continue

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


def _paired_operational_differences(rows):
    by_key = {(r["variant_id"], r["task_id"]): r for r in rows if r["task_id"]}
    comparisons = {}
    for left, right, name in (
        ("D6", "P6", "P6_minus_D6"),
        ("P6", "P6V", "P6V_minus_P6"),
    ):
        pairs = []
        task_ids = sorted(
            {task_id for variant, task_id in by_key if variant in {left, right}}
        )
        for task_id in task_ids:
            a = by_key.get((left, task_id))
            b = by_key.get((right, task_id))
            if not a or not b:
                continue
            pairs.append(
                {
                    "task_id": task_id,
                    "total_tokens_delta": b["total_tokens"] - a["total_tokens"],
                    "latency_seconds_delta": b["latency_seconds"] - a["latency_seconds"],
                    "model_calls_delta": b["model_call_count"] - a["model_call_count"],
                    "successful_sources_delta": b["successful_source_count"] - a["successful_source_count"],
                }
            )
        comparisons[name] = {
            "n_pairs": len(pairs),
            "avg_total_tokens_delta": _mean(p["total_tokens_delta"] for p in pairs),
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
    rows = _load_traces()
    if not rows:
        raise SystemExit(
            f"No pilot traces found under {TRACE_ROOT}. Run scripts/run_pilot.py first."
        )

    payload = {
        "n_trace_files": len(rows),
        "variant_summary": _variant_summary(rows),
        "paired_operational_differences": _paired_operational_differences(rows),
        "limitations": [
            "This summary does not perform blinded human report-quality scoring.",
            "Verifier support rates are available only for verification variants.",
            "USD cost is intentionally omitted until a model-pricing table is frozen for the experiment date.",
        ],
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_csv(rows)

    print(json.dumps(payload["variant_summary"], indent=2, sort_keys=True))
    print(f"summary_json={OUTPUT_JSON}")
    print(f"runs_csv={OUTPUT_CSV}")


if __name__ == "__main__":
    main()

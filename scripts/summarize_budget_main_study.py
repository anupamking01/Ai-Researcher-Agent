"""Offline summary for the low-cost main study.

Combines treatment traces with the common post-hoc support evaluator. No model
calls are made here. The summary is descriptive; inferential analysis and human
quality scoring remain separate research steps.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
EVAL_ROOT = REPO_ROOT / "outputs" / "posthoc_evaluations"
PRICING_FILE = REPO_ROOT / "experiments" / "openai_pricing_2026-09-08.json"
OUT_JSON = REPO_ROOT / "outputs" / "main_study_summary.json"
OUT_CSV = REPO_ROOT / "outputs" / "main_study_runs.csv"
VARIANTS = ("D3", "D6", "P6", "P6V")


def _mean(values):
    values = list(values)
    return statistics.mean(values) if values else None


def main() -> int:
    from scripts.summarize_pilot import _estimate_reported_token_cost

    pricing = json.loads(PRICING_FILE.read_text(encoding="utf-8"))
    eval_by_key = {}
    for path in EVAL_ROOT.glob("*/*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        eval_by_key[(row["variant_id"], row["task_id"])] = row

    rows = []
    for variant in VARIANTS:
        for path in sorted((TRACE_ROOT / variant).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            trace = payload.get("trace", {})
            experiment = payload.get("experiment", {})
            task_id = str(trace.get("task_id") or experiment.get("task_id") or "")
            cost, status = _estimate_reported_token_cost(
                trace.get("provider_usage_by_model", {}), pricing
            )
            evaluator = eval_by_key.get((variant, task_id), {})
            rows.append(
                {
                    "variant_id": variant,
                    "task_id": task_id,
                    "completed": bool(trace.get("completed")),
                    "source_budget": int(trace.get("source_budget", 0) or 0),
                    "successful_sources": int(trace.get("successful_source_count", 0) or 0),
                    "failed_sources": int(trace.get("failed_source_count", 0) or 0),
                    "search_calls": int(trace.get("search_call_count", 0) or 0),
                    "model_calls": int(trace.get("model_call_count", 0) or 0),
                    "total_tokens": int(trace.get("total_tokens", 0) or 0),
                    "treatment_cost_usd": cost,
                    "cost_status": status,
                    "latency_seconds": float(trace.get("latency_seconds", 0.0) or 0.0),
                    "report_words": int(trace.get("report_words", 0) or 0),
                    "posthoc_claims_checked": int(evaluator.get("claims_checked", 0) or 0),
                    "posthoc_strict_support_rate": evaluator.get("strict_support_rate"),
                    "posthoc_evaluator_cost_usd": evaluator.get("estimated_cost_usd"),
                }
            )

    if not rows:
        raise SystemExit("No main-study traces found")

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["variant_id"]].append(row)

    variant_summary = {}
    for variant in VARIANTS:
        items = grouped[variant]
        variant_summary[variant] = {
            "n": len(items),
            "completed": sum(1 for r in items if r["completed"]),
            "avg_successful_sources": _mean(r["successful_sources"] for r in items),
            "avg_model_calls": _mean(r["model_calls"] for r in items),
            "avg_total_tokens": _mean(r["total_tokens"] for r in items),
            "avg_treatment_cost_usd": _mean(r["treatment_cost_usd"] for r in items if r["treatment_cost_usd"] is not None),
            "avg_latency_seconds": _mean(r["latency_seconds"] for r in items),
            "avg_report_words": _mean(r["report_words"] for r in items),
            "avg_posthoc_strict_support_rate": _mean(
                r["posthoc_strict_support_rate"] for r in items
                if r["posthoc_strict_support_rate"] is not None
            ),
            "posthoc_evaluated_runs": sum(1 for r in items if r["posthoc_claims_checked"] > 0),
        }

    by_key = {(r["variant_id"], r["task_id"]): r for r in rows}
    comparisons = {}
    for left, right, name in (
        ("D3", "D6", "D6_minus_D3_retrieval_depth"),
        ("D6", "P6", "P6_minus_D6_planning"),
        ("P6", "P6V", "P6V_minus_P6_verification"),
    ):
        pairs = []
        task_ids = sorted({r["task_id"] for r in rows})
        for task_id in task_ids:
            a = by_key.get((left, task_id))
            b = by_key.get((right, task_id))
            if not a or not b:
                continue
            support_delta = None
            if a["posthoc_strict_support_rate"] is not None and b["posthoc_strict_support_rate"] is not None:
                support_delta = b["posthoc_strict_support_rate"] - a["posthoc_strict_support_rate"]
            pairs.append(
                {
                    "task_id": task_id,
                    "successful_sources_delta": b["successful_sources"] - a["successful_sources"],
                    "total_tokens_delta": b["total_tokens"] - a["total_tokens"],
                    "treatment_cost_usd_delta": (
                        b["treatment_cost_usd"] - a["treatment_cost_usd"]
                        if a["treatment_cost_usd"] is not None and b["treatment_cost_usd"] is not None else None
                    ),
                    "latency_seconds_delta": b["latency_seconds"] - a["latency_seconds"],
                    "posthoc_strict_support_rate_delta": support_delta,
                }
            )
        comparisons[name] = {
            "n_pairs": len(pairs),
            "avg_successful_sources_delta": _mean(p["successful_sources_delta"] for p in pairs),
            "avg_total_tokens_delta": _mean(p["total_tokens_delta"] for p in pairs),
            "avg_treatment_cost_usd_delta": _mean(
                p["treatment_cost_usd_delta"] for p in pairs if p["treatment_cost_usd_delta"] is not None
            ),
            "avg_latency_seconds_delta": _mean(p["latency_seconds_delta"] for p in pairs),
            "avg_posthoc_strict_support_rate_delta": _mean(
                p["posthoc_strict_support_rate_delta"] for p in pairs if p["posthoc_strict_support_rate_delta"] is not None
            ),
            "pairs": pairs,
        }

    treatment_cost = sum(float(r["treatment_cost_usd"] or 0.0) for r in rows)
    evaluator_cost = sum(float(r["posthoc_evaluator_cost_usd"] or 0.0) for r in rows)
    summary = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "n_runs": len(rows),
        "n_posthoc_evaluations": sum(1 for r in rows if r["posthoc_claims_checked"] > 0),
        "estimated_treatment_cost_usd": treatment_cost,
        "estimated_common_evaluator_cost_usd": evaluator_cost,
        "estimated_total_cost_usd": treatment_cost + evaluator_cost,
        "variant_summary": variant_summary,
        "paired_descriptive_comparisons": comparisons,
        "limitations": [
            "This 10-task original live-web set is not an established public benchmark.",
            "The common post-hoc support evaluator is automated and should be supplemented by blinded human evaluation.",
            "Costs use frozen uncached input rates because cached tokens are not separately tracked.",
            "Live-web source availability can vary across treatment runs.",
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    fieldnames = list(rows[0].keys())
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

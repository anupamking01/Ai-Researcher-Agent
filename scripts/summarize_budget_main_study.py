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


def _load_bound_inputs(pricing: dict) -> tuple[list[dict], dict[tuple[str, str], dict]]:
    from scripts.evaluate_posthoc_support import (
        _load_json,
        _prepare_evaluator_input,
        _validate_cached_evaluation,
    )
    from scripts.run_budget_main_study import _validated_trace_cost

    traces = []
    trace_by_key = {}
    for variant in VARIANTS:
        for path in sorted((TRACE_ROOT / variant).glob("*.json")):
            payload = _load_json(path)
            experiment = payload.get("experiment")
            trace = payload.get("trace")
            if not isinstance(experiment, dict) or not isinstance(trace, dict):
                raise SystemExit(
                    f"Treatment trace must contain object metadata: {path}"
                )
            if (
                experiment.get("variant_id") != variant
                or trace.get("variant_id") != variant
            ):
                raise SystemExit(
                    f"Treatment trace {path} variant_id does not match trace path"
                )
            experiment_task = experiment.get("task_id")
            task_id = trace.get("task_id")
            if (
                not isinstance(task_id, str)
                or not task_id.strip()
                or experiment_task != task_id
            ):
                raise SystemExit(
                    f"Treatment trace {path} task_id differs between experiment and trace"
                )
            run_id = trace.get("run_id")
            if not isinstance(run_id, str) or run_id != path.stem:
                raise SystemExit(
                    f"Treatment trace {path} run_id does not match trace filename"
                )
            key = (variant, task_id)
            if key in trace_by_key:
                raise SystemExit(f"duplicate treatment cell: {variant}/{task_id}")
            treatment_cost = _validated_trace_cost(
                payload,
                path=path,
                pricing=pricing,
            )
            record = {
                "variant": variant,
                "task_id": task_id,
                "run_id": run_id,
                "trace": trace,
                "treatment_cost_usd": treatment_cost,
            }
            traces.append(record)
            trace_by_key[key] = record

    eval_by_key = {}
    evaluator_model = None
    evaluator_temperature = None
    for path in sorted(EVAL_ROOT.glob("*/*.json")):
        row = _load_json(path)
        path_variant = path.parent.name
        path_task = path.stem
        if row.get("variant_id") != path_variant:
            raise SystemExit(
                f"Evaluator cache {path} variant_id does not match cache path"
            )
        if row.get("task_id") != path_task:
            raise SystemExit(
                f"Evaluator cache {path} task_id does not match cache path"
            )
        key = (path_variant, path_task)
        trace_record = trace_by_key.get(key)
        if trace_record is None:
            raise SystemExit(
                f"Evaluator cache {path} has no matching treatment trace"
            )
        if row.get("run_id") != trace_record["run_id"]:
            raise SystemExit(
                f"Evaluator cache {path} run_id does not match treatment trace"
            )
        if key in eval_by_key:
            raise SystemExit(f"Duplicate evaluator cell: {path_variant}/{path_task}")
        if evaluator_model is None:
            evaluator_model = row.get("evaluator_model")
            evaluator_temperature = row.get("temperature")
        successful_sources = int(
            trace_record["trace"].get("successful_source_count", 0) or 0
        )
        expected_evidence_status = (
            "zero_successful_sources"
            if successful_sources == 0
            else "retrieved_evidence"
        )
        expected_input_fingerprints = None
        if row.get("schema_version") == 2:
            prepared = _prepare_evaluator_input(
                trace_record["trace"],
                path_variant,
                path_task,
                trace_record["run_id"],
                root=REPO_ROOT,
            )
            if prepared["evidence_status"] != expected_evidence_status:
                raise SystemExit(
                    f"Evaluator cache {path} evidence status disagrees with inputs"
                )
            expected_input_fingerprints = prepared["input_fingerprints"]
        eval_by_key[key] = _validate_cached_evaluation(
            row,
            path=path,
            expected_variant=path_variant,
            expected_task_id=path_task,
            expected_run_id=trace_record["run_id"],
            expected_evaluator_model=evaluator_model,
            expected_temperature=evaluator_temperature,
            expected_evidence_status=expected_evidence_status,
            pricing=pricing,
            expected_input_fingerprints=expected_input_fingerprints,
        )

    for record in traces:
        key = (record["variant"], record["task_id"])
        if record["trace"].get("completed") is True and key not in eval_by_key:
            raise SystemExit(
                "missing evaluator cache for completed trace: "
                f"{record['variant']}/{record['task_id']}"
            )
    return traces, eval_by_key


def main() -> int:
    from scripts.run_budget_main_study import _load_pricing

    pricing, pricing_snapshot = _load_pricing(PRICING_FILE)
    traces, eval_by_key = _load_bound_inputs(pricing)

    rows = []
    for record in traces:
        variant = record["variant"]
        task_id = record["task_id"]
        trace = record["trace"]
        cost = record["treatment_cost_usd"]
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
                "cost_status": "estimated_from_frozen_uncached_rates",
                "pricing_file": pricing_snapshot["path"],
                "pricing_file_size_bytes": pricing_snapshot["size_bytes"],
                "pricing_file_sha256": pricing_snapshot["sha256"],
                "pricing_unit": pricing["unit"],
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
        "pricing_reference": {
            "file": pricing_snapshot["path"],
            "size_bytes": pricing_snapshot["size_bytes"],
            "sha256": pricing_snapshot["sha256"],
            "effective_date": pricing.get("effective_date"),
            "currency": pricing.get("currency"),
            "unit": pricing["unit"],
            "source": pricing.get("source"),
            "method": (
                "provider-reported prompt/output tokens multiplied by frozen "
                "uncached text-token rates"
            ),
        },
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

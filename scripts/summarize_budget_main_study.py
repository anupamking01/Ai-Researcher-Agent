"""Offline summary for the low-cost main study.

Combines treatment traces with the common post-hoc support evaluator. No model
calls are made here. The summary is descriptive; inferential analysis and human
quality scoring remain separate research steps.
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
from io import StringIO
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.evaluate_posthoc_support import (
    FROZEN_EVALUATOR_MODEL,
    FROZEN_EVALUATOR_TEMPERATURE,
    _verify_aggregate_outputs,
    _load_json,
    _read_regular_bytes,
)

TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
EVAL_ROOT = REPO_ROOT / "outputs" / "posthoc_evaluations"
PRICING_FILE = REPO_ROOT / "experiments" / "openai_pricing_2026-09-08.json"
TASK_FILE = REPO_ROOT / "experiments" / "main_budget_tasks.json"
OUT_JSON = REPO_ROOT / "outputs" / "main_study_summary.json"
OUT_CSV = REPO_ROOT / "outputs" / "main_study_runs.csv"
VARIANTS = ("D3", "D6", "P6", "P6V")


def _mean(values):
    values = list(values)
    return statistics.mean(values) if values else None


def _verify_main_study_summary_pair(summary_path: Path, csv_path: Path) -> None:
    """Replay the descriptive JSON-to-CSV generation binding from retained bytes.

    This checks a completed local pair, not atomic publication or independent
    authentication of original treatment/evaluator sources.
    """
    summary = _load_json(summary_path)
    fingerprint = summary.get("main_study_runs_sha256")
    byte_size = summary.get("main_study_runs_size_bytes")
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(char not in "0123456789abcdef" for char in fingerprint)
        or type(byte_size) is not int
        or byte_size < 0
    ):
        raise SystemExit(
            "Main-study descriptive summary lacks a valid CSV generation fingerprint"
        )
    csv_bytes = _read_regular_bytes(
        csv_path, label="main-study descriptive CSV", max_bytes=8 * 1024 * 1024
    )
    if len(csv_bytes) != byte_size or hashlib.sha256(csv_bytes).hexdigest() != fingerprint:
        raise SystemExit(
            "Main-study descriptive summary/CSV generation mismatch; "
            "preserve both outputs for provenance review"
        )


def _publish_main_study_summary_pair(summary: dict, csv_bytes: bytes) -> None:
    """Refuse to replace retained descriptive evidence with a new generation.

    If a complete pair already exists, require a valid digest and byte-for-byte
    agreement with this run. Identical replay is read-only. Never silently
    overwrite a different, partial, or linked pair, even for a local analysis.
    This does not make first-time two-file publication atomic.
    """
    json_bytes = json.dumps(summary, indent=2, sort_keys=True).encode("utf-8")

    def present(path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise SystemExit(
                f"Cannot inspect retained descriptive output {path}: {exc}"
            ) from exc
        return True

    has_json = present(OUT_JSON)
    has_csv = present(OUT_CSV)
    if has_json != has_csv:
        raise SystemExit(
            "Refusing to replace incomplete prior main-study descriptive "
            "output pair; preserve retained evidence for provenance review"
        )
    if has_json:
        _verify_main_study_summary_pair(OUT_JSON, OUT_CSV)
        prior_json = _read_regular_bytes(
            OUT_JSON, label="retained main-study descriptive JSON",
            max_bytes=8 * 1024 * 1024,
        )
        prior_csv = _read_regular_bytes(
            OUT_CSV, label="retained main-study descriptive CSV",
            max_bytes=8 * 1024 * 1024,
        )
        if prior_json != json_bytes or prior_csv != csv_bytes:
            raise SystemExit(
                "Refusing to overwrite retained main-study descriptive outputs "
                "with a different generation; archive and review the earlier "
                "pair before a new noncanonical summary"
            )
        return

    # Exclusive creation refuses a pre-existing file or symlink even if it
    # appears after the presence check. A crash between files leaves an
    # incomplete pair that the next run refuses to overwrite.
    try:
        with OUT_CSV.open("xb") as handle:
            handle.write(csv_bytes)
        with OUT_JSON.open("xb") as handle:
            handle.write(json_bytes)
    except OSError as exc:
        raise SystemExit(
            "Cannot exclusively publish main-study descriptive output pair; "
            "preserve any retained artifacts for provenance review"
        ) from exc
    _verify_main_study_summary_pair(OUT_JSON, OUT_CSV)


def _verify_optional_posthoc_aggregate_pair(summary_path: Path, csv_path: Path) -> None:
    """Refuse partial upstream aggregate evidence before publishing a summary.

    The aggregate is optional for a local descriptive run, but either both
    outputs are absent or both must be verifiably bound. lstat detects dangling
    symlinks that Path.exists() silently treats as missing.
    """
    def present(path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise SystemExit(
                f"Cannot inspect optional post-hoc aggregate path {path}: {exc}"
            ) from exc
        return True

    has_summary = present(summary_path)
    has_csv = present(csv_path)
    if has_summary != has_csv:
        raise SystemExit(
            "Incomplete post-hoc aggregate summary/CSV pair; preserve retained "
            "evidence for provenance review instead of publishing a description"
        )
    if has_summary:
        _verify_aggregate_outputs(summary_path, csv_path)


def _load_bound_inputs(pricing: dict) -> tuple[list[dict], dict[tuple[str, str], dict]]:
    from scripts.evaluate_posthoc_support import (
        _load_frozen_task_contract,
        _load_json,
        _prepare_evaluator_input,
        _validate_trace_task_contract,
        _validate_cached_evaluation,
        _inventory_evaluator_cache_tree,
        _inventory_evaluator_treatment_trace_tree,
    )
    from scripts.run_budget_main_study import _validated_trace_cost

    task_set_id, expected_questions = _load_frozen_task_contract(TASK_FILE)
    # Select the entire observed trace inventory, not a globbed subset that
    # silently drops additional attempts or renamed source evidence.
    trace_inventory = _inventory_evaluator_treatment_trace_tree(
        TRACE_ROOT, variants=VARIANTS
    )
    traces = []
    trace_by_key = {}
    run_id_owner = {}
    for variant in VARIANTS:
        for path in trace_inventory[variant]:
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
            prior_cell = run_id_owner.get(run_id)
            if prior_cell is not None:
                raise SystemExit(
                    "Repeated treatment run_id across distinct cells: "
                    f"{run_id} ({prior_cell[0]}/{prior_cell[1]} and "
                    f"{variant}/{task_id}); shared report provenance is ambiguous"
                )
            run_id_owner[run_id] = key
            treatment_cost = _validated_trace_cost(
                payload,
                path=path,
                pricing=pricing,
            )
            _validate_trace_task_contract(
                payload,
                path=path,
                expected_task_set_id=task_set_id,
                expected_questions=expected_questions,
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

    # A complete cache inventory is required even for locally generated
    # descriptive summaries; ignored cache files can hide selective measurement.
    cache_inventory = _inventory_evaluator_cache_tree(
        EVAL_ROOT, variants=VARIANTS
    )
    eval_by_key = {}
    for path in sorted(cache_inventory):
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
            expected_evaluator_model=FROZEN_EVALUATOR_MODEL,
            expected_temperature=FROZEN_EVALUATOR_TEMPERATURE,
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

    _verify_optional_posthoc_aggregate_pair(
        REPO_ROOT / "outputs" / "posthoc_support_summary.json",
        REPO_ROOT / "outputs" / "posthoc_support_runs.csv",
    )

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
    # Serialize the run table exactly once and bind its physical UTF-8 bytes to
    # the final JSON. Publish the CSV first so a pre-existing newer summary
    # cannot appear consistent with a partially written new CSV.
    csv_buffer = StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    if len(csv_bytes) > 8 * 1024 * 1024:
        raise SystemExit("Main-study descriptive CSV exceeds the 8 MiB output bound")
    summary["main_study_runs_sha256"] = hashlib.sha256(csv_bytes).hexdigest()
    summary["main_study_runs_size_bytes"] = len(csv_bytes)
    _publish_main_study_summary_pair(summary, csv_bytes)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

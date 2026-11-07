"""Strict integrity checks for a completed live research pilot.

GitHub Actions can be green even when an experiment catches and records an
internal failure. This validator converts those research-validity conditions
into CI assertions so a run is only green when its artifacts are usable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_pilot(output_root: Path = DEFAULT_OUTPUT_ROOT) -> list[str]:
    errors: list[str] = []
    manifest_path = output_root / "pilot_manifest.json"
    progress_path = output_root / "pilot_progress.json"
    summary_path = output_root / "pilot_summary.json"

    for required in (manifest_path, progress_path, summary_path):
        if not required.is_file():
            errors.append(f"missing required artifact: {required.name}")
    if errors:
        return errors

    manifest = _load_json(manifest_path)
    progress = _load_json(progress_path)
    summary = _load_json(summary_path)

    variants = [str(value) for value in manifest.get("variants", [])]
    task_ids = [str(value) for value in manifest.get("task_ids", [])]
    expected_pairs = {(variant, task_id) for variant in variants for task_id in task_ids}
    expected_count = len(expected_pairs)

    if expected_count <= 0:
        errors.append("manifest defines no expected experiment runs")
        return errors

    if progress.get("total_expected_runs") != expected_count:
        errors.append(
            "progress total_expected_runs does not match manifest: "
            f"{progress.get('total_expected_runs')} != {expected_count}"
        )
    if progress.get("attempted_runs") != expected_count:
        errors.append(
            f"attempted_runs={progress.get('attempted_runs')} expected={expected_count}"
        )
    if progress.get("completed_runs") != expected_count:
        errors.append(
            f"completed_runs={progress.get('completed_runs')} expected={expected_count}"
        )
    if progress.get("failed_runs", 0) != 0:
        errors.append(f"failed_runs={progress.get('failed_runs')}")
    if progress.get("timeout_runs", 0) != 0:
        errors.append(f"timeout_runs={progress.get('timeout_runs')}")

    trace_files = sorted((output_root / "experiment_traces").glob("*/*.json"))
    if len(trace_files) != expected_count:
        errors.append(
            f"trace_count={len(trace_files)} expected={expected_count}"
        )

    seen_pairs: set[tuple[str, str]] = set()
    for trace_file in trace_files:
        payload = _load_json(trace_file)
        experiment = payload.get("experiment", {})
        trace = payload.get("trace", {})
        variant = str(experiment.get("variant_id") or trace.get("variant_id") or "")
        task_id = str(experiment.get("task_id") or trace.get("task_id") or "")
        pair = (variant, task_id)
        label = f"{variant}/{task_id or trace_file.name}"

        if pair not in expected_pairs:
            errors.append(f"unexpected trace pair: {pair}")
        if pair in seen_pairs:
            errors.append(f"duplicate trace pair: {pair}")
        seen_pairs.add(pair)

        if trace.get("completed") is not True:
            errors.append(f"{label}: completed is not true")

        source_budget = int(trace.get("source_budget", experiment.get("source_budget", 0)) or 0)
        source_count = int(trace.get("source_count", 0) or 0)
        success_count = int(trace.get("successful_source_count", 0) or 0)
        failed_count = int(trace.get("failed_source_count", 0) or 0)
        scheduled_urls = trace.get("scheduled_urls", []) or []
        successful_urls = trace.get("successful_urls", []) or []
        failed_urls = trace.get("failed_urls", []) or []

        if source_count != source_budget:
            errors.append(
                f"{label}: source_count={source_count} does not spend source_budget={source_budget}"
            )
        if success_count < 1:
            errors.append(f"{label}: no successfully processed evidence sources")
        if len(scheduled_urls) != source_count:
            errors.append(
                f"{label}: scheduled_urls={len(scheduled_urls)} source_count={source_count}"
            )
        if len(successful_urls) != success_count:
            errors.append(
                f"{label}: successful_urls={len(successful_urls)} successful_source_count={success_count}"
            )
        if len(failed_urls) != failed_count:
            errors.append(
                f"{label}: failed_urls={len(failed_urls)} failed_source_count={failed_count}"
            )
        if success_count + failed_count != source_count:
            errors.append(
                f"{label}: success+failure={success_count + failed_count} source_count={source_count}"
            )

        planning_mode = trace.get("planning_mode")
        expected_queries = 1 if planning_mode == "direct" else 4
        if int(trace.get("query_count", 0) or 0) != expected_queries:
            errors.append(
                f"{label}: query_count={trace.get('query_count')} expected={expected_queries}"
            )
        if int(trace.get("search_call_count", 0) or 0) != expected_queries:
            errors.append(
                f"{label}: search_call_count={trace.get('search_call_count')} expected={expected_queries}"
            )

        if int(trace.get("research_context_words", 0) or 0) <= 0:
            errors.append(f"{label}: research_context_words is zero")
        if int(trace.get("report_words", 0) or 0) <= 0:
            errors.append(f"{label}: report_words is zero")
        if int(trace.get("model_call_count", 0) or 0) <= 0:
            errors.append(f"{label}: model_call_count is zero")
        if int(trace.get("total_tokens", 0) or 0) <= 0:
            errors.append(f"{label}: provider total_tokens is zero")
        if trace.get("usage_accounting_status") != "provider_usage_complete":
            errors.append(
                f"{label}: usage_accounting_status={trace.get('usage_accounting_status')}"
            )

        if trace.get("smart_model") != manifest.get("smart_model"):
            errors.append(f"{label}: smart model differs from manifest")
        if trace.get("fast_model") != manifest.get("fast_model"):
            errors.append(f"{label}: fast model differs from manifest")
        if float(trace.get("temperature", -999)) != float(manifest.get("temperature", -998)):
            errors.append(f"{label}: temperature differs from manifest")

        verification_mode = trace.get("verification_mode")
        if verification_mode == "verify":
            if trace.get("verification_status") != "ok":
                errors.append(
                    f"{label}: verification_status={trace.get('verification_status')}"
                )
            if int(trace.get("verified_claim_count", 0) or 0) <= 0:
                errors.append(f"{label}: verifier checked zero claims")
        elif trace.get("verification_status") != "not_requested":
            errors.append(
                f"{label}: unexpected verification_status={trace.get('verification_status')}"
            )

    missing_pairs = expected_pairs - seen_pairs
    if missing_pairs:
        errors.append(f"missing trace pairs: {sorted(missing_pairs)}")

    if int(summary.get("n_trace_files", -1)) != expected_count:
        errors.append(
            f"summary n_trace_files={summary.get('n_trace_files')} expected={expected_count}"
        )
    variant_summary = summary.get("variant_summary", {})
    for variant in variants:
        stats = variant_summary.get(variant)
        if not isinstance(stats, dict):
            errors.append(f"summary missing variant {variant}")
            continue
        if int(stats.get("n_runs", -1)) != len(task_ids):
            errors.append(
                f"summary {variant}.n_runs={stats.get('n_runs')} expected={len(task_ids)}"
            )
        if int(stats.get("n_completed", -1)) != len(task_ids):
            errors.append(
                f"summary {variant}.n_completed={stats.get('n_completed')} expected={len(task_ids)}"
            )

    return errors


def main() -> int:
    errors = validate_pilot()
    if errors:
        print("PILOT ARTIFACT VALIDATION: FAIL", flush=True)
        for error in errors:
            print(f" - {error}", flush=True)
        return 1
    print("PILOT ARTIFACT VALIDATION: PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

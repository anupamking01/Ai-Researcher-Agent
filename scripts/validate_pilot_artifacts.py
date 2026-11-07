"""Strict integrity checks for a completed live research pilot.

GitHub Actions can be green even when an experiment catches and records an
internal failure. This validator converts those research-validity conditions
into CI assertions so a run is only green when its artifacts are usable.
"""

from __future__ import annotations

from collections import Counter
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_url_list(
    trace: dict, name: str, label: str, errors: list[str]
) -> list[str] | None:
    """Validate source identity before comparing per-stage retrieval accounting.

    Strings are not URL lists, and padding/empty entries make exact source
    matching ambiguous. Do not normalize away differences after collection.
    """
    values = trace.get(name)
    if not isinstance(values, list) or any(
        type(url) is not str or not url or url != url.strip()
        for url in values
    ):
        errors.append(
            f"{label}: {name} must be a list of nonempty, unpadded URL strings"
        )
        return None
    return values


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

    # Do not let set construction silently collapse a repeated treatment or
    # task ID into a plausible-looking completed experimental matrix.
    variants = manifest.get("variants")
    task_ids = manifest.get("task_ids")
    for name, values in (("variants", variants), ("task_ids", task_ids)):
        if not isinstance(values, list) or not values:
            errors.append(f"manifest {name} must be a nonempty list")
            continue
        if any(type(value) is not str or not value or value != value.strip() for value in values):
            errors.append(f"manifest {name} has invalid identifiers")
        if all(type(value) is str for value in values) and len(set(values)) != len(values):
            errors.append(f"manifest {name} contains duplicates")
    if isinstance(variants, list) and any(
        type(value) is not str or value not in ("D6", "P6", "P6V") for value in variants
    ):
        errors.append("manifest variants contains unsupported treatment")
    task_set_id = manifest.get("task_set_id")
    if type(task_set_id) is not str or not task_set_id or task_set_id != task_set_id.strip():
        errors.append("manifest task_set_id is invalid")
    if errors:
        return errors
    for name, expected in (
        ("variants", variants), ("task_ids", task_ids), ("task_set_id", task_set_id)
    ):
        if progress.get(name) != expected:
            errors.append(f"progress {name} differs from manifest")
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
        if not isinstance(experiment, dict) or not isinstance(trace, dict):
            errors.append(f"invalid pilot trace identity structure: {trace_file.name}")
            continue
        variant = experiment.get("variant_id") or trace.get("variant_id") or ""
        task_id = experiment.get("task_id") or trace.get("task_id") or ""
        pair = (variant, task_id)
        label = f"{variant}/{task_id or trace_file.name}"

        # The runner records both its declared cell and its execution trace.
        # Either may be missing in legacy traces, but supplied identities may
        # never disagree with each other or with the manifest/directory.
        for name, expected in (
            ("variant_id", variant),
            ("task_id", task_id),
            ("task_set_id", task_set_id),
        ):
            for source_name, source in (("experiment", experiment), ("trace", trace)):
                recorded = source.get(name)
                if recorded is not None and recorded != expected:
                    errors.append(
                        f"{label}: {source_name}.{name} disagrees with expected {expected!r}"
                    )
        if trace_file.parent.name != variant:
            errors.append(
                f"{label}: trace directory {trace_file.parent.name!r} disagrees with variant"
            )
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
        scheduled_urls = _source_url_list(trace, "scheduled_urls", label, errors)
        successful_urls = _source_url_list(trace, "successful_urls", label, errors)
        failed_urls = _source_url_list(trace, "failed_urls", label, errors)

        # Each scheduled browse is an independent URL-budget unit. Counts and
        # list lengths alone cannot detect reused URLs or an unrelated URL
        # substituted into successful/failed evidence bookkeeping.
        if scheduled_urls is not None and len(set(scheduled_urls)) != len(scheduled_urls):
            errors.append(f"{label}: duplicate scheduled source URL")
        if all(urls is not None for urls in (
            scheduled_urls, successful_urls, failed_urls
        )):
            if Counter(scheduled_urls) != (
                Counter(successful_urls) + Counter(failed_urls)
            ):
                errors.append(
                    f"{label}: success/failure URLs do not partition scheduled source URLs"
                )

        if source_count != source_budget:
            errors.append(
                f"{label}: source_count={source_count} does not spend source_budget={source_budget}"
            )
        if success_count < 1:
            errors.append(f"{label}: no successfully processed evidence sources")
        if scheduled_urls is not None and len(scheduled_urls) != source_count:
            errors.append(
                f"{label}: scheduled_urls={len(scheduled_urls)} source_count={source_count}"
            )
        if successful_urls is not None and len(successful_urls) != success_count:
            errors.append(
                f"{label}: successful_urls={len(successful_urls)} successful_source_count={success_count}"
            )
        if failed_urls is not None and len(failed_urls) != failed_count:
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

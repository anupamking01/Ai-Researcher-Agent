"""Strict integrity checks for a completed live research pilot.

GitHub Actions can be green even when an experiment catches and records an
internal failure. This validator converts those research-validity conditions
into CI assertions so a run is only green when its artifacts are usable.
"""

from __future__ import annotations

from collections import Counter
import json
import math
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs"

# Independent frozen pilot assignment: a trace must not define its own treatment.
# Keep this separate from the live runner's ExperimentConfig.from_variant()
# so postrun validation detects, rather than inherits, a changed factor map.
PILOT_TREATMENT_FACTORS = {
    "D6": {"planning_mode": "direct", "source_budget": 6, "verification_mode": "none"},
    "P6": {"planning_mode": "planner", "source_budget": 6, "verification_mode": "none"},
    "P6V": {"planning_mode": "planner", "source_budget": 6, "verification_mode": "verify"},
}


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate keys at every depth, including otherwise unused fields."""
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"duplicate JSON key {key!r}")
        record[key] = value
    return record


def _reject_json_constant(token: str):
    """Python's JSON decoder otherwise accepts NaN and Infinity extensions."""
    raise ValueError(f"nonstandard JSON numeric constant {token!r}")


def _finite_json_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"nonfinite JSON numeric literal {token!r}")
    return value


def _load_json(path: Path) -> dict:
    """Parse one unambiguous, finite JSON object without last-key-wins semantics."""
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
        parse_float=_finite_json_float,
    )
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON document must be an object")
    return payload


def _read_artifact(path: Path, output_root: Path, errors: list[str]) -> dict | None:
    """Return a diagnostic instead of crashing or silently selecting bad inputs."""
    try:
        return _load_json(path)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        try:
            label = str(path.relative_to(output_root))
        except ValueError:
            label = str(path)
        errors.append(f"invalid JSON artifact {label}: {exc}")
        return None


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


def _count(record: dict, field: str, source: str, errors: list[str]) -> int:
    """Reject coerced/missing telemetry while collecting all independent errors."""
    value = record.get(field)
    if type(value) is not int or value < 0:
        errors.append(f"{source}.{field} must be a nonnegative integer; got {value!r}")
        return 0
    return value


def _temperature(record: dict, source: str, errors: list[str]) -> int | float | None:
    """Reject numeric-looking strings, booleans and nonfinite settings."""
    value = record.get("temperature")
    if type(value) not in (int, float):
        errors.append(f"{source}.temperature must be a finite numeric value")
        return None
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        errors.append(f"{source}.temperature must be a finite numeric value")
        return None
    return value



def _audit_progress_events(
    progress: dict, expected_pairs: set[tuple[str, str]], errors: list[str]
) -> None:
    """Reconcile the run-event ledger with the frozen pilot assignment.

    The live runner writes one terminal event per attempted cell. A matching
    aggregate counter alone cannot establish that different cells were run.
    Legacy unversioned fixture/checkpoint records may lack this newer ledger;
    a versioned runner checkpoint must not silently omit it.
    """
    if "events" not in progress:
        version = progress.get("schema_version")
        if type(version) is int and version >= 1:
            errors.append("versioned progress is missing its events ledger")
        return

    events = progress["events"]
    if not isinstance(events, list):
        errors.append("progress.events must be a list")
        return
    if "current" in progress and progress["current"] is not None:
        errors.append("progress.current must be null for a completed pilot")
    if len(events) != len(expected_pairs):
        errors.append(
            f"progress events={len(events)} expected={len(expected_pairs)}"
        )
    if type(progress.get("attempted_runs")) is int and len(events) != progress["attempted_runs"]:
        errors.append("progress events count differs from attempted_runs")

    seen: set[tuple[str, str]] = set()
    completed = 0
    for index, event in enumerate(events, start=1):
        label = f"progress.events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{label} must be an object")
            continue
        variant, task_id = event.get("variant"), event.get("task_id")
        if any(
            type(value) is not str or not value or value != value.strip()
            for value in (variant, task_id)
        ):
            errors.append(f"{label} has invalid treatment/task identity")
            continue
        pair = (variant, task_id)
        if pair not in expected_pairs:
            errors.append(f"{label} has unplanned treatment/task cell: {pair}")
        if pair in seen:
            errors.append(f"{label} duplicates treatment/task cell: {pair}")
        seen.add(pair)
        if event.get("status") != "completed" or type(event.get("status")) is not str:
            errors.append(f"{label} is not a completed terminal event")
        else:
            completed += 1

    if seen != expected_pairs:
        errors.append(f"progress events missing planned cells: {sorted(expected_pairs - seen)}")
    if type(progress.get("completed_runs")) is int and completed != progress["completed_runs"]:
        errors.append("progress completed event count differs from completed_runs")



def _enumerate_pilot_traces(
    output_root: Path, selected_variants: list[str], errors: list[str]
) -> list[Path]:
    """Inventory every trace-root entry before selecting experimental cells.

    A two-level *.json glob can overlook nested retries, unknown arm
    directories, temporary files, and symlinked sources. A successful
    cardinality check on *selected* files is not evidence that those were
    all the files present in the experimental workspace.
    """
    root = output_root / "experiment_traces"
    if root.is_symlink():
        errors.append("pilot trace root must not be a symlink")
        return []
    if not root.is_dir():
        errors.append("missing or invalid pilot trace root directory")
        return []

    files: list[Path] = []
    try:
        for arm in sorted(root.iterdir()):
            if (arm.is_symlink() or not arm.is_dir()
                    or arm.name not in selected_variants):
                errors.append(
                    f"unselected pilot trace directory or entry: {arm.relative_to(output_root)}"
                )
                continue
            for source in sorted(arm.iterdir()):
                if (source.is_symlink() or not source.is_file()
                        or source.suffix != ".json"):
                    errors.append(
                        f"unselected pilot trace entry: {source.relative_to(output_root)}"
                    )
                    continue
                files.append(source)
    except OSError as exc:
        errors.append(f"cannot inspect pilot trace inventory: {exc}")
    return files


def validate_pilot(output_root: Path = DEFAULT_OUTPUT_ROOT) -> list[str]:
    errors: list[str] = []
    if output_root.is_symlink():
        return ["pilot output root must not be a symlink"]
    manifest_path = output_root / "pilot_manifest.json"
    progress_path = output_root / "pilot_progress.json"
    summary_path = output_root / "pilot_summary.json"

    for required in (manifest_path, progress_path, summary_path):
        if required.is_symlink():
            errors.append(f"required artifact is a symlink: {required.name}")
        elif not required.is_file():
            errors.append(f"missing required artifact: {required.name}")
    if errors:
        return errors

    manifest = _read_artifact(manifest_path, output_root, errors)
    progress = _read_artifact(progress_path, output_root, errors)
    summary = _read_artifact(summary_path, output_root, errors)
    if errors:
        return errors

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

    progress_counts = {
        field: _count(progress, field, "progress", errors)
        for field in ("total_expected_runs", "attempted_runs", "completed_runs",
                      "failed_runs", "timeout_runs")
    }
    if progress_counts["total_expected_runs"] != expected_count:
        errors.append(
            "progress total_expected_runs does not match manifest: "
            f"{progress.get('total_expected_runs')} != {expected_count}"
        )
    # A correct aggregate count cannot substitute for a unique, complete
    # terminal-event ledger when the live runner records one.
    _audit_progress_events(progress, expected_pairs, errors)
    for field in ("attempted_runs", "completed_runs"):
        if progress_counts[field] != expected_count:
            errors.append(f"{field}={progress.get(field)} expected={expected_count}")
    for field in ("failed_runs", "timeout_runs"):
        if progress_counts[field] != 0:
            errors.append(f"{field}={progress.get(field)}")

    trace_files = _enumerate_pilot_traces(output_root, variants, errors)
    if len(trace_files) != expected_count:
        errors.append(
            f"trace_count={len(trace_files)} expected={expected_count}"
        )

    seen_pairs: set[tuple[str, str]] = set()
    for trace_file in trace_files:
        payload = _read_artifact(trace_file, output_root, errors)
        if payload is None:
            continue
        experiment = payload.get("experiment", {})
        trace = payload.get("trace", {})
        if not isinstance(experiment, dict) or not isinstance(trace, dict):
            errors.append(f"invalid pilot trace identity structure: {trace_file.name}")
            continue
        # The create-only publisher uses run_id as the trace filename stem.
        # Reject an explicitly supplied but contradictory ID rather than
        # silently trusting the directory/metadata or selecting a retry.
        for source_name, record in (("trace", trace), ("experiment", experiment)):
            if "run_id" in record:
                run_id = record["run_id"]
                if (type(run_id) is not str or not run_id
                        or run_id != run_id.strip() or run_id != trace_file.stem):
                    errors.append(
                        f"{trace_file.name}: {source_name}.run_id "
                        "disagrees with source filename"
                    )
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

        # Never let a self-consistent but incorrectly labelled execution
        # define the treatment it purports to measure. A P6V trace with
        # verification disabled or a D6 trace with planner queries must not
        # pass just because its own counters agree with its own mode.
        frozen_factors = PILOT_TREATMENT_FACTORS.get(variant)
        if frozen_factors is not None:
            for field, expected_value in frozen_factors.items():
                for source_name, record in (("trace", trace), ("experiment", experiment)):
                    # Legacy experiment metadata can omit an optional factor;
                    # the execution trace itself must always declare each one.
                    if source_name == "experiment" and field not in record:
                        continue
                    actual_value = record.get(field)
                    if type(actual_value) is not type(expected_value) or actual_value != expected_value:
                        errors.append(
                            f"{label}: {source_name}.{field}={actual_value!r} "
                            f"differs from frozen {variant} factor {expected_value!r}"
                        )

        if trace.get("completed") is not True:
            errors.append(f"{label}: completed is not true")

        source_budget = _count(trace, "source_budget", f"{label}: trace", errors)
        source_count = _count(trace, "source_count", f"{label}: trace", errors)
        success_count = _count(trace, "successful_source_count", f"{label}: trace", errors)
        failed_count = _count(trace, "failed_source_count", f"{label}: trace", errors)
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
        # Use the assigned arm, not a potentially tampered trace mode.
        expected_mode = (
            frozen_factors["planning_mode"] if frozen_factors is not None
            else planning_mode
        )
        expected_queries = 1 if expected_mode == "direct" else 4
        for field in ("query_count", "search_call_count"):
            if _count(trace, field, f"{label}: trace", errors) != expected_queries:
                errors.append(
                    f"{label}: {field}={trace.get(field)} expected={expected_queries}"
                )
        for field in ("research_context_words", "report_words", "model_call_count",
                      "total_tokens"):
            if _count(trace, field, f"{label}: trace", errors) <= 0:
                display = "provider total_tokens" if field == "total_tokens" else field
                errors.append(f"{label}: {display} is zero")
        if trace.get("usage_accounting_status") != "provider_usage_complete":
            errors.append(
                f"{label}: usage_accounting_status={trace.get('usage_accounting_status')}"
            )

        if trace.get("smart_model") != manifest.get("smart_model"):
            errors.append(f"{label}: smart model differs from manifest")
        if trace.get("fast_model") != manifest.get("fast_model"):
            errors.append(f"{label}: fast model differs from manifest")
        trace_temperature = _temperature(trace, f"{label}: trace", errors)
        manifest_temperature = _temperature(manifest, "manifest", errors)
        if (trace_temperature is not None and manifest_temperature is not None
                and trace_temperature != manifest_temperature):
            errors.append(f"{label}: temperature differs from manifest")

        verification_mode = (
            frozen_factors["verification_mode"] if frozen_factors is not None
            else trace.get("verification_mode")
        )
        if verification_mode == "verify":
            if trace.get("verification_status") != "ok":
                errors.append(
                    f"{label}: verification_status={trace.get('verification_status')}"
                )
            if _count(trace, "verified_claim_count", f"{label}: trace", errors) <= 0:
                errors.append(f"{label}: verifier checked zero claims")
        else:
            if "verified_claim_count" in trace:
                _count(trace, "verified_claim_count", f"{label}: trace", errors)
            if trace.get("verification_status") != "not_requested":
                errors.append(
                    f"{label}: unexpected verification_status={trace.get('verification_status')}"
                )

    missing_pairs = expected_pairs - seen_pairs
    if missing_pairs:
        errors.append(f"missing trace pairs: {sorted(missing_pairs)}")

    if _count(summary, "n_trace_files", "summary", errors) != expected_count:
        errors.append(
            f"summary n_trace_files={summary.get('n_trace_files')} expected={expected_count}"
        )
    variant_summary = summary.get("variant_summary", {})
    for variant in variants:
        stats = variant_summary.get(variant)
        if not isinstance(stats, dict):
            errors.append(f"summary missing variant {variant}")
            continue
        for field in ("n_runs", "n_completed"):
            if _count(stats, field, f"summary {variant}", errors) != len(task_ids):
                errors.append(
                    f"summary {variant}.{field}={stats.get(field)} expected={len(task_ids)}"
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

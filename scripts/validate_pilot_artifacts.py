"""Strict integrity checks for a completed live research pilot.

GitHub Actions can be green even when an experiment catches and records an
internal failure. This validator converts those research-validity conditions
into CI assertions so a run is only green when its artifacts are usable.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import json
import math
import re
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



# The runner records these UTC instants using datetime.isoformat(). Accept
# the equally explicit 'Z' suffix but never local/naive or ambiguous offsets.
_UTC_INSTANT = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)$"
)


def _pilot_utc_instant(value, source: str, errors: list[str]) -> datetime | None:
    if type(value) is not str or not _UTC_INSTANT.fullmatch(value):
        errors.append(f"{source} must be an explicit UTC ISO-8601 timestamp")
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{source} must be a valid UTC ISO-8601 timestamp")
        return None
    if result.utcoffset() != timedelta(0):
        errors.append(f"{source} must be in UTC")
        return None
    return result


def _audit_pilot_clock_window(
    manifest: dict, progress: dict, errors: list[str]
) -> None:
    """Verify versioned pilot event timestamps without assuming treatment order.

    The serial live runner records a launch, a checkpoint start/finish and
    per-cell event intervals. These instants are *reported metadata*, not
    authenticated wall-clock receipts or proof of randomized assignment.
    Unversioned historical checkpoints retain their explicit legacy
    compatibility, but malformed version markers cannot bypass this audit.
    """
    if "schema_version" not in progress:
        return
    version = progress["schema_version"]
    if type(version) is not int or version < 1:
        errors.append("progress.schema_version must be a positive integer")
        return

    manifest_start = _pilot_utc_instant(
        manifest.get("started_at_utc"), "manifest.started_at_utc", errors
    )
    progress_start = _pilot_utc_instant(
        progress.get("started_at_utc"), "progress.started_at_utc", errors
    )
    progress_finish = _pilot_utc_instant(
        progress.get("finished_at_utc"), "progress.finished_at_utc", errors
    )
    if manifest_start is not None and progress_start is not None:
        if progress_start < manifest_start:
            errors.append("progress started before manifest creation")
    if progress_start is not None and progress_finish is not None:
        if progress_finish < progress_start:
            errors.append("progress finished before it started")

    events = progress.get("events")
    if not isinstance(events, list):
        return  # Already diagnosed by the event-ledger integrity audit.

    intervals = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            continue  # Already diagnosed by the event-ledger integrity audit.
        label = f"progress.events[{index}]"
        started = _pilot_utc_instant(
            event.get("started_at_utc"), f"{label}.started_at_utc", errors
        )
        finished = _pilot_utc_instant(
            event.get("finished_at_utc"), f"{label}.finished_at_utc", errors
        )
        if started is None or finished is None:
            continue
        if finished < started:
            errors.append(f"{label} finished before it started")
            continue
        if progress_start is not None and started < progress_start:
            errors.append(f"{label} started before the pilot checkpoint")
        if progress_finish is not None and finished > progress_finish:
            errors.append(f"{label} finished after the pilot checkpoint")
        intervals.append((started, finished, index))

    # Pilot execution is serial; overlapping event windows contradict that
    # execution model. Sort independently of event-list order, because the
    # validator must not infer randomized/fixed treatment order from indexing.
    intervals.sort()
    for (_, earlier_finish, earlier_index), (later_start, _, later_index) in zip(
        intervals, intervals[1:]
    ):
        if later_start < earlier_finish:
            errors.append(
                f"progress events {earlier_index} and {later_index} overlap "
                "despite serial pilot execution"
            )




def _audit_pilot_provider_token_ledger(
    trace: dict, label: str, schema_version: int | None, errors: list[str]
) -> None:
    """Check producer token conservation independently of the summarizer.

    The trace producer writes schema-v2 token totals and a per-model ledger.
    Historical unversioned minimal records without those fields remain
    compatible, but supplying any part of a ledger activates strict checks.
    This checks internal consistency, not authenticity of provider billing.
    """
    fields = ("prompt_tokens", "completion_tokens", "provider_usage_by_model")
    if schema_version is None and not any(key in trace for key in fields):
        return
    if schema_version == 1 and not any(key in trace for key in fields):
        return

    prompt = trace.get("prompt_tokens")
    completion = trace.get("completion_tokens")
    total = trace.get("total_tokens")
    valid_counts = True
    for field, value in (
        ("prompt_tokens", prompt), ("completion_tokens", completion),
        ("total_tokens", total),
    ):
        if type(value) is not int or value < 0:
            errors.append(f"{label}: trace.{field} must be a nonnegative integer for provider usage")
            valid_counts = False
    if valid_counts and total != prompt + completion:
        errors.append(
            f"{label}: provider token totals disagree: total_tokens "
            "!= prompt_tokens + completion_tokens"
        )

    if "provider_usage_by_model" not in trace:
        if schema_version is not None and schema_version >= 2:
            errors.append(f"{label}: schema-v2 trace missing provider_usage_by_model")
        return
    by_model = trace["provider_usage_by_model"]
    if not isinstance(by_model, dict):
        errors.append(f"{label}: provider_usage_by_model must be a mapping")
        return
    if not by_model and trace.get("usage_accounting_status") == "provider_usage_complete":
        errors.append(f"{label}: complete provider usage has an empty per-model ledger")
        return

    sums = {"prompt_tokens": 0, "completion_tokens": 0}
    ledger_valid = True
    for model, bucket in by_model.items():
        if (type(model) is not str or not model or model != model.strip()
                or not isinstance(bucket, dict)):
            errors.append(f"{label}: invalid provider model usage bucket")
            ledger_valid = False
            continue
        for field in sums:
            value = bucket.get(field)
            if type(value) is not int or value < 0:
                errors.append(
                    f"{label}: provider model {model!r}.{field} "
                    "must be an explicit nonnegative integer"
                )
                ledger_valid = False
            else:
                sums[field] += value
    if valid_counts and ledger_valid:
        for field in sums:
            if trace[field] != sums[field]:
                errors.append(
                    f"{label}: provider usage ledger mismatch for {field}: "
                    f"trace={trace[field]}, model_sum={sums[field]}"
                )



def _audit_pilot_paired_summary(
    summary: dict,
    source_traces: dict[tuple[str, str], dict],
    variants: list[str],
    task_ids: list[str],
    errors: list[str],
) -> None:
    """Independently reconcile descriptive non-cost pair deltas with traces.

    Validate the published rows *and* their means; agreeing aggregate counts
    cannot establish that the reported per-task contrasts were calculated
    from the selected experimental cells. USD estimates are deliberately
    outside this check: price and missingness require a distinct source audit.
    """

    def match_number(actual, expected, label):
        if type(expected) is int:
            if type(actual) is not int or actual != expected:
                errors.append(f"{label} disagrees with pilot traces: {actual!r} != {expected!r}")
            return
        if expected is None:
            if actual is not None:
                errors.append(f"{label} must be null when no paired tasks exist")
            return
        if type(actual) not in (int, float):
            errors.append(f"{label} must be a finite numeric mean")
            return
        try:
            valid = math.isfinite(actual) and math.isclose(
                actual, expected, rel_tol=1e-12, abs_tol=1e-12
            )
        except OverflowError:
            valid = False
        if not valid:
            errors.append(f"{label} disagrees with pilot traces: {actual!r} != {expected!r}")

    comparisons = summary.get("paired_operational_differences")
    expected_names = {
        "P6_minus_D6": ("D6", "P6"),
        "P6V_minus_P6": ("P6", "P6V"),
    }
    if not isinstance(comparisons, dict):
        errors.append("summary paired_operational_differences must be an object")
        return
    if set(comparisons) != set(expected_names):
        errors.append("summary paired comparison names differ from frozen pilot contrasts")
        return

    for name, (left, right) in expected_names.items():
        record = comparisons[name]
        label = f"summary paired_operational_differences.{name}"
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            continue

        union_tasks = sorted(task_ids) if left in variants or right in variants else []
        paired_tasks = sorted(task_ids) if left in variants and right in variants else []
        expected_missing_left = union_tasks if left not in variants else []
        expected_missing_right = union_tasks if right not in variants else []
        match_number(record.get("n_tasks_union"), len(union_tasks), f"{label}.n_tasks_union")
        match_number(record.get("n_pairs"), len(paired_tasks), f"{label}.n_pairs")
        for field, expected in (
            ("missing_left_task_ids", expected_missing_left),
            ("missing_right_task_ids", expected_missing_right),
        ):
            if record.get(field) != expected:
                errors.append(f"{label}.{field} disagrees with selected pilot tasks")

        expected_rows = []
        for task in paired_tasks:
            before = source_traces[(left, task)]
            after = source_traces[(right, task)]
            def latency(trace):
                value = trace.get("latency_seconds", 0.0)
                if type(value) not in (int, float) or value < 0:
                    return None
                try:
                    return float(value) if math.isfinite(value) else None
                except (OverflowError, ValueError):
                    return None

            first_latency, second_latency = latency(before), latency(after)
            if first_latency is None or second_latency is None:
                errors.append(f"{label}: nonfinite or invalid source latency for {task}")
                return
            expected_rows.append({
                "task_id": task,
                "total_tokens_delta": after["total_tokens"] - before["total_tokens"],
                "latency_seconds_delta": second_latency - first_latency,
                "model_calls_delta": after["model_call_count"] - before["model_call_count"],
                "successful_sources_delta": (
                    after["successful_source_count"] - before["successful_source_count"]
                ),
            })
        rows = record.get("pairs")
        if not isinstance(rows, list) or len(rows) != len(expected_rows):
            errors.append(f"{label}.pairs must include each selected paired task exactly once")
            continue
        for position, (observed, expected) in enumerate(zip(rows, expected_rows), start=1):
            row_label = f"{label}.pairs[{position}]"
            if not isinstance(observed, dict) or observed.get("task_id") != expected["task_id"]:
                errors.append(f"{row_label} has a missing, repeated or out-of-order task")
                continue
            for field in (
                "total_tokens_delta", "latency_seconds_delta",
                "model_calls_delta", "successful_sources_delta",
            ):
                value = expected[field]
                if field == "latency_seconds_delta":
                    match_number(observed.get(field), float(value), f"{row_label}.{field}")
                else:
                    match_number(observed.get(field), value, f"{row_label}.{field}")

        for mean_key, row_key in (
            ("avg_total_tokens_delta", "total_tokens_delta"),
            ("avg_latency_seconds_delta", "latency_seconds_delta"),
            ("avg_model_calls_delta", "model_calls_delta"),
            ("avg_successful_sources_delta", "successful_sources_delta"),
        ):
            values = [item[row_key] for item in expected_rows]
            if values:
                try:
                    mean = math.fsum(values) / len(values)
                except OverflowError:
                    errors.append(f"{label}: source values overflow the paired mean")
                    continue
            else:
                mean = None
            match_number(record.get(mean_key), mean, f"{label}.{mean_key}")


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
    _audit_pilot_clock_window(manifest, progress, errors)
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
    source_traces: dict[tuple[str, str], dict] = {}
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
        if pair in expected_pairs and pair not in source_traces:
            source_traces[pair] = trace

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

        # Schema-v2 traces are written with explicit provider token buckets.
        # A plausible total_tokens count is insufficient evidence of complete
        # usage: independently reconcile the model-level and aggregate counts.
        schema_version = payload.get("schema_version")
        if "schema_version" in payload and (
            type(schema_version) is not int or schema_version < 1
        ):
            errors.append(f"{label}: invalid trace schema_version")
        else:
            _audit_pilot_provider_token_ledger(trace, label, schema_version, errors)

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

    # A versioned summary may not silently omit its paired descriptive rows.
    # Legacy minimal summary fixtures without a schema marker remain compatible.
    if "schema_version" in summary:
        if type(summary["schema_version"]) is not int or summary["schema_version"] != 1:
            errors.append("summary.schema_version must be the supported integer 1")
        elif "paired_operational_differences" not in summary:
            errors.append("versioned pilot summary is missing paired operational comparisons")
    if "paired_operational_differences" in summary and not errors:
        _audit_pilot_paired_summary(summary, source_traces, variants, task_ids, errors)

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

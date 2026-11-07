"""Read-only chronology diagnostic for the historical VERA main-study progress log.

Checks the recorded fixed treatment schedule, not historical archive custody,
actual web conditions, causal identification, or statistical significance.
No provider calls, inference, or report publication are performed.
"""
from __future__ import annotations

import argparse
import csv
from contextlib import ExitStack
from datetime import datetime, timedelta
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat

STUDY_ID = "budget-main-v1"
TASK_SET_ID = "main-budget-v1-2026-09-11"
HISTORICAL_RUNNER_COMMIT = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
VARIANTS = ("D3", "D6", "P6", "P6V")
TASK_IDS = tuple(f"main-{index:02d}" for index in range(1, 11))
EXPECTED_ORDER = tuple((task, variant) for task in TASK_IDS for variant in VARIANTS)
# Descriptive timing diagnostics only: do not change the frozen inference family.
PRIMARY_CONTRAST_START_PAIRS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
# Exact completed-file keys emitted by the original frozen runner at
# c3c15e46a8eec3a8bbc24c968eedc0548172a897. This schema is a
# structural correspondence check, not independent archive authentication.
ORIGINAL_COMPLETED_PROGRESS_FIELDS = frozenset({
    "schema_version", "study_id", "task_set_id", "total_expected_runs",
    "attempted_runs", "completed_runs", "failed_runs", "timeout_runs",
    "estimated_treatment_cost_usd", "events", "current",
    "started_at_utc", "finished_at_utc",
})
ORIGINAL_COMPLETED_EVENT_FIELDS = frozenset({
    "variant", "task_id", "status", "started_at_utc", "finished_at_utc",
})

MAX_PROGRESS_BYTES = 1024 * 1024
# The historical writer serializes ordinary bounded Python ints/floats. Bounds
# apply even to uninspected JSON fields in a recovered, untrusted progress log.
MAX_JSON_NUMBER_TOKEN_CHARS = 128
PUBLISHED_TREATMENT_CSV = Path(__file__).resolve().parents[1] / "outputs" / "main_study_runs.csv"
# Pinned file-byte SHA-256 from the canonical automated-analysis manifest.
PUBLISHED_TREATMENT_CSV_SHA256 = (
    "966ea80519af5ea7b832c86d7868525a4ef75874f396f242291e3be949382a0e"
)
MAX_PUBLISHED_CSV_BYTES = 128 * 1024
# Accommodate only float summation-order rounding, not changed study costs.
TREATMENT_COST_FLOAT_TOLERANCE_USD = 1e-12
# Bound only materially impossible outer UTC durations, allowing a small
# difference between wall-clock and trace latency clocks.
TREATMENT_LATENCY_CLOCK_TOLERANCE_MICROSECONDS = 5_000_000

# Original Actions run 34620917346, attempt 1, job 103334373932,
# "Run 10-task four-variant treatment matrix" step; inspected 2026-10-31.
# These second-resolution GitHub service timestamps are not a signed archive.
HISTORICAL_TREATMENT_STEP_STARTED = "2026-09-11T16:15:52+00:00"
HISTORICAL_TREATMENT_STEP_COMPLETED = "2026-09-11T17:12:08+00:00"
HISTORICAL_TREATMENT_JOB_ID = 103334373932
HISTORICAL_TREATMENT_RUN_ID = 34620917346
HISTORICAL_STEP_BOUNDARY_TOLERANCE = timedelta(seconds=5)


class ChronologyError(ValueError):
    """The observed file cannot establish a valid recorded schedule."""



def _capture_chronology_source(path: Path, *, limit: int, label: str) -> bytes:
    """Read a bounded leaf while holding no-follow ancestors across capture."""
    path = Path(path)
    if ".." in path.parts:
        raise ChronologyError(f"{label} path contains parent traversal")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ChronologyError(f"{label} requires no-follow directory support")
    absolute = path.absolute()
    dflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fflags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)

    def file_generation(st):
        return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
                st.st_mtime_ns, st.st_ctime_ns)

    def directory_identity(st):
        # Unrelated sibling writes may change directory mtime.
        return (st.st_dev, st.st_ino, st.st_mode)

    try:
        with ExitStack() as stack:
            parent = os.open(absolute.anchor, dflags)
            stack.callback(os.close, parent)
            ancestors = []
            for name in absolute.parts[1:-1]:
                child = os.open(name, dflags, dir_fd=parent)
                stack.callback(os.close, child)
                opened_dir = os.fstat(child)
                linked_dir = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (not stat.S_ISDIR(opened_dir.st_mode)
                        or directory_identity(opened_dir) != directory_identity(linked_dir)):
                    raise ChronologyError(f"{label} parent directory changed before capture")
                ancestors.append((parent, name, child))
                parent = child
            before = os.stat(absolute.name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ChronologyError(f"{label} must be a single-link regular non-symlink file")
            if not 0 < before.st_size <= limit:
                raise ChronologyError(f"{label} input size outside bounded range")
            fd = os.open(absolute.name, fflags, dir_fd=parent)
            stack.callback(os.close, fd)
            opened = os.fstat(fd)
            linked = os.stat(absolute.name, dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(opened.st_mode)
                    or file_generation(before) != file_generation(opened)
                    or file_generation(opened) != file_generation(linked)):
                raise ChronologyError(f"{label} source changed before capture")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                raw = handle.read(limit + 1)
            after = os.fstat(fd)
            linked_after = os.stat(absolute.name, dir_fd=parent, follow_symlinks=False)
            if (len(raw) != opened.st_size
                    or file_generation(opened) != file_generation(after)
                    or file_generation(after) != file_generation(linked_after)):
                raise ChronologyError(f"{label} source changed during capture")
            for holder, name, child in ancestors:
                visible = os.stat(name, dir_fd=holder, follow_symlinks=False)
                if directory_identity(visible) != directory_identity(os.fstat(child)):
                    raise ChronologyError(f"{label} parent directory changed during capture")
            return raw
    except OSError as exc:
        raise ChronologyError(f"cannot safely capture {label} input") from exc


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ChronologyError(f"duplicate JSON key in progress log: {key}")
        result[key] = value
    return result


def _reject_constant(token):
    raise ChronologyError(f"nonstandard JSON constant in progress log: {token}")


def _bounded_json_int(token: str) -> int:
    if len(token) > MAX_JSON_NUMBER_TOKEN_CHARS:
        raise ChronologyError("progress JSON integer token exceeds numeric bound")
    return int(token)


def _finite_json_float(token: str) -> float:
    if len(token) > MAX_JSON_NUMBER_TOKEN_CHARS:
        raise ChronologyError("progress JSON float token exceeds numeric bound")
    number = float(token)
    if not math.isfinite(number):
        raise ChronologyError("progress JSON float overflows finite range")
    return number


def _capture_progress(path: Path) -> tuple[dict, str, int]:
    """Capture bounded original progress through held no-follow ancestors."""
    raw = _capture_chronology_source(path, limit=MAX_PROGRESS_BYTES, label="progress")
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
            parse_int=_bounded_json_int, parse_float=_finite_json_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ChronologyError("progress input is not unambiguous UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise ChronologyError("progress top level must be an object")
    return payload, hashlib.sha256(raw).hexdigest(), len(raw)



def _load_published_treatment_cost(path: Path, *, include_latencies: bool = False):
    """Pin the frozen 40-cell resource ledger; optionally capture latency.

    This is local source integrity, not authentication of provider billing.
    """
    raw = _capture_chronology_source(
        path, limit=MAX_PUBLISHED_CSV_BYTES, label="published treatment CSV"
    )
    if hashlib.sha256(raw).hexdigest() != PUBLISHED_TREATMENT_CSV_SHA256:
        raise ChronologyError(
            "published treatment CSV differs from frozen analysis input SHA-256"
        )
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
        header = reader.fieldnames
        required = {"variant_id", "task_id", "completed", "treatment_cost_usd"}
        if include_latencies:
            required.add("latency_seconds")
        if (header is None or len(set(header)) != len(header)
                or not required <= set(header)):
            raise ChronologyError("published treatment CSV has missing/ambiguous columns")
        observed = set()
        costs = []
        latencies = {}
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ChronologyError("published treatment CSV has malformed row")
            key = (row["task_id"], row["variant_id"])
            if key not in EXPECTED_ORDER or key in observed or row["completed"] != "True":
                raise ChronologyError(
                    "published treatment CSV has duplicate, unknown, or incomplete cell"
                )
            observed.add(key)
            token = row["treatment_cost_usd"]
            if not token or len(token) > MAX_JSON_NUMBER_TOKEN_CHARS:
                raise ChronologyError("published treatment CSV has invalid cost token")
            cost = float(token)
            if not math.isfinite(cost) or cost < 0:
                raise ChronologyError("published treatment CSV has nonfinite/negative cost")
            costs.append(cost)
            if include_latencies:
                latency_token = row["latency_seconds"]
                if not latency_token or len(latency_token) > MAX_JSON_NUMBER_TOKEN_CHARS:
                    raise ChronologyError("published treatment CSV has invalid latency token")
                latency = float(latency_token)
                if not math.isfinite(latency) or latency <= 0:
                    raise ChronologyError(
                        "published treatment CSV has nonpositive or nonfinite latency"
                    )
                latencies[key] = latency
    except (UnicodeDecodeError, csv.Error, ValueError, OverflowError) as exc:
        if isinstance(exc, ChronologyError):
            raise
        raise ChronologyError("cannot parse published treatment CSV ledger") from exc
    if observed != set(EXPECTED_ORDER):
        raise ChronologyError("published treatment CSV lacks frozen 40-cell matrix")
    total_cost = math.fsum(costs)
    return (total_cost, latencies) if include_latencies else total_cost


# Historical runner c3c15e46 emitted datetime.now(timezone.utc).isoformat().
# Python's fromisoformat() accepts many other spellings (Unicode separators,
# basic dates, Z and zero-offset aliases). Those cannot be original writer
# output, even when they describe the same instant.
_ORIGINAL_WRITER_UTC_ISOFORMAT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{6})?\+00:00"
)


def _utc(value, label: str) -> datetime:
    if (type(value) is not str
            or _ORIGINAL_WRITER_UTC_ISOFORMAT.fullmatch(value) is None):
        raise ChronologyError(
            f"{label} must be explicitly UTC in original runner ISO format"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ChronologyError(f"{label} is not a real UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ChronologyError(f"{label} must be explicitly UTC")
    return parsed


def _elapsed_microseconds(later: datetime, earlier: datetime) -> int:
    """Exact wall-clock separation of two recorded UTC timestamps."""
    delta = later - earlier
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def audit_progress(payload: dict, *, sha256: str, byte_size: int,
                   expected_sha256: str | None = None,
                   published_treatment_csv: Path | None = None,
                    require_historical_actions_step_window: bool = False) -> dict:
    """Validate a *recorded* task-major, fixed-arm schedule without outcomes."""
    if type(payload) is not dict:
        raise ChronologyError("progress must be an original completed-run JSON object")
    observed_fields = set(payload)
    if observed_fields != ORIGINAL_COMPLETED_PROGRESS_FIELDS:
        missing = sorted(ORIGINAL_COMPLETED_PROGRESS_FIELDS - observed_fields)
        unexpected = sorted(map(str, observed_fields - ORIGINAL_COMPLETED_PROGRESS_FIELDS))
        raise ChronologyError(
            "progress fields differ from original completed-run writer schema: "
            f"missing={missing}, unexpected={unexpected}"
        )
    if expected_sha256 is not None:
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise ChronologyError("supplied progress SHA-256 has invalid format")
        if expected_sha256 != sha256:
            raise ChronologyError("observed progress bytes disagree with supplied pin")
    for field, expected in (
        ("schema_version", 1), ("study_id", STUDY_ID),
        ("task_set_id", TASK_SET_ID),
        ("total_expected_runs", 40), ("attempted_runs", 40),
        ("completed_runs", 40), ("failed_runs", 0), ("timeout_runs", 0),
    ):
        observed = payload.get(field)
        if type(observed) is not type(expected) or observed != expected:
            raise ChronologyError(f"progress {field} differs from completed frozen run")
    # The original completed runner always persists a finite cumulative
    # treatment-cost estimate. Validate its shape without recalculating prices
    # or treating this retrospective log as authenticated financial evidence.
    cost = payload.get("estimated_treatment_cost_usd")
    if (type(cost) not in (int, float) or cost < 0
            or (type(cost) is float and not math.isfinite(cost))):
        raise ChronologyError(
            "progress estimated_treatment_cost_usd must be finite and nonnegative"
        )
    cost_concordance = {"checked": False}
    published_latencies = None
    if published_treatment_csv is not None:
        published_cost, published_latencies = _load_published_treatment_cost(
            published_treatment_csv, include_latencies=True
        )
        if not math.isclose(
            cost, published_cost, rel_tol=0.0,
            abs_tol=TREATMENT_COST_FLOAT_TOLERANCE_USD,
        ):
            raise ChronologyError(
                "recorded final treatment cost differs from frozen published 40-cell sum"
            )
        cost_concordance = {
            "checked": True,
            "published_treatment_csv_sha256": PUBLISHED_TREATMENT_CSV_SHA256,
            "published_treatment_cells_checked": len(EXPECTED_ORDER),
            "published_treatment_cost_sum_usd": published_cost,
            "recorded_final_treatment_cost_usd": cost,
            "difference_usd": cost - published_cost,
            "float_summation_tolerance_usd": TREATMENT_COST_FLOAT_TOLERANCE_USD,
            "provider_billing_authenticated": False,
            "historical_archive_custody_authenticated": False,
        }
    if payload.get("current", "missing") is not None:
        raise ChronologyError("progress has an unfinished current run")
    events = payload.get("events")
    if type(events) is not list or len(events) != len(EXPECTED_ORDER):
        raise ChronologyError("progress must contain exactly 40 recorded events")
    study_start = _utc(payload.get("started_at_utc"), "study start")
    study_end = _utc(payload.get("finished_at_utc"), "study finish")
    previous_finish = study_start
    recorded_starts = {}
    for index, ((task, variant), event) in enumerate(zip(EXPECTED_ORDER, events, strict=True)):
        if type(event) is not dict:
            raise ChronologyError(f"progress event {index + 1} must be an object")
        if set(event) != ORIGINAL_COMPLETED_EVENT_FIELDS:
            raise ChronologyError(
                f"progress event {index + 1} fields differ from original completed-run writer schema"
            )
        if (event.get("task_id") != task or event.get("variant") != variant
                or event.get("status") != "completed" or "error" in event):
            raise ChronologyError(
                f"progress event {index + 1} violates original task-major fixed-arm order"
            )
        started = _utc(event.get("started_at_utc"), f"event {index + 1} start")
        finished = _utc(event.get("finished_at_utc"), f"event {index + 1} finish")
        if started < previous_finish or finished < started:
            raise ChronologyError(f"progress event {index + 1} timestamps overlap or reverse")
        if published_latencies is not None:
            recorded_microseconds = _elapsed_microseconds(finished, started)
            frozen_microseconds = round(
                published_latencies[(task, variant)] * 1_000_000
            )
            if (recorded_microseconds + TREATMENT_LATENCY_CLOCK_TOLERANCE_MICROSECONDS
                    < frozen_microseconds):
                raise ChronologyError(
                    f"progress event {index + 1} UTC interval is shorter than "
                    "frozen published treatment latency beyond clock tolerance"
                )
        previous_finish = finished
        recorded_starts[(task, variant)] = started
    if study_end < previous_finish:
        raise ChronologyError("study finish predates final event")

    # All 40 event intervals fall within the validated study interval above.
    # Compare that enclosing interval to the historical treatment *step*, not
    # to the broader workflow (which later failed in the evaluator step).
    actions_window = {"checked": False}
    if require_historical_actions_step_window:
        step_start = _utc(HISTORICAL_TREATMENT_STEP_STARTED, "Actions step start")
        step_end = _utc(HISTORICAL_TREATMENT_STEP_COMPLETED, "Actions step end")
        if (study_start < step_start - HISTORICAL_STEP_BOUNDARY_TOLERANCE
                or study_end > step_end + HISTORICAL_STEP_BOUNDARY_TOLERANCE):
            raise ChronologyError(
                "recorded study interval is outside original GitHub Actions treatment step"
            )
        actions_window = {
            "checked": True,
            "original_actions_run_id": HISTORICAL_TREATMENT_RUN_ID,
            "original_actions_job_id": HISTORICAL_TREATMENT_JOB_ID,
            "original_actions_run_attempt": 1,
            "step_started_at_utc": HISTORICAL_TREATMENT_STEP_STARTED,
            "step_completed_at_utc": HISTORICAL_TREATMENT_STEP_COMPLETED,
            "timestamp_resolution": "seconds",
            "boundary_tolerance_seconds": int(HISTORICAL_STEP_BOUNDARY_TOLERANCE.total_seconds()),
            "recorded_study_within_treatment_step": True,
            "source": "GitHub Actions original treatment-step job metadata",
            "independently_authenticated": False,
        }

    # Observed timing, not proof of time-varying evidence or a causal correction.
    contrast_lags = {}
    for left, right, label in PRIMARY_CONTRAST_START_PAIRS:
        by_task = {
            task: _elapsed_microseconds(
                recorded_starts[(task, right)], recorded_starts[(task, left)]
            )
            for task in TASK_IDS
        }
        if any(lag < 0 for lag in by_task.values()):
            raise ChronologyError("recorded paired treatment starts are reversed")
        contrast_lags[label] = {
            "left_variant": left,
            "right_variant": right,
            "start_lag_microseconds_by_task": by_task,
            "minimum_start_lag_microseconds": min(by_task.values()),
            "maximum_start_lag_microseconds": max(by_task.values()),
        }
    return {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "status": "recorded_fixed_order_consistent_not_authenticated",
        "historical_runner_commit": HISTORICAL_RUNNER_COMMIT,
        "progress_sha256_observed_now": sha256,
        "progress_bytes_observed_now": byte_size,
        "supplied_digest_matched": expected_sha256 is not None,
        "independent_archive_custody_authenticated": False,
        "recorded_events_checked": len(EXPECTED_ORDER),
        "original_completed_writer_field_schema": {
            "checked": True,
            "progress_fields_checked": len(ORIGINAL_COMPLETED_PROGRESS_FIELDS),
            "completed_event_fields_per_run_checked": len(ORIGINAL_COMPLETED_EVENT_FIELDS),
            "unexpected_fields_allowed": False,
            "independently_authenticated": False,
        },
        "frozen_treatment_cost_concordance": cost_concordance,
        "frozen_treatment_latency_concordance": (
            {
                "checked": True,
                "published_treatment_csv_sha256": PUBLISHED_TREATMENT_CSV_SHA256,
                "published_treatment_cells_checked": len(EXPECTED_ORDER),
                "maximum_wall_clock_shortfall_tolerance_seconds": (
                    TREATMENT_LATENCY_CLOCK_TOLERANCE_MICROSECONDS / 1_000_000
                ),
                "recorded_utc_intervals_not_materially_shorter_than_frozen_latency": True,
                "historical_archive_custody_authenticated": False,
                "trace_latency_clock_authenticated": False,
            }
            if published_latencies is not None else {"checked": False}
        ),
        "historical_actions_step_window_concordance": actions_window,
        "recorded_task_major_schedule": True,
        "recorded_clock_exposure": {
            "interpretation": "recorded_start_time_separation_only_not_web_drift",
            "unit": "microseconds",
            "study_window_microseconds": _elapsed_microseconds(study_end, study_start),
            "primary_contrast_start_lags": contrast_lags,
        },
        "fixed_variant_order_within_each_task": list(VARIANTS),
        "variant_order_randomized": False,
        "temporal_confounding_resolved": False,
        "warning": (
            "Fixed D3/D6/P6/P6V treatment order is confounded with within-task "
            "execution time. Log consistency cannot demonstrate absence of live-web "
            "drift, prove historical custody, or validate randomization assumptions."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress-json", required=True, type=Path)
    parser.add_argument("--expected-sha256", help="Previously retained file hash; matching alone does not authenticate custody")
    parser.add_argument(
        "--published-treatment-csv", type=Path, default=PUBLISHED_TREATMENT_CSV,
        help="Frozen published 40-cell CSV; must match immutable SHA-256 pin",
    )
    args = parser.parse_args(argv)
    try:
        payload, sha256, size = _capture_progress(args.progress_json)
        receipt = audit_progress(
            payload, sha256=sha256, byte_size=size,
            expected_sha256=args.expected_sha256,
            published_treatment_csv=args.published_treatment_csv,
            require_historical_actions_step_window=True,
        )
    except ChronologyError as exc:
        parser.exit(1, f"MAIN-STUDY CHRONOLOGY: FAIL: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

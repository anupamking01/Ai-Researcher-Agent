"""Read-only chronology diagnostic for the historical VERA main-study progress log.

Checks the recorded fixed treatment schedule, not historical archive custody,
actual web conditions, causal identification, or statistical significance.
No provider calls, inference, or report publication are performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
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
MAX_PROGRESS_BYTES = 1024 * 1024


class ChronologyError(ValueError):
    """The observed file cannot establish a valid recorded schedule."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ChronologyError(f"duplicate JSON key in progress log: {key}")
        result[key] = value
    return result


def _reject_constant(token):
    raise ChronologyError(f"nonstandard JSON constant in progress log: {token}")


def _capture_progress(path: Path) -> tuple[dict, str, int]:
    """Bound input bytes and prevent symlink, FIFO and observable file swaps."""
    path = Path(path)
    try:
        named_before = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(named_before.st_mode):
            raise ChronologyError("progress input must be a regular non-symlink file")
        if not 0 < named_before.st_size <= MAX_PROGRESS_BYTES:
            raise ChronologyError("progress input size outside bounded range")
        fd = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError as exc:
        raise ChronologyError("cannot safely open progress input") from exc

    def generation(entry):
        return (entry.st_dev, entry.st_ino, entry.st_mode, entry.st_size,
                entry.st_mtime_ns, entry.st_ctime_ns)

    try:
        opened_before = os.fstat(fd)
        if (not stat.S_ISREG(opened_before.st_mode)
                or generation(named_before) != generation(opened_before)):
            raise ChronologyError("progress source changed before capture")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_PROGRESS_BYTES + 1)
        opened_after = os.fstat(fd)
        named_after = path.stat(follow_symlinks=False)
        if (len(raw) != opened_before.st_size
                or generation(opened_before) != generation(opened_after)
                or generation(opened_after) != generation(named_after)):
            raise ChronologyError("progress source changed during capture")
    except OSError as exc:
        raise ChronologyError("cannot safely capture progress input") from exc
    finally:
        os.close(fd)

    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ChronologyError("progress input is not unambiguous UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise ChronologyError("progress top level must be an object")
    return payload, hashlib.sha256(raw).hexdigest(), len(raw)


def _utc(value, label: str) -> datetime:
    if type(value) is not str:
        raise ChronologyError(f"{label} must be an ISO 8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ChronologyError(f"{label} is not an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ChronologyError(f"{label} must be explicitly UTC")
    return parsed


def audit_progress(payload: dict, *, sha256: str, byte_size: int,
                   expected_sha256: str | None = None) -> dict:
    """Validate a *recorded* task-major, fixed-arm schedule without outcomes."""
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
    if payload.get("current", "missing") is not None:
        raise ChronologyError("progress has an unfinished current run")
    events = payload.get("events")
    if type(events) is not list or len(events) != len(EXPECTED_ORDER):
        raise ChronologyError("progress must contain exactly 40 recorded events")
    study_start = _utc(payload.get("started_at_utc"), "study start")
    study_end = _utc(payload.get("finished_at_utc"), "study finish")
    previous_finish = study_start
    for index, ((task, variant), event) in enumerate(zip(EXPECTED_ORDER, events, strict=True)):
        if type(event) is not dict:
            raise ChronologyError(f"progress event {index + 1} must be an object")
        if (event.get("task_id") != task or event.get("variant") != variant
                or event.get("status") != "completed" or "error" in event):
            raise ChronologyError(
                f"progress event {index + 1} violates original task-major fixed-arm order"
            )
        started = _utc(event.get("started_at_utc"), f"event {index + 1} start")
        finished = _utc(event.get("finished_at_utc"), f"event {index + 1} finish")
        if started < previous_finish or finished < started:
            raise ChronologyError(f"progress event {index + 1} timestamps overlap or reverse")
        previous_finish = finished
    if study_end < previous_finish:
        raise ChronologyError("study finish predates final event")
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
        "recorded_task_major_schedule": True,
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
    args = parser.parse_args(argv)
    payload, sha256, size = _capture_progress(args.progress_json)
    print(json.dumps(audit_progress(payload, sha256=sha256, byte_size=size,
                                    expected_sha256=args.expected_sha256),
                     indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

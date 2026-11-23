"""Offline, fail-closed completion triage for a single VERA 16-shard CI run.

This audits GitHub Actions *job metadata*, not pytest output or retained test
receipts. A successful replay job is necessary for completion, but inspecting
metadata alone never independently verifies the replay artifact's contents.
No network calls, treatments, evaluator calls, or experimental data are used.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

EXPECTED_SHARDS = 16
REPLAY_JOB = "replay-complete-shard-set"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 32
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
UTC_JOB_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
SHARD_RE = re.compile(r"unit-tests \(([0-9]+)\)\Z")


# Require every unconditional step in the pinned offline tests.yml jobs.
# A green pytest/receipt/upload chain cannot certify skipped runtime, dependency,
# compilation, or checkout prerequisites. Failure-only diagnostic upload remains
# optional. These are still same-provider step reports, not authenticated bytes.
REQUIRED_SHARD_STEPS = (
    "Checkout repository",
    "Set up Python",
    "Verify pinned CI Python runtime before tests",
    "Verify pinned Python before dependency-free diagnostic gate",
    "Verify exact checkout before dependency-free diagnostic gate",
    "Run dependency-free diagnostic invariants before pip installation",
    "Verify exact checkout after dependency-free diagnostic gate",
    "Bind dependency-free test transcript to commit and run",
    "Independently replay dependency-free evidence before retention",
    "Retain pre-install diagnostic evidence (90 days)",
    "Install application and test dependencies",
    "Verify installed CI dependencies before tests",
    "Compile research code",
    "Verify exact source checkout before tests",
    "Run offline unit tests",
    "Verify exact source checkout after tests",
    "Verify installed CI dependencies after tests",
    "Verify pinned CI Python runtime after tests",
    "Bind exact-commit offline test evidence",
    "Replay exact-commit offline test evidence before upload",
    "Retain source-bound offline test evidence (90 days)",
)
REQUIRED_REPLAY_STEPS = (
    "Checkout exact tested sources for full-set replay",
    "Set up pinned Python for full-set replay",
    "Verify Python and checkout before full-set replay",
    "Install exact pinned replay dependencies",
    "Verify pinned replay dependencies",
    "Download current-attempt shard evidence",
    "Stage exact-attempt shard directories",
    "Download exact-attempt pre-install diagnostic evidence",
    "Stage complete early diagnostic evidence set",
    "Independently replay all sixteen downloaded shard receipts",
    "Verify exact checkout after full-set replay",
    "Retain verified sixteen-shard replay (90 days)",
)

# These labels are GitHub-managed setup/cleanup steps (plus the declared
# failure-only diagnostic upload), not additional user-defined research steps.
# A successful job that reports any other unrecognized step cannot satisfy
# the source-bound workflow execution inventory.
SHARD_AUXILIARY_STEPS = frozenset({
    "Set up job",
    "Complete job",
    "Post Checkout repository",
    "Post Set up Python",
    "Retain unverified diagnostics on CI failure or cancellation (90 days)",
})
REPLAY_AUXILIARY_STEPS = frozenset({
    "Set up job",
    "Complete job",
    "Post Checkout exact tested sources for full-set replay",
    "Post Set up pinned Python for full-set replay",
})


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _json_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate jobs JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonstandard JSON number {value!r}")



def _require_json_container_depth(raw: bytes) -> None:
    """Bound JSON nesting before decoding externally supplied job metadata.

    Brackets inside quoted strings, including escaped quotes, are not nesting.
    This avoids uncontrolled parser recursion on byte-bounded hostile input.
    It does not authenticate GitHub job metadata or retained artifacts.
    """
    depth = 0
    quoted = False
    escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:  # Backslash.
                escaped = True
            elif char == 34:  # Closing double quote.
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):  # Opening square/curly bracket.
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("jobs JSON exceeds nesting limit")
        elif char in (93, 125):  # Closing square/curly bracket.
            depth -= 1
            if depth < 0:
                raise ValueError("jobs JSON has unmatched closing container")
    if depth != 0 or quoted:
        raise ValueError("jobs JSON has an incomplete container or string")


def load_jobs_json(path: Path) -> dict:
    """Read one bounded JSON snapshot; caller must independently trust its source."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("jobs JSON exceeds two-megabyte limit")
    _require_json_container_depth(raw)
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_json_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("jobs input must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("jobs JSON must be an object")
    return payload


def _require_successful_steps(
    job: dict, *, required: tuple[str, ...], auxiliary: frozenset[str]
) -> None:
    """Every mandatory step in a green job must succeed in declared workflow order."""
    name = job["name"]
    steps = job.get("steps")
    if not isinstance(steps, list):
        raise ValueError(f"{name}: successful job has no steps inventory")
    seen: dict[str, dict] = {}
    positions: dict[str, int] = {}
    last_number = 0
    for position, step in enumerate(steps):
        if not isinstance(step, dict) or not isinstance(step.get("name"), str) or not step["name"]:
            raise ValueError(f"{name}: malformed job step")
        label = step["name"]
        if label in seen:
            raise ValueError(f"{name}: duplicate job step {label!r}")
        if label not in required and label not in auxiliary:
            raise ValueError(f"{name}: unexpected successful-job step {label!r}")
        number = step.get("number")
        if type(number) is not int or number <= last_number:
            raise ValueError(f"{name}: malformed or out-of-order step number")
        last_number = number
        seen[label] = step
        positions[label] = position
    for label in required:
        step = seen.get(label)
        if step is None:
            raise ValueError(f"{name}: missing required successful step {label!r}")
        if step.get("status") != "completed" or step.get("conclusion") != "success":
            raise ValueError(f"{name}: required step did not succeed: {label!r}")
    # Names and green conclusions alone cannot certify that dependencies, tests,
    # replay, and retention appear in the actual required workflow sequence.
    if [positions[label] for label in required] != sorted(positions[label] for label in required):
        raise ValueError(f"{name}: required evidence steps out of execution order")


def _completed_job_window(job: dict) -> tuple[datetime, datetime]:
    """Parse provider UTC job times; a green replay must follow the shards."""
    times: list[datetime] = []
    for field in ("started_at", "completed_at"):
        value = job.get(field)
        if not isinstance(value, str) or not UTC_JOB_TIME_RE.fullmatch(value):
            raise ValueError(f"{job['name']}: missing or malformed {field} UTC timestamp")
        try:
            times.append(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError as exc:
            raise ValueError(f"{job['name']}: invalid {field} UTC timestamp") from exc
    if times[1] < times[0]:
        raise ValueError(f"{job['name']}: completed_at precedes started_at")
    return times[0], times[1]


def audit_jobs(payload: dict, *, run_id: int, run_attempt: int, commit: str) -> dict:
    """Classify exact-run jobs without upgrading partial pytest to verified CI."""
    run_id = _positive_int(run_id, "run_id")
    run_attempt = _positive_int(run_attempt, "run_attempt")
    if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
        raise ValueError("commit must be an exact lowercase 40-character SHA")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("jobs payload must contain a jobs array")
    jobs = payload["jobs"]
    if type(payload.get("total_count")) is not int or payload["total_count"] != len(jobs):
        raise ValueError("incomplete/paginated jobs inventory: total_count does not match jobs")
    seen_names: set[str] = set()
    seen_ids: set[int] = set()
    shard_conclusions: dict[int, str] = {}
    replay_conclusion: str | None = None
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("malformed job entry")
        name = job.get("name")
        if not isinstance(name, str) or name in seen_names:
            raise ValueError("duplicate or malformed CI job name")
        seen_names.add(name)
        job_id = _positive_int(job.get("id"), "job.id")
        if job_id in seen_ids:
            raise ValueError("duplicate GitHub Actions job ID")
        seen_ids.add(job_id)
        if (job.get("run_id"), job.get("run_attempt"), job.get("head_sha")) != (
            run_id, run_attempt, commit
        ):
            raise ValueError(f"{name}: mixed run, attempt, or checkout SHA")
        if job.get("status") not in {"queued", "in_progress", "completed", "waiting", "pending"}:
            raise ValueError(f"{name}: unsupported GitHub Actions job status")
        conclusion = job.get("conclusion")
        if conclusion is not None and conclusion not in {
            "success", "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral"
        }:
            raise ValueError(f"{name}: unsupported job conclusion")
        if job["status"] == "completed" and conclusion is None:
            raise ValueError(f"{name}: completed job without conclusion")
        if job["status"] != "completed" and conclusion is not None:
            raise ValueError(f"{name}: unfinished job with conclusion")
        if name == REPLAY_JOB:
            if conclusion == "success":
                _require_successful_steps(
                    job, required=REQUIRED_REPLAY_STEPS, auxiliary=REPLAY_AUXILIARY_STEPS
                )
            replay_conclusion = conclusion
        else:
            match = SHARD_RE.fullmatch(name)
            if not match or not 0 <= int(match.group(1)) < EXPECTED_SHARDS:
                raise ValueError(f"unexpected CI job {name!r}; refusing to infer completion")
            index = int(match.group(1))
            if index in shard_conclusions:
                raise ValueError(f"duplicate shard index {index}")
            if conclusion == "success":
                _require_successful_steps(
                    job, required=REQUIRED_SHARD_STEPS, auxiliary=SHARD_AUXILIARY_STEPS
                )
            shard_conclusions[index] = conclusion or "in_progress"
    if REPLAY_JOB not in seen_names:
        raise ValueError("missing full-set replay job metadata")
    passed = sorted(i for i, value in shard_conclusions.items() if value == "success")
    failed = sorted(i for i, value in shard_conclusions.items() if value in {"failure", "timed_out", "action_required"})
    cancelled = sorted(i for i, value in shard_conclusions.items() if value == "cancelled")
    other = sorted(i for i, value in shard_conclusions.items() if value not in {"success", "failure", "timed_out", "action_required", "cancelled"})
    missing = sorted(set(range(EXPECTED_SHARDS)) - shard_conclusions.keys())
    complete = (
        len(passed) == EXPECTED_SHARDS
        and not missing
        and replay_conclusion == "success"
    )
    if complete:
        # Step-by-step green conclusions must not certify a replay that
        # started before all sixteen shard jobs had finished and uploaded.
        # Incomplete/cancelled runs remain triageable without full timestamps.
        windows = {job["name"]: _completed_job_window(job) for job in jobs}
        replay_start = windows[REPLAY_JOB][0]
        if replay_start < max(windows[f"unit-tests ({i})"][1]
                              for i in range(EXPECTED_SHARDS)):
            raise ValueError("full-set replay started before all successful shards completed")
    return {
        "schema_version": 1,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "commit": commit,
        "source": "provided GitHub Actions jobs metadata; authenticity not independently attested",
        "successful_shards": passed,
        "failed_shards": failed,
        "cancelled_shards": cancelled,
        "other_incomplete_shards": other,
        "missing_shards": missing,
        "replay_job_conclusion": replay_conclusion or "in_progress",
        "full_job_gate_completed": complete,
        "retained_evidence_verified_by_this_tool": False,
        "research_result_or_human_validation": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-json", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    try:
        audit = audit_jobs(
            load_jobs_json(args.jobs_json),
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            commit=args.commit,
        )
    except (OSError, ValueError) as exc:
        print(f"CI job completion audit invalid: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(audit, sort_keys=True, indent=2))
    return 0 if audit["full_job_gate_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

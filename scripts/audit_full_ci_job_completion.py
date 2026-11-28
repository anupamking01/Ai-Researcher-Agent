"""Offline, fail-closed completion triage for a single VERA 16-shard CI run.

This audits GitHub Actions *job and workflow-run metadata*, not pytest output
or retained test receipts. The REST head SHA identifies the workflow source head,
not necessarily the runner checkout (pull requests can test a merge commit).
A successful replay job is necessary for completion, but inspecting metadata
alone never independently verifies the tested checkout or replay artifact.
No network calls, treatments, evaluator calls, or experimental data are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime
from pathlib import Path

EXPECTED_SHARDS = 16
REPLAY_JOB = "replay-complete-shard-set"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
UTC_JOB_TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
SHARD_RE = re.compile(r"unit-tests \((0|[1-9][0-9]?)\)\Z")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
RUN_URL_RE = re.compile(
    r"https://api\.github\.com/repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/actions/runs/([1-9][0-9]*)\Z"
)


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
SHARD_FAILURE_ONLY_STEP = "Retain unverified diagnostics on CI failure or cancellation (90 days)"
SHARD_AUXILIARY_STEPS = frozenset({
    "Set up job",
    "Complete job",
    "Post Checkout repository",
    "Post Set up Python",
    SHARD_FAILURE_ONLY_STEP,
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


def _file_generation(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _load_metadata_snapshot(path: Path) -> tuple[dict, str]:
    """Parse and fingerprint the same bounded raw bytes, without reopening the input."""
    path = Path(path)

    # Reject special files before opening them, then validate the opened
    # descriptor too. Nonblocking open prevents a FIFO substituted between
    # lstat and open from hanging the offline auditor.
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode):
        raise ValueError("metadata snapshot must be a regular file (not a symlink)")
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("metadata snapshot must be a regular file")
        if (expected.st_dev, expected.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("metadata snapshot replaced before capture")
        if _file_generation(expected) != _file_generation(opened):
            raise ValueError("metadata snapshot changed before capture")
        raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("jobs JSON exceeds two-megabyte limit")
        final = os.fstat(stream.fileno())
        if (_file_generation(opened) != _file_generation(final)
                or len(raw) != opened.st_size
                or _file_generation(final) != _file_generation(path.lstat())):
            raise ValueError("metadata snapshot changed during capture")
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
    return payload, hashlib.sha256(raw).hexdigest()


def load_jobs_json(path: Path) -> dict:
    """Read one bounded JSON snapshot; caller must independently trust its source."""
    payload, _ = _load_metadata_snapshot(path)
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
    # The shard diagnostic upload is guarded by "failure() || cancelled()"
    # in tests.yml. A successful shard cannot execute that conditional step.
    # Provider-managed setup/cleanup, when present, must also have succeeded:
    # green user-defined steps cannot mask skipped or failed housekeeping.
    for label in auxiliary:
        step = seen.get(label)
        if step is None:
            continue
        if label == SHARD_FAILURE_ONLY_STEP:
            if step.get("status") != "completed" or step.get("conclusion") != "skipped":
                raise ValueError(f"{name}: failure-only diagnostics must be skipped in successful job")
        elif step.get("status") != "completed" or step.get("conclusion") != "success":
            raise ValueError(f"{name}: provider housekeeping step did not succeed: {label!r}")
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


def _require_step_windows(job: dict, job_window: tuple[datetime, datetime]) -> None:
    """Check actual mandatory step chronology for a claim of full completion."""
    required = REQUIRED_REPLAY_STEPS if job["name"] == REPLAY_JOB else REQUIRED_SHARD_STEPS
    previous_end = job_window[0]
    for step in job["steps"]:
        if step["name"] not in required:
            continue
        # Reuse strict UTC parsing, but include the parent job in diagnostics.
        start, end = _completed_job_window({
            "name": f"{job['name']}: {step['name']}",
            "started_at": step.get("started_at"),
            "completed_at": step.get("completed_at"),
        })
        if start < job_window[0] or end > job_window[1]:
            raise ValueError(f"{job['name']}: required step lies outside job time window")
        if start < previous_end:
            raise ValueError(f"{job['name']}: required step overlaps previous required step")
        previous_end = end


def _cancelled_shard_progress(job: dict) -> dict:
    """Summarize reported mandatory-step progress, never infer cancellation cause.

    Cancelled jobs may have partial or missing step inventories. Malformed
    inventories remain classifiable as cancelled but yield no progress claim.
    Cleanup and diagnostic uploads are not mandatory execution progress.
    """
    unavailable = {
        "step_inventory_usable": False,
        "last_contiguous_successful_step": None,
        "first_unconfirmed_step": None,
        "first_unconfirmed_step_conclusion": None,
        "reported_cancelled_required_steps": [],
    }
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        return unavailable
    seen: dict[str, dict] = {}
    last_number = 0
    required_positions = []
    for step in steps:
        if not isinstance(step, dict):
            return unavailable
        label, number = step.get("name"), step.get("number")
        if (not isinstance(label, str) or not label or label in seen
                or type(number) is not int or number <= last_number):
            return unavailable
        last_number = number
        seen[label] = step
        if label in REQUIRED_SHARD_STEPS:
            required_positions.append(REQUIRED_SHARD_STEPS.index(label))
            conclusion, status = step.get("conclusion"), step.get("status")
            if "conclusion" not in step or not isinstance(status, str):
                return unavailable
            if conclusion is not None and (
                not isinstance(conclusion, str) or conclusion not in {
                    "success", "failure", "cancelled", "skipped", "timed_out",
                    "action_required", "neutral",
                }
            ):
                return unavailable
            if status not in {"queued", "in_progress", "completed", "waiting", "pending"}:
                return unavailable
            if (status == "completed") != (conclusion is not None):
                return unavailable
    if not required_positions or required_positions != sorted(required_positions):
        return unavailable

    last_success = first_unconfirmed = first_conclusion = None
    for label in REQUIRED_SHARD_STEPS:
        step = seen.get(label)
        if step is None or step["conclusion"] != "success":
            first_unconfirmed = label
            first_conclusion = step["conclusion"] if step is not None else None
            break
        last_success = label
    return {
        "step_inventory_usable": True,
        "last_contiguous_successful_step": last_success,
        "first_unconfirmed_step": first_unconfirmed,
        "first_unconfirmed_step_conclusion": first_conclusion,
        "reported_cancelled_required_steps": [
            label for label in REQUIRED_SHARD_STEPS
            if label in seen and seen[label]["conclusion"] == "cancelled"
        ],
    }


def audit_jobs(payload: dict, *, run_id: int, run_attempt: int, commit: str) -> dict:
    """Classify exact-run jobs without upgrading partial pytest to verified CI."""
    run_id = _positive_int(run_id, "run_id")
    run_attempt = _positive_int(run_attempt, "run_attempt")
    if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
        raise ValueError("workflow head SHA must be an exact lowercase 40-character SHA")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("jobs payload must contain a jobs array")
    jobs = payload["jobs"]
    if type(payload.get("total_count")) is not int or payload["total_count"] != len(jobs):
        raise ValueError("incomplete/paginated jobs inventory: total_count does not match jobs")
    seen_names: set[str] = set()
    seen_ids: set[int] = set()
    shard_conclusions: dict[int, str] = {}
    cancelled_progress: dict[int, dict] = {}
    replay_conclusion: str | None = None
    jobs_run_url: str | None = None
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
        if (type(job.get("run_id")) is not int or type(job.get("run_attempt")) is not int
                or (job.get("run_id"), job.get("run_attempt"), job.get("head_sha")) != (
                    run_id, run_attempt, commit
                )):
            raise ValueError(f"{name}: mixed run, attempt, or workflow head SHA")
        # The original jobs endpoint identifies its workflow and repository in
        # every job, even cancelled jobs. Do not accept contradictory identities.
        run_url = job.get("run_url")
        match_url = RUN_URL_RE.fullmatch(run_url) if isinstance(run_url, str) else None
        if job.get("workflow_name") != "tests" or match_url is None or match_url.group(2) != str(run_id):
            raise ValueError(f"{name}: unexpected job workflow or run URL")
        if jobs_run_url is not None and run_url != jobs_run_url:
            raise ValueError(f"{name}: mixed repository run URLs")
        jobs_run_url = run_url
        status = job.get("status")
        if not isinstance(status, str) or status not in {"queued", "in_progress", "completed", "waiting", "pending"}:
            raise ValueError(f"{name}: unsupported GitHub Actions job status")
        if "conclusion" not in job:
            raise ValueError(f"{name}: missing job conclusion field")
        conclusion = job["conclusion"]
        if conclusion is not None and (not isinstance(conclusion, str) or conclusion not in {
            "success", "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral"
        }):
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
            if conclusion == "cancelled":
                cancelled_progress[index] = _cancelled_shard_progress(job)
    if REPLAY_JOB not in seen_names:
        raise ValueError("missing full-set replay job metadata")
    passed = sorted(i for i, value in shard_conclusions.items() if value == "success")
    failed = sorted(i for i, value in shard_conclusions.items() if value in {"failure", "timed_out", "action_required"})
    cancelled = sorted(i for i, value in shard_conclusions.items() if value == "cancelled")
    pending = sorted(i for i, value in shard_conclusions.items() if value == "in_progress")
    other = sorted(i for i, value in shard_conclusions.items() if value not in {"success", "failure", "timed_out", "action_required", "cancelled", "in_progress"})
    missing = sorted(set(range(EXPECTED_SHARDS)) - shard_conclusions.keys())
    # The replay job has needs: unit-tests and no status override in
    # tests.yml. A successful replay cannot coexist with missing, pending,
    # or unsuccessful dependencies in this exact-attempt inventory.
    # Reject contradictory metadata rather than issuing an incomplete
    # receipt that nevertheless advertises successful aggregate replay.
    if replay_conclusion == "success" and len(passed) != EXPECTED_SHARDS:
        raise ValueError(
            "successful full-set replay contradicts incomplete shard dependencies; "
            "recapture the original attempt-specific jobs inventory"
        )
    complete = len(passed) == EXPECTED_SHARDS and replay_conclusion == "success"
    # A successful shard is an affirmative metadata claim even when its
    # siblings fail or are cancelled. Apply the same chronology contract
    # regardless of aggregate success; incomplete jobs need no timestamps.
    successful_jobs = [job for job in jobs if job["conclusion"] == "success"]
    windows = {job["name"]: _completed_job_window(job) for job in successful_jobs}
    if complete:
        replay_start = windows[REPLAY_JOB][0]
        if replay_start < max(windows[f"unit-tests ({i})"][1]
                              for i in range(EXPECTED_SHARDS)):
            raise ValueError("full-set replay started before all successful shards completed")
    for job in successful_jobs:
        _require_step_windows(job, windows[job["name"]])
    return {
        "schema_version": 1,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "commit": commit,  # Legacy alias for the REST head SHA, not a checkout claim.
        "workflow_head_sha": commit,
        "tested_checkout_sha_verified_by_this_tool": False,
        "jobs_run_url": jobs_run_url,
        "source": "provided GitHub Actions jobs metadata; authenticity not independently attested",
        "successful_shards": passed,
        "failed_shards": failed,
        "cancelled_shards": cancelled,
        "cancelled_shard_progress": [
            {"shard": index, **cancelled_progress[index]} for index in cancelled
        ],
        "pending_shards": pending,
        "other_incomplete_shards": other,
        "missing_shards": missing,
        "replay_job_conclusion": replay_conclusion or "in_progress",
        "full_job_gate_completed": complete,
        "retained_evidence_verified_by_this_tool": False,
        "research_result_or_human_validation": False,
    }


def audit_run_envelope(
    run: dict, job_audit: dict, *, run_id: int, run_attempt: int, commit: str
) -> dict:
    """Bind a complete job inventory to the overall GitHub workflow verdict.

    Job-step conclusions alone cannot certify a cancelled or unfinished run.
    Both inputs remain unauthenticated same-provider metadata, not evidence bytes.
    """
    if not isinstance(run, dict):
        raise ValueError("workflow run JSON must be an object")
    if (
        type(run.get("id")) is not int
        or type(run.get("run_attempt")) is not int
        or run["id"] != run_id
        or run["run_attempt"] != run_attempt
        or run.get("head_sha") != commit
    ):
        raise ValueError("workflow run metadata has mixed ID, attempt, or workflow head SHA")
    if run.get("name") != "tests" or run.get("path") != ".github/workflows/tests.yml":
        raise ValueError("unexpected workflow identity; expected tests.yml")
    # Cross-check the job audit against the actual run envelope, not merely
    # against caller-supplied IDs. This is metadata consistency, not authentication.
    repository = run.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    if not isinstance(full_name, str) or not REPOSITORY_RE.fullmatch(full_name):
        raise ValueError("workflow run metadata has invalid repository identity")
    expected_url = f"https://api.github.com/repos/{full_name}/actions/runs/{run_id}"
    if run.get("url") != expected_url or job_audit.get("jobs_run_url") != expected_url:
        raise ValueError("job inventory and workflow run repository URLs disagree")
    if (job_audit.get("run_id"), job_audit.get("run_attempt"), job_audit.get("commit"),
            job_audit.get("workflow_head_sha")) != (run_id, run_attempt, commit, commit):
        raise ValueError("job audit and workflow run identities disagree")
    event = run.get("event")
    if not isinstance(event, str) or event not in {"pull_request", "push", "workflow_dispatch"}:
        raise ValueError("unexpected workflow trigger")
    status = run.get("status")
    if "conclusion" not in run:
        raise ValueError("missing workflow conclusion field")
    conclusion = run["conclusion"]
    if not isinstance(status, str) or status not in {"requested", "waiting", "queued", "pending", "in_progress", "completed"}:
        raise ValueError("unsupported workflow status")
    if conclusion is not None and (not isinstance(conclusion, str) or conclusion not in {
        "success", "failure", "cancelled", "skipped", "timed_out",
        "action_required", "neutral", "startup_failure", "stale",
    }):
        raise ValueError("unsupported workflow conclusion")
    if (status == "completed") != (conclusion is not None):
        raise ValueError("inconsistent workflow status and conclusion")
    if conclusion == "success" and not job_audit["full_job_gate_completed"]:
        raise ValueError("successful workflow contradicts incomplete job inventory")
    # Separately captured endpoint snapshots can disagree while GitHub is
    # settling a run. Do not issue a settled-run receipt from stale job states.
    if status == "completed" and (
        job_audit["pending_shards"] or job_audit["replay_job_conclusion"] == "in_progress"
    ):
        raise ValueError("completed workflow contradicts unfinished job metadata; recapture both snapshots")
    result = dict(job_audit)
    result.update({
        "workflow_event": event,
        "workflow_status": status,
        "workflow_conclusion": conclusion or "in_progress",
        "workflow_source": "provided GitHub workflow-run metadata; authenticity not independently attested",
        "full_workflow_job_gate_completed": (
            job_audit["full_job_gate_completed"] and conclusion == "success"
        ),
    })
    return result


def audit_artifact_inventory(
    payload: dict, run: dict, *, successful_shards: list[int] | None = None
) -> dict:
    """Inventory exact-attempt artifact names, never certify archive contents.

    The run-wide endpoint includes previous attempts. Artifact names encode the
    attempt by workflow convention, not an independently attested attempt ID.
    When a job audit is supplied, reject failure-only artifacts for green shards.
    """
    run_id = _positive_int(run.get("id"), "run.id")
    attempt = _positive_int(run.get("run_attempt"), "run.run_attempt")
    repository = run.get("repository")
    repo_id = _positive_int(
        repository.get("id") if isinstance(repository, dict) else None,
        "run.repository.id",
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("artifacts"), list):
        raise ValueError("artifact inventory must contain an artifacts array")
    artifacts = payload["artifacts"]
    if type(payload.get("total_count")) is not int or payload["total_count"] != len(artifacts):
        raise ValueError("incomplete/paginated artifact inventory: total_count does not match artifacts")
    suffix = f"-{run_id}-{attempt}"
    groups = {
        "early_diagnostics": {
            f"vera-stdlib-evaluation-shard-{i}{suffix}": i for i in range(EXPECTED_SHARDS)
        },
        "offline_tests": {
            f"vera-offline-tests-shard-{i}{suffix}": i for i in range(EXPECTED_SHARDS)
        },
        "unverified_diagnostics": {
            f"vera-unverified-failure-shard-{i}{suffix}": i for i in range(EXPECTED_SHARDS)
        },
        "aggregate_replay": {f"vera-full-shard-replay{suffix}": "replay"},
    }
    expected = {name for group in groups.values() for name in group}
    seen_ids: set[int] = set()
    current: dict[str, dict] = {}
    excluded = 0
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("malformed artifact entry")
        artifact_id = _positive_int(artifact.get("id"), "artifact.id")
        if artifact_id in seen_ids:
            raise ValueError("duplicate artifact ID")
        seen_ids.add(artifact_id)
        name = artifact.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("malformed artifact name")
        if type(artifact.get("expired")) is not bool:
            raise ValueError("artifact expired flag must be boolean")
        lineage = artifact.get("workflow_run")
        if (not isinstance(lineage, dict)
                or type(lineage.get("id")) is not int
                or type(lineage.get("repository_id")) is not int
                or (lineage.get("id"), lineage.get("repository_id"), lineage.get("head_sha"))
                != (run_id, repo_id, run.get("head_sha"))):
            raise ValueError("artifact inventory has mixed workflow run, repository or head SHA")
        if name not in expected:
            excluded += 1
            continue
        if name in current:
            raise ValueError(f"duplicate exact-attempt artifact name {name!r}")
        digest = artifact.get("digest")
        if digest is not None and (not isinstance(digest, str)
                                   or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
            raise ValueError("invalid provider artifact SHA-256 digest")
        size = artifact.get("size_in_bytes")
        if size is not None and (type(size) is not int or size < 0):
            raise ValueError("invalid provider artifact size_in_bytes")
        current[name] = artifact
    # The reviewed workflow can only upload this diagnostic on failure or
    # cancellation. Its presence (even expired) contradicts a successful
    # shard in the same attempt. Previous-attempt names were excluded above.
    if successful_shards is not None:
        contradictory = sorted(
            index for name, index in groups["unverified_diagnostics"].items()
            if name in current and index in successful_shards
        )
        if contradictory:
            raise ValueError(
                f"failure-only artifacts contradict successful shards: {contradictory}; "
                "recapture the original attempt-specific metadata"
            )
    # Keep exact artifact identities for a later independent archive download.
    # The digest is provider-declared metadata, not a digest of locally read bytes.
    result = {}
    for group, names in groups.items():
        result[group] = {
            "listed_unexpired": [index for name, index in names.items()
                                 if name in current and not current[name]["expired"]],
            "listed_expired": [index for name, index in names.items()
                               if name in current and current[name]["expired"]],
            "missing": [index for name, index in names.items() if name not in current],
        }
    return {
        "artifact_inventory": result,
        "excluded_artifact_count": excluded,
        # Stable ordering is independent of the API pagination/order. Missing
        # or null legacy digest/size fields remain unknown, not verified.
        "listed_artifact_identities": [
            {
                "group": group,
                "slot": index,
                "name": name,
                "artifact_id": current[name]["id"],
                "expired": current[name]["expired"],
                "provider_declared_digest": current[name].get("digest"),
                "provider_declared_size_in_bytes": current[name].get("size_in_bytes"),
            }
            for group, names in groups.items()
            for name, index in names.items()
            if name in current
        ],
        "full_artifact_inventory_listed_unexpired": all(
            not result[group]["missing"] and not result[group]["listed_expired"]
            for group in ("early_diagnostics", "offline_tests", "aggregate_replay")
        ),
        "artifact_inventory_source": (
            "provided run-wide GitHub artifact metadata; attempt inferred from names; "
            "availability and archive bytes not independently verified"
        ),
    }


def _audit_artifact_upload_windows(payload: dict, jobs: dict, inventory: dict) -> dict:
    """Compare creation timestamps with the exact successful retention steps.

    Call only after job and artifact inventories have been validated. Incomplete
    jobs can have partial uploads; do not infer their upload chronology.
    """
    successful = {job["name"]: job for job in jobs["jobs"]
                  if job["conclusion"] == "success"}
    artifacts = {item["id"]: item for item in payload["artifacts"]}
    labels = {
        "early_diagnostics": "Retain pre-install diagnostic evidence (90 days)",
        "offline_tests": "Retain source-bound offline test evidence (90 days)",
        "aggregate_replay": "Retain verified sixteen-shard replay (90 days)",
    }
    matched, unchecked = [], []
    for item in inventory["listed_artifact_identities"]:
        group, slot, artifact_id = item["group"], item["slot"], item["artifact_id"]
        job_name = REPLAY_JOB if group == "aggregate_replay" else f"unit-tests ({slot})"
        job = successful.get(job_name)
        if group not in labels or job is None:
            unchecked.append(artifact_id)
            continue
        step = next(step for step in job["steps"] if step["name"] == labels[group])
        start, end = _completed_job_window(step)
        created = artifacts[artifact_id].get("created_at")
        instant, _ = _completed_job_window({
            "name": f"artifact {artifact_id} created_at",
            "started_at": created, "completed_at": created,
        })
        if not start <= instant <= end:
            raise ValueError(
                f"artifact {artifact_id} creation outside successful upload step window"
            )
        matched.append(artifact_id)
    return {
        "artifact_upload_window_matched_ids": sorted(matched),
        "artifact_upload_window_unchecked_ids": sorted(unchecked),
        "artifact_upload_window_scope": (
            "provider creation time within corresponding successful retention step; "
            "not independent attestation of upload identity or attempt"
        ),
    }


def _capture_archive_digest(path: Path) -> tuple[str, int]:
    """Hash bounded raw bytes from one regular file without extracting it."""
    expected = path.lstat()
    if not stat.S_ISREG(expected.st_mode):
        raise ValueError("artifact archive must be a regular file (not a symlink)")
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("artifact archive must be a regular file")
        if (expected.st_dev, expected.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("artifact archive replaced before capture")
        if _file_generation(expected) != _file_generation(opened):
            raise ValueError("artifact archive changed before capture")
        if opened.st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("artifact archive exceeds byte limit")
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError("artifact archive exceeds byte limit")
            digest.update(chunk)
        final = os.fstat(stream.fileno())
        if (_file_generation(opened) != _file_generation(final)
                or size != opened.st_size
                or _file_generation(final) != _file_generation(path.lstat())):
            raise ValueError("artifact archive changed during capture")
    return "sha256:" + digest.hexdigest(), size


def audit_local_archive_digests(inventory: dict, directory: Path) -> dict:
    """Compare local ID-named downloads to provider digests and known sizes."""
    if not stat.S_ISDIR(directory.lstat().st_mode):
        raise ValueError("archive directory must be a directory (not a symlink)")
    comparisons = []
    for item in inventory["listed_artifact_identities"]:
        if item["group"] == "unverified_diagnostics":
            continue
        path = directory / f"{item['artifact_id']}.zip"
        observed, size = None, None
        try:
            path.lstat()
        except FileNotFoundError:
            status = "missing_local_archive"
        else:
            observed, size = _capture_archive_digest(path)
            declared = item["provider_declared_digest"]
            if declared is None:
                status = "provider_digest_unavailable"
            elif declared != observed:
                status = "mismatch"
            elif (item["provider_declared_size_in_bytes"] is not None
                  and item["provider_declared_size_in_bytes"] != size):
                status = "provider_size_mismatch"
            else:
                status = "match"
        comparisons.append({
            "artifact_id": item["artifact_id"],
            "name": item["name"],
            "status": status,
            "local_digest": observed,
            "local_size_in_bytes": size,
        })
    # Availability at the provider and the identity of retained local bytes
    # are different facts. Expiration cannot invalidate an already saved ZIP.
    full_local_match = (
        len(comparisons) == 2 * EXPECTED_SHARDS + 1
        and all(item["status"] == "match" for item in comparisons)
    )
    return {
        "local_archive_digest_comparisons": comparisons,
        "full_local_archive_bytes_match": full_local_match,
        "full_archive_digest_match": (
            inventory["full_artifact_inventory_listed_unexpired"] and full_local_match
        ),
        "archive_digest_scope": (
            "local raw bytes compared with provider-declared digests and known sizes; "
            "archive contents, source checkout and provider authenticity not verified"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-json", type=Path, required=True)
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--artifacts-json", type=Path, help="optional complete run-wide artifact inventory")
    parser.add_argument("--archives-dir", type=Path, help="optional local downloads named by artifact ID (<id>.zip)")
    parser.add_argument(
        "--historical-local-archives", action="store_true",
        help="require all local archive bytes to match, even if provider listing reports expiration",
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--head-sha", dest="commit", help="REST run/job head_sha, not necessarily the tested checkout SHA")
    identity.add_argument("--commit", dest="commit", help="legacy alias for --head-sha")
    args = parser.parse_args(argv)
    try:
        if args.historical_local_archives and args.archives_dir is None:
            raise ValueError("--historical-local-archives requires --archives-dir")
        if args.archives_dir is not None and args.artifacts_json is None:
            raise ValueError("--archives-dir requires --artifacts-json")
        jobs, jobs_sha256 = _load_metadata_snapshot(args.jobs_json)
        job_audit = audit_jobs(
            jobs,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            commit=args.commit,
        )
        run, run_sha256 = _load_metadata_snapshot(args.run_json)
        audit = audit_run_envelope(
            run, job_audit,
            run_id=args.run_id, run_attempt=args.run_attempt, commit=args.commit,
        )
        if args.artifacts_json is not None:
            artifacts, artifacts_sha256 = _load_metadata_snapshot(args.artifacts_json)
            audit.update(audit_artifact_inventory(
                artifacts, run, successful_shards=audit["successful_shards"]
            ))
            audit.update(_audit_artifact_upload_windows(artifacts, jobs, audit))
            audit["artifacts_json_sha256"] = artifacts_sha256
            if args.archives_dir is not None:
                audit.update(audit_local_archive_digests(audit, args.archives_dir))
    except (OSError, ValueError) as exc:
        print(f"CI job completion audit invalid: {exc}", file=sys.stderr)
        return 2
    # A receipt binds the exact parsed snapshots, not reserialized JSON or a
    # second read that might capture different bytes. This is identification,
    # not independent authentication of the source or retained evidence.
    audit.update({
        "jobs_json_sha256": jobs_sha256,
        "run_json_sha256": run_sha256,
    })
    if args.historical_local_archives:
        audit["archive_gate_mode"] = "historical_local_bytes"
        archive_gate = audit["full_local_archive_bytes_match"]
    else:
        archive_gate = (
            audit.get("full_artifact_inventory_listed_unexpired", True)
            and audit.get("full_archive_digest_match", True)
        )
    print(json.dumps(audit, sort_keys=True, indent=2))
    return 0 if audit["full_workflow_job_gate_completed"] and archive_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())

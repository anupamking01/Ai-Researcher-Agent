"""Audit contemporaneous GitHub Actions ZIP digests from original job logs.

This is an offline, fail-closed comparison of two *caller-supplied* workflow
logs against Git-committed historical GitHub upload metadata. It never downloads
an artifact, reads report contents, runs models, or establishes independent
archive custody. The GitHub service produced both logs and the original ZIP
digests; a matching log excerpt is not an out-of-band signed attestation.
"""
from __future__ import annotations

import argparse
import calendar
from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat

MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_LOG_LINES = 15000
REPOSITORY = "anupamking01/Ai-Researcher-Agent"

# The original GitHub job-log endpoint returns a UTF-8 BOM at the beginning
# and renders upload-artifact's multi-line "path:" input with one timestamp
# followed by ten UNSTAMPED continuation lines. These precise historical
# input lines are allowed only immediately after the stamped first path line,
# inside an upload-artifact v4 step. Other unframed lines remain errors.
_UPLOAD_PATH_CONTINUATION = (
    "outputs/main_study_progress.json",
    "outputs/main_study_summary.json",
    "outputs/main_study_runs.csv",
    "outputs/posthoc_support_summary.json",
    "outputs/posthoc_support_runs.csv",
    "outputs/posthoc_evaluations/**",
    "outputs/experiment_traces/**",
    "outputs/*/research_report.md",
    "outputs/*/research-query-*.txt",
    "outputs/*/verification.json",
)
_UPLOAD_PATH_HEAD = "  path: outputs/main_study_manifest.json"

# Recorded from the upload-artifact v4 and download-artifact v4 job steps on
# 2026-09-11 and 2026-09-13. These are contemporaneous, GitHub-service-reported
# ZIP metadata, *not* independently archived report/trace fingerprints.
ORIGINAL = {
    "role": "original_treatment",
    "run_id": 34620917346,
    "job_id": 103334373932,
    "artifact_name": "budget-main-study-34620917346",
    "artifact_id": 10275100801,
    "size_bytes": 608355,
    "zip_sha256": "878205ff42267b85d71f478520a4a3ebe520915f22ae2d2307e930fa39545400",
}
RECOVERED = {
    "role": "evaluator_recovery",
    "run_id": 34783525480,
    "job_id": 103794737655,
    "artifact_name": "budget-main-study-recovered-34783525480",
    "artifact_id": 10324954205,
    "size_bytes": 618586,
    "zip_sha256": "c357b068fa4c0b7e86f7c56cd1d3e346f6922106d7bde644db92feb7f8fc84cc",
}
_LOG_LINE = re.compile(
    r"(?P<stamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,9}Z) (?P<message>.*)\Z"
)
_HEX = r"[0-9a-f]{64}"

# Pinned, second-precision run_started_at / updated_at values from GitHub
# Actions workflow metadata, not independently archived execution evidence.
# The end-of-second ceiling avoids rejecting a legitimate log event only
# because GitHub's workflow timestamp omits fractional seconds.
HISTORICAL_WORKFLOW_WINDOWS = {
    ORIGINAL["run_id"]: (
        "2026-09-11T16:15:15.000000000Z",
        "2026-09-11T17:22:43.999999999Z",
    ),
    RECOVERED["run_id"]: (
        "2026-09-13T21:20:32.000000000Z",
        "2026-09-13T21:21:40.999999999Z",
    ),
}


class HistoricalLogError(ValueError):
    """Logs cannot support the claimed historical GitHub ZIP metadata."""


def _event_time_ns(timestamp: str) -> int:
    """Parse action-log UTC timestamps with all nine fractional digits preserved."""
    try:
        seconds = datetime.strptime(timestamp[:19], "%Y-%m-%dT%H:%M:%S")
        nanoseconds = int(timestamp[20:-1].ljust(9, "0"))
    except ValueError as exc:
        raise HistoricalLogError("invalid GitHub job-log UTC event timestamp") from exc
    return calendar.timegm(seconds.timetuple()) * 1_000_000_000 + nanoseconds


def _require_event_chronology(events: list[tuple[int, str, re.Match]], label: str) -> None:
    """Log lines alone do not establish event-time order or a valid calendar date."""
    instants = [_event_time_ns(event[1]) for event in events]
    if any(later < earlier for earlier, later in zip(instants, instants[1:])):
        raise HistoricalLogError(f"{label}: GitHub event timestamps are out of order")


def _require_workflow_window(
    events: list[tuple[int, str, re.Match]], *, run_id: int,
) -> None:
    """Bind claimed job-log events to their recorded Actions workflow window."""
    start, end = HISTORICAL_WORKFLOW_WINDOWS[run_id]
    minimum, maximum = _event_time_ns(start), _event_time_ns(end)
    if any(not minimum <= _event_time_ns(event[1]) <= maximum for event in events):
        raise HistoricalLogError(
            f"GitHub job-log event outside pinned workflow window for run {run_id}"
        )


def _require_action_step_chronology(
    step: list[tuple[str, str]], *, run_id: int, label: str,
) -> None:
    """Check every timestamped line in the action step, not just digest events.

    The GitHub job logger emits other timestamped messages between the pinned
    events. Their chronology must not contradict the lineage receipt merely
    because the digest/ID messages remain ordered. These caller-supplied logs
    are still not independently authenticated.
    """
    all_events = [(index, stamp, None) for index, (stamp, _) in enumerate(step)]
    _require_event_chronology(all_events, label)
    _require_workflow_window(all_events, run_id=run_id)


def _bounded_lines(content: str, label: str) -> list[tuple[str, str]]:
    if type(content) is not str or len(content.encode("utf-8")) > MAX_LOG_BYTES:
        raise HistoricalLogError(f"{label} log is not bounded UTF-8 text")
    lines = content.splitlines()
    if len(lines) > MAX_LOG_LINES:
        raise HistoricalLogError(f"{label} log has too many lines")
    result = []
    in_upload_step = False
    path_block_seen = False
    pending_path_index = None
    for line_number, line in enumerate(lines, 1):
        # GitHub's raw job-log download has a single UTF-8 BOM at byte zero.
        # A BOM anywhere else is not a permitted second log framing prefix.
        if line_number == 1 and line.startswith("\ufeff"):
            line = line[1:]
        if pending_path_index is not None:
            # These are the only unframed lines accepted: the literal, ordered
            # upload-artifact@v4 path input from the two pinned original runs.
            # Never interpret an arbitrary continuation as an action event.
            if line != _UPLOAD_PATH_CONTINUATION[pending_path_index]:
                raise HistoricalLogError(
                    f"{label} log has unexpected upload-artifact path continuation "
                    f"at line {line_number}"
                )
            pending_path_index += 1
            if pending_path_index == len(_UPLOAD_PATH_CONTINUATION):
                pending_path_index = None
            continue
        if not line:
            continue
        # The only permitted BOM is removed from byte zero above. A later
        # BOM inside a timestamped message could disguise a second log header.
        if "\ufeff" in line:
            raise HistoricalLogError(
                f"{label} log contains an unframed or malformed timestamped line "
                f"at line {line_number}"
            )
        match = _LOG_LINE.fullmatch(line)
        if match is None:
            raise HistoricalLogError(
                f"{label} log contains an unframed or malformed timestamped line "
                f"at line {line_number}"
            )
        message = match["message"]
        if message == "##[group]Run actions/upload-artifact@v4":
            in_upload_step = True
        elif message.startswith("##[group]Run ") or message == "Post job cleanup.":
            in_upload_step = False
        if message == _UPLOAD_PATH_HEAD:
            if not in_upload_step or path_block_seen:
                raise HistoricalLogError(
                    f"{label} log has an unexpected upload-artifact path input"
                )
            path_block_seen = True
            pending_path_index = 0
        result.append((match["stamp"], message))
    if pending_path_index is not None:
        raise HistoricalLogError(
            f"{label} log has a truncated upload-artifact path continuation"
        )
    return result



def _require_historical_job_envelope(
    content: str, *, run_id: int, label: str,
) -> None:
    """Check the observed opening/terminal markers of each pinned Actions job.

    A digest-bearing excerpt can pass action-step checks despite omitting the
    rest of the GitHub job. These markers identify a *plausibly bounded* job
    transcript, not completeness of its middle or independent authentication.
    Synthetic in-memory step fixtures use audit_historical_job_logs directly;
    the CLI additionally enforces these full-job envelope markers.
    """
    if run_id not in HISTORICAL_WORKFLOW_WINDOWS:
        raise HistoricalLogError("unknown historical job-log envelope")
    lines = _bounded_lines(content, label)
    if not lines or lines[0][1] != "Current runner version: '2.337.0'":
        raise HistoricalLogError(f"{label}: missing pinned GitHub runner opening marker")
    openings = [
        index for index, (_, message) in enumerate(lines)
        if message.startswith("Current runner version:")
    ]
    if openings != [0]:
        raise HistoricalLogError(f"{label}: duplicate or relocated runner opening marker")
    cleanups = [
        index for index, (_, message) in enumerate(lines)
        if message == "Cleaning up orphan processes"
    ]
    uploads = [
        index for index, (_, message) in enumerate(lines)
        if message.startswith(
            f"Artifact download URL: https://github.com/{REPOSITORY}"
            f"/actions/runs/{run_id}/artifacts/"
        )
    ]
    if len(cleanups) != 1 or len(uploads) != 1 or cleanups[0] <= uploads[0]:
        raise HistoricalLogError(
            f"{label}: missing or misplaced terminal cleanup after artifact upload"
        )
    warning_prefix = (
        "##[warning]Node.js 20 is deprecated. The following actions target "
        "Node.js 20 but are being forced to run on Node.js 24:"
    )
    warnings = [
        index for index, (_, message) in enumerate(lines)
        if message.startswith(warning_prefix)
    ]
    if warnings != [len(lines) - 1] or warnings[0] <= cleanups[0]:
        raise HistoricalLogError(
            f"{label}: missing or misplaced pinned terminal job-log warning"
        )


def _action_step(lines: list[tuple[str, str]], action: str) -> list[tuple[str, str]]:
    marker = f"##[group]Run actions/{action}@v4"
    starts = [n for n, (_, message) in enumerate(lines) if message == marker]
    if len(starts) != 1:
        raise HistoricalLogError(f"expected exactly one {action} v4 action step")
    start = starts[0]
    end = None
    for n in range(start + 1, len(lines)):
        message = lines[n][1]
        if message.startswith("##[group]Run ") or message == "Post job cleanup.":
            end = n
            break
    if end is None:
        raise HistoricalLogError(
            f"{action} v4 action step has no following workflow boundary"
        )
    # A digest-bearing excerpt with no subsequent step/cleanup marker may be
    # truncated. Include the observed boundary in the chronological and run-
    # window checks; otherwise a reversed or future boundary escapes review.
    return lines[start:end + 1]


def _one(step: list[tuple[str, str]], pattern: str, label: str) -> tuple[int, str, re.Match]:
    found = [
        (index, stamp, match)
        for index, (stamp, message) in enumerate(step)
        if (match := re.fullmatch(pattern, message))
    ]
    if len(found) != 1:
        raise HistoricalLogError(f"{label}: expected exactly one matching action event")
    return found[0]


def _upload(step: list[tuple[str, str]], expected: dict) -> dict:
    _require_action_step_chronology(
        step, run_id=expected["run_id"], label="artifact upload action step"
    )
    name = re.escape(expected["artifact_name"])
    digest = _one(
        step, rf"SHA256 digest of uploaded artifact zip is (?P<sha>{_HEX})",
        "upload ZIP digest",
    )
    finalized = _one(
        step, rf"Artifact {name}\.zip successfully finalized\. Artifact ID (?P<id>\d+)",
        "artifact finalization",
    )
    success = _one(
        step,
        rf"Artifact {name} has been successfully uploaded! Final size is "
        rf"(?P<size>\d+) bytes\. Artifact ID is (?P<id>\d+)",
        "completed artifact upload",
    )
    url = _one(
        step,
        rf"Artifact download URL: https://github\.com/{re.escape(REPOSITORY)}"
        rf"/actions/runs/{expected['run_id']}/artifacts/(?P<id>\d+)",
        "artifact run-scoped URL",
    )
    if not digest[0] < finalized[0] < success[0] < url[0]:
        raise HistoricalLogError("artifact upload events occur in unexpected order")
    _require_event_chronology([digest, finalized, success, url], "artifact upload")
    _require_workflow_window([digest, finalized, success, url], run_id=expected["run_id"])
    if (
        digest[2]["sha"] != expected["zip_sha256"]
        or any(int(event[2]["id"]) != expected["artifact_id"] for event in (finalized, success, url))
        or int(success[2]["size"]) != expected["size_bytes"]
    ):
        raise HistoricalLogError("historical upload differs from pinned GitHub job-log metadata")
    return {
        **expected,
        "upload_digest_logged_at_utc": digest[1],
        "upload_completed_logged_at_utc": success[1],
        "upload_url_logged_at_utc": url[1],
        "source": "GitHub Actions upload-artifact@v4 job log",
    }


def _download(step: list[tuple[str, str]]) -> dict:
    _require_action_step_chronology(
        step, run_id=RECOVERED["run_id"], label="recovery download action step"
    )
    expected = ORIGINAL
    name = re.escape(expected["artifact_name"])
    announced = _one(
        step, rf"- {name} \(ID: (?P<id>\d+), Size: (?P<size>\d+), "
        rf"Expected Digest: sha256:(?P<sha>{_HEX})\)",
        "recovery download announcement",
    )
    source = _one(
        step,
        rf"Downloading artifact '(?P<id>\d+)' from '{re.escape(REPOSITORY)}'",
        "recovery repository identity",
    )
    observed = _one(
        step, rf"SHA256 digest of downloaded artifact is (?P<sha>{_HEX})",
        "recovery observed ZIP digest",
    )
    complete = _one(
        step, r"Artifact download completed successfully\.",
        "recovery download completion",
    )
    count = _one(step, r"Total of 1 artifact\(s\) downloaded", "single recovered download")
    if not announced[0] < source[0] < observed[0] < complete[0] < count[0]:
        raise HistoricalLogError("recovery download events occur in unexpected order")
    _require_event_chronology([announced, source, observed, complete, count], "recovery download")
    _require_workflow_window([announced, source, observed, complete, count], run_id=RECOVERED["run_id"])
    if (
        int(announced[2]["id"]) != expected["artifact_id"]
        or int(source[2]["id"]) != expected["artifact_id"]
        or int(announced[2]["size"]) != expected["size_bytes"]
        or announced[2]["sha"] != expected["zip_sha256"]
        or observed[2]["sha"] != expected["zip_sha256"]
    ):
        raise HistoricalLogError("evaluator recovery download does not match original ZIP metadata")
    return {
        "from_run_id": expected["run_id"],
        "to_run_id": RECOVERED["run_id"],
        "artifact_id": expected["artifact_id"],
        "zip_sha256": expected["zip_sha256"],
        "download_announced_logged_at_utc": announced[1],
        "observed_download_logged_at_utc": observed[1],
        "download_count_logged_at_utc": count[1],
        "source": "GitHub Actions download-artifact@v4 job log",
    }


def audit_historical_job_logs(original_log: str, recovery_log: str) -> dict:
    """Validate two historical log transcripts without inferring archive survival."""
    original_lines = _bounded_lines(original_log, "original treatment")
    recovery_lines = _bounded_lines(recovery_log, "evaluator recovery")
    # Validate the complete timestamped job transcript, not only the selected
    # ZIP-bearing action steps. Raw uploads include other stamped steps before
    # and after the archive events; contradictory clock events there also
    # weaken the claimed GitHub-service lineage.
    for lines, run_id, label in (
        (original_lines, ORIGINAL["run_id"], "original treatment job log"),
        (recovery_lines, RECOVERED["run_id"], "evaluator recovery job log"),
    ):
        events = [(index, stamp, None) for index, (stamp, _) in enumerate(lines)]
        _require_event_chronology(events, label)
        _require_workflow_window(events, run_id=run_id)
    treatment = _upload(_action_step(original_lines, "upload-artifact"), ORIGINAL)
    download = _download(_action_step(recovery_lines, "download-artifact"))
    recovered = _upload(_action_step(recovery_lines, "upload-artifact"), RECOVERED)
    # Even when all recorded SHA-256 digests agree, a transcript claiming that
    # the original upload occurred after its recovery download (or that the
    # recovered ZIP was uploaded before that download) is not provenance.
    if not (
        _event_time_ns(treatment["upload_url_logged_at_utc"])
        <= _event_time_ns(download["download_announced_logged_at_utc"])
        and _event_time_ns(download["download_count_logged_at_utc"])
        <= _event_time_ns(recovered["upload_digest_logged_at_utc"])
    ):
        raise HistoricalLogError("historical GitHub event chronology contradicts archive lineage")
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "historical_github_job_log_zip_lineage_corresponds_not_authenticated",
        "original_treatment_upload": treatment,
        "evaluator_recovery_download": download,
        "evaluator_recovery_upload": recovered,
        "two_workflow_github_log_digest_concordance": True,
        "logs_independently_authenticated": False,
        "original_zip_downloadability_checked": False,
        "original_zip_currently_downloadable": None,
        "original_report_trace_bytes_inspected": False,
        "historical_treatment_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
        "interpretation": (
            "GitHub Actions originally logged ZIP bytes/digests and evaluator recovery "
            "later logged a matching original ZIP download. The input transcripts "
            "remain caller-supplied GitHub-service evidence, not an independently "
            "signed or externally preserved archive, not present-day availability, "
            "and not an original trace/report content or human-evaluation proof."
        ),
    }


def _read_log(path: Path) -> str:
    """Read one bounded stable regular file, refusing symlinks and pipe hangs."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        # Caller-supplied historical logs are not independently authenticated.
        # Still reject mutable aliases and any partial descriptor read: a
        # truncated transcript could omit contradictory event timestamps.
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= MAX_LOG_BYTES
        ):
            raise HistoricalLogError(
                "job log must be a bounded single-link regular file"
            )
        raw = handle.read(MAX_LOG_BYTES + 1)
        after = os.fstat(handle.fileno())
        path_stat = os.stat(path, follow_symlinks=False)
        identity = lambda s: (
            s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns,
        )
        if (
            len(raw) != before.st_size
            or identity(before) != identity(after)
            or identity(after) != identity(path_stat)
        ):
            raise HistoricalLogError("job log changed or was truncated during read")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HistoricalLogError("job log is not UTF-8 text") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-job-log", type=Path, required=True)
    parser.add_argument("--recovery-job-log", type=Path, required=True)
    args = parser.parse_args()
    try:
        original_log = _read_log(args.original_job_log)
        recovery_log = _read_log(args.recovery_job_log)
        _require_historical_job_envelope(
            original_log, run_id=ORIGINAL["run_id"], label="original treatment",
        )
        _require_historical_job_envelope(
            recovery_log, run_id=RECOVERED["run_id"], label="evaluator recovery",
        )
        receipt = audit_historical_job_logs(original_log, recovery_log)
        receipt["pinned_job_opening_and_terminal_markers_matched"] = True
    except (OSError, HistoricalLogError) as exc:
        parser.exit(1, f"VERA HISTORICAL JOB-LOG LINEAGE: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

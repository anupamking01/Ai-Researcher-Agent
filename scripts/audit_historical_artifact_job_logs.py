"""Audit contemporaneous GitHub Actions ZIP digests from original job logs.

This is an offline, fail-closed comparison of two *caller-supplied* workflow
logs against Git-committed historical GitHub upload metadata. It never downloads
an artifact, reads report contents, runs models, or establishes independent
archive custody. The GitHub service produced both logs and the original ZIP
digests; a matching log excerpt is not an out-of-band signed attestation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat

MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_LOG_LINES = 15000
REPOSITORY = "anupamking01/Ai-Researcher-Agent"

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


class HistoricalLogError(ValueError):
    """Logs cannot support the claimed historical GitHub ZIP metadata."""


def _bounded_lines(content: str, label: str) -> list[tuple[str, str]]:
    if type(content) is not str or len(content.encode("utf-8")) > MAX_LOG_BYTES:
        raise HistoricalLogError(f"{label} log is not bounded UTF-8 text")
    lines = content.splitlines()
    if len(lines) > MAX_LOG_LINES:
        raise HistoricalLogError(f"{label} log has too many lines")
    result = []
    for line in lines:
        match = _LOG_LINE.fullmatch(line)
        if match:
            result.append((match["stamp"], match["message"]))
    return result


def _action_step(lines: list[tuple[str, str]], action: str) -> list[tuple[str, str]]:
    marker = f"##[group]Run actions/{action}@v4"
    starts = [n for n, (_, message) in enumerate(lines) if message == marker]
    if len(starts) != 1:
        raise HistoricalLogError(f"expected exactly one {action} v4 action step")
    start = starts[0]
    end = len(lines)
    for n in range(start + 1, len(lines)):
        message = lines[n][1]
        if message.startswith("##[group]Run ") or message == "Post job cleanup.":
            end = n
            break
    return lines[start:end]


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
        "source": "GitHub Actions upload-artifact@v4 job log",
    }


def _download(step: list[tuple[str, str]]) -> dict:
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
        "observed_download_logged_at_utc": observed[1],
        "source": "GitHub Actions download-artifact@v4 job log",
    }


def audit_historical_job_logs(original_log: str, recovery_log: str) -> dict:
    """Validate two historical log transcripts without inferring archive survival."""
    original_lines = _bounded_lines(original_log, "original treatment")
    recovery_lines = _bounded_lines(recovery_log, "evaluator recovery")
    treatment = _upload(_action_step(original_lines, "upload-artifact"), ORIGINAL)
    download = _download(_action_step(recovery_lines, "download-artifact"))
    recovered = _upload(_action_step(recovery_lines, "upload-artifact"), RECOVERED)
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
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_LOG_BYTES:
            raise HistoricalLogError("job log must be a bounded regular file")
        raw = handle.read(MAX_LOG_BYTES + 1)
        after = os.fstat(handle.fileno())
        path_stat = os.stat(path, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) > MAX_LOG_BYTES or identity(before) != identity(after) or identity(after) != identity(path_stat):
            raise HistoricalLogError("job log changed or exceeded limit during read")
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
        receipt = audit_historical_job_logs(
            _read_log(args.original_job_log),
            _read_log(args.recovery_job_log),
        )
    except (OSError, HistoricalLogError) as exc:
        parser.exit(1, f"VERA HISTORICAL JOB-LOG LINEAGE: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

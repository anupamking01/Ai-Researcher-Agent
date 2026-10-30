"""Read-only 40-cell treatment/report inventory for a recovered VERA Actions ZIP.

Runs the bounded structural ZIP preflight first, then compares *member paths*
with the fingerprint-pinned, published common-evaluator run identities. This
does not extract archives, inspect trace/report semantics, create artifacts,
authenticate independent custody, or authorize blinded human evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from scripts import build_human_eval_packet as packet_builder
from scripts import preflight_recovered_artifact_zip as preflight
from scripts import verify_human_eval_automated_run_lineage as lineage

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CELLS = {
    (variant, task) for variant in lineage.VARIANTS for task in lineage.TASKS
}


class RecoveryMatrixError(ValueError):
    """The candidate ZIP does not contain the published 40-cell source matrix."""


def _generation(path: Path) -> tuple[int, ...]:
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise RecoveryMatrixError("published evaluator input is not a regular file")
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns,
    )


def _capture_evaluator(path: Path) -> tuple[bytes, tuple[int, ...]]:
    """Read one stable file generation without following a leaf symlink."""
    before = _generation(path)
    raw = packet_builder._read_regular_file_captured(
        path, label="published post-hoc evaluator run-identity CSV"
    )
    after = _generation(path)
    if before != after:
        raise RecoveryMatrixError("published evaluator CSV changed during capture")
    if hashlib.sha256(raw).hexdigest() != packet_builder.PUBLISHED_EVALUATOR_CSV_SHA256:
        raise RecoveryMatrixError("published evaluator CSV differs from frozen input fingerprint")
    return raw, after


def _expected_paths(csv_bytes: bytes, *, csv_path: Path) -> tuple[set[str], set[str]]:
    rows = lineage._read_study_csv(csv_bytes, path=csv_path)
    matrix = lineage._matrix(
        rows, label="published post-hoc evaluator",
        expected_cells=EXPECTED_CELLS, run_identity=True,
    )
    traces = {
        f"experiment_traces/{variant}/{row['run_id']}.json"
        for (variant, _task), row in matrix.items()
    }
    reports = {
        f"{row['run_id']}/research_report.md"
        for row in matrix.values()
    }
    if len(traces) != 40 or len(reports) != 40:
        raise RecoveryMatrixError("published evaluator does not define 40 distinct source pairs")
    return traces, reports


def _verify_member_paths(
    names: set[str], *, traces: set[str], reports: set[str],
) -> str:
    """Require all sources and reject any unselected trace or report member.

    GitHub upload-artifact normally drops the shared outputs/ parent. Accept
    that layout or an explicit outputs/ parent, but never mix the two.
    """
    matches = []
    for prefix in ("", "outputs/"):
        if ({prefix + name for name in traces} | {prefix + name for name in reports}) <= names:
            matches.append(prefix)
    if len(matches) != 1:
        raise RecoveryMatrixError(
            "candidate ZIP does not contain exactly one complete published "
            "40-trace/40-report path layout"
        )
    prefix = matches[0]
    expected = {prefix + name for name in traces | reports}
    unselected = {
        name for name in names
        if (
            name.startswith("experiment_traces/")
            or "/experiment_traces/" in name
            or name.endswith("/research_report.md")
        ) and name not in expected
    }
    if unselected:
        raise RecoveryMatrixError(
            "candidate ZIP includes unselected treatment traces or Markdown reports"
        )
    return prefix


def audit_recovered_treatment_matrix(
    archive: Path, *, artifact_role: str, repo_root: Path = REPO_ROOT,
    expected_archive_sha256: str | None = None,
) -> dict:
    """Verify ZIP layout against 40 published execution IDs, without extraction.

    The historical GitHub job-log role is mandatory: this check cannot turn a
    plausible, newly constructed ZIP into an authenticated original archive.
    A caller-supplied independent pin is separate from the GitHub same-provider
    digest, and must have been retained before recovery to be provenance.
    """
    if type(artifact_role) is not str or artifact_role not in preflight.GITHUB_JOB_LOG_ARCHIVES:
        raise RecoveryMatrixError("choose a pinned historical GitHub artifact role")
    csv_path = Path(repo_root) / lineage.SUPPORT_REL
    csv_bytes, csv_generation = _capture_evaluator(csv_path)
    traces, reports = _expected_paths(csv_bytes, csv_path=csv_path)
    archive_receipt = preflight.audit_recovered_zip(
        Path(archive), expected_archive_sha256=expected_archive_sha256,
        github_job_log_artifact=artifact_role,
    )
    names = {entry["path"] for entry in archive_receipt["files"]}
    layout_prefix = _verify_member_paths(names, traces=traces, reports=reports)
    # The ZIP preflight can be lengthy. Do not authorize a result from an
    # evaluator CSV which changed or was replaced during archive inspection.
    csv_rechecked, generation_rechecked = _capture_evaluator(csv_path)
    if (csv_rechecked, generation_rechecked) != (csv_bytes, csv_generation):
        raise RecoveryMatrixError("published evaluator CSV changed during ZIP inspection")
    return {
        "schema_version": 1,
        "status": "zip_40_treatment_sources_match_published_run_ids_not_authenticated",
        "artifact_role": artifact_role,
        "source_layout_prefix": layout_prefix,
        "published_evaluator_csv_sha256": packet_builder.PUBLISHED_EVALUATOR_CSV_SHA256,
        "published_evaluator_source": lineage.SUPPORT_REL,
        "trace_members_matched": len(traces),
        "report_members_matched": len(reports),
        "unselected_trace_or_report_members": 0,
        "zip_preflight_status": archive_receipt["status"],
        "zip_sha256_observed_now": archive_receipt["archive_sha256_observed_now"],
        "github_job_log_zip_correspondence": archive_receipt["github_job_log_zip_correspondence"],
        "independent_zip_pin_supplied_and_matched": archive_receipt["expected_archive_sha256_matched"],
        "trace_contents_verified": False,
        "report_contents_verified": False,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
        "interpretation": (
            "Offline ZIP member-path completeness and published automated-run "
            "identity correspondence only. Neither same-provider GitHub log "
            "digests nor member paths authenticate historical trace/report "
            "contents or independent archive custody. Human evaluation is blocked."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="authorized recovered ZIP; never extracted")
    parser.add_argument(
        "--artifact-role", choices=tuple(preflight.GITHUB_JOB_LOG_ARCHIVES),
        required=True, help="pin archive to the original historical GitHub job-log identity",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--expected-archive-sha256",
        help="optional independently retained historical ZIP-byte fingerprint",
    )
    args = parser.parse_args()
    try:
        result = audit_recovered_treatment_matrix(
            args.archive, artifact_role=args.artifact_role,
            repo_root=args.repo_root,
            expected_archive_sha256=args.expected_archive_sha256,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"VERA RECOVERED MATRIX: FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

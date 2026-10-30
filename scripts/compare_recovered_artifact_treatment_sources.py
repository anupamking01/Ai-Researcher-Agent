"""Compare original/recovery treatment sources in two historical VERA ZIPs.

The source bytes must be unchanged across evaluator-only recovery. Both ZIPs
are individually checked against GitHub's *same-provider* historical job-log
fingerprints before comparing all 40 trace/report hashes. A match is NOT an
independent historical custody attestation or permission to distribute human
evaluation packets. No extraction, evaluator runs, or treatments occur.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from scripts import audit_recovered_artifact_treatment_matrix as matrix
from scripts import preflight_recovered_artifact_zip as preflight


class RecoveryConcordanceError(ValueError):
    """Original and evaluator-recovery experimental sources differ."""


def _archive_source_snapshot(path: Path) -> tuple[tuple[int, ...], str]:
    """Capture a stable, no-follow ZIP generation and its current byte digest.

    Unlike each individual ZIP preflight, this snapshot also bounds the
    *combined* two-archive comparison window. It does not authenticate custody.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            pathname = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or not preflight._unchanged(before, pathname):
                raise RecoveryConcordanceError(
                    "archive source must be an unchanged regular file, not a link"
                )
            if not 0 < before.st_size <= preflight.MAX_ARCHIVE_BYTES:
                raise RecoveryConcordanceError("archive source size outside preflight bounds")
            digest = preflight._fingerprint(handle)
            if (
                not preflight._unchanged(before, os.fstat(handle.fileno()))
                or not preflight._unchanged(before, os.stat(path, follow_symlinks=False))
            ):
                raise RecoveryConcordanceError("archive changed during source snapshot")
    except OSError as exc:
        raise RecoveryConcordanceError(
            f"cannot safely capture archive source {path}: {exc}"
        ) from exc
    generation = (
        before.st_dev, before.st_ino, before.st_mode, before.st_size,
        before.st_mtime_ns, before.st_ctime_ns,
    )
    return generation, digest


def compare_recovered_treatment_sources(
    original_archive: Path,
    recovery_archive: Path,
    *,
    repo_root: Path = matrix.REPO_ROOT,
    original_expected_archive_sha256: str | None = None,
    recovery_expected_archive_sha256: str | None = None,
) -> dict:
    """Check distinct role-pinned ZIPs have identical frozen source bytes.

    Independently retained archive pins are optional caller claims, not inferred
    from the recovered archives or from GitHub's own job logs.
    """
    original_archive = Path(original_archive)
    recovery_archive = Path(recovery_archive)
    if original_archive.samefile(recovery_archive):
        raise RecoveryConcordanceError(
            "original and recovery inputs must be distinct archive files"
        )
    # Snapshot all three governing sources before either expensive archive audit.
    # Individual per-ZIP custody checks cannot detect a source replaced in the
    # gap between two otherwise successful independent audits.
    original_start = _archive_source_snapshot(original_archive)
    recovery_start = _archive_source_snapshot(recovery_archive)
    evaluator_path = Path(repo_root) / matrix.lineage.SUPPORT_REL
    evaluator_start = matrix._capture_evaluator(evaluator_path)
    original = matrix.audit_recovered_treatment_matrix(
        original_archive,
        artifact_role="original_treatment",
        repo_root=repo_root,
        expected_archive_sha256=original_expected_archive_sha256,
    )
    recovered = matrix.audit_recovered_treatment_matrix(
        recovery_archive,
        artifact_role="evaluator_recovery",
        repo_root=repo_root,
        expected_archive_sha256=recovery_expected_archive_sha256,
    )
    original_manifest = original["observed_source_content_manifest"]
    recovered_manifest = recovered["observed_source_content_manifest"]
    before = original_manifest["cells"]
    after = recovered_manifest["cells"]
    differences = []
    for left, right in zip(before, after):
        identity = (left["treatment"], left["task_id"], left["run_id"])
        if identity != (right["treatment"], right["task_id"], right["run_id"]):
            raise RecoveryConcordanceError("published treatment identities differ")
        for source in ("trace", "report"):
            fields = (f"{source}_sha256", f"{source}_uncompressed_bytes")
            if any(left[field] != right[field] for field in fields):
                differences.append((identity, source))
    # Recheck both ZIPs and the frozen evaluator after *both* audits, including
    # replacement by a new inode containing the same bytes. Validate the
    # preflight digests against the initial snapshots as well.
    original_end = _archive_source_snapshot(original_archive)
    recovery_end = _archive_source_snapshot(recovery_archive)
    evaluator_end = matrix._capture_evaluator(evaluator_path)
    if (
        original_start != original_end
        or recovery_start != recovery_end
        or evaluator_start != evaluator_end
        or original["zip_sha256_observed_now"] != original_start[1]
        or recovered["zip_sha256_observed_now"] != recovery_start[1]
        or original_archive.samefile(recovery_archive)
    ):
        raise RecoveryConcordanceError(
            "original, recovery, or evaluator source changed during comparison"
        )
    if differences:
        sample = ", ".join(
            f"{treatment}/{task}/{run_id}:{source}"
            for (treatment, task, run_id), source in differences[:5]
        )
        raise RecoveryConcordanceError(
            f"original and evaluator-recovery source bytes differ in "
            f"{len(differences)} treatment source(s): {sample}"
        )
    if (
        len(before) != 40
        or len(after) != 40
        or original_manifest != recovered_manifest
        or original["observed_source_content_manifest_sha256"]
        != recovered["observed_source_content_manifest_sha256"]
    ):
        raise RecoveryConcordanceError("40-cell source manifest concordance failed")
    return {
        "schema_version": 1,
        "status": "original_and_evaluator_recovery_40_source_pairs_match_not_authenticated",
        "source_cells_compared": 40,
        "trace_sources_unchanged": 40,
        "report_sources_unchanged": 40,
        "source_content_manifest_sha256": original[
            "observed_source_content_manifest_sha256"
        ],
        "published_evaluator_csv_sha256": original[
            "published_evaluator_csv_sha256"
        ],
        "original_zip_sha256_observed_now": original["zip_sha256_observed_now"],
        "recovery_zip_sha256_observed_now": recovered["zip_sha256_observed_now"],
        "original_github_job_log_correspondence": original[
            "github_job_log_zip_correspondence"
        ],
        "recovery_github_job_log_correspondence": recovered[
            "github_job_log_zip_correspondence"
        ],
        "caller_claimed_independent_original_zip_pin_matched": original[
            "caller_claimed_independent_zip_pin_matched"
        ],
        "caller_claimed_independent_recovery_zip_pin_matched": recovered[
            "caller_claimed_independent_zip_pin_matched"
        ],
        "independent_archive_custody_verified": False,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
        "interpretation": (
            "Both candidate ZIPs match their separate historical GitHub job-log "
            "fingerprints and have exactly equal decompressed trace/report source "
            "bytes for 40 frozen run identities. Same-provider log anchors and "
            "present-day comparisons do not prove independently retained custody, "
            "historical report authenticity, or human-evaluation readiness."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-zip", required=True, type=Path)
    parser.add_argument("--recovery-zip", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=matrix.REPO_ROOT)
    parser.add_argument(
        "--original-expected-archive-sha256",
        help="optional independently retained original ZIP-byte fingerprint",
    )
    parser.add_argument(
        "--recovery-expected-archive-sha256",
        help="optional independently retained recovery ZIP-byte fingerprint",
    )
    args = parser.parse_args()
    try:
        result = compare_recovered_treatment_sources(
            args.original_zip,
            args.recovery_zip,
            repo_root=args.repo_root,
            original_expected_archive_sha256=args.original_expected_archive_sha256,
            recovery_expected_archive_sha256=args.recovery_expected_archive_sha256,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"VERA RECOVERED SOURCE CONCORDANCE: FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

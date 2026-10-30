"""Compare original/recovery treatment sources in two historical VERA ZIPs.

The source bytes must be unchanged across evaluator-only recovery. Both ZIPs
are individually checked against GitHub's *same-provider* historical job-log
fingerprints before comparing all 40 trace/report hashes. A match is NOT an
independent historical custody attestation or permission to distribute human
evaluation packets. No extraction, evaluator runs, or treatments occur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

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



# The original 2026-09-13 evaluator-only recovery workflow explicitly
# documented this missing set before any recovery evaluator calls. It is
# an operational lineage anchor, not a new research-analysis selection.
RECOVERY_ONLY_EVALUATOR_CELLS = frozenset({
    ("P6V", "main-02"),
    ("P6V", "main-08"),
    ("P6V", "main-10"),
})


def _evaluator_cache_map(
    audit: dict, expected_cells: set[tuple[str, str]],
) -> dict[tuple[str, str], tuple[str, int]]:
    """Locate all evaluator caches without ignoring alternate ZIP layouts."""
    prefix = audit["source_layout_prefix"]
    expected_paths = {
        f"{prefix}posthoc_evaluations/{variant}/{task}": (variant, task)
        for variant, task in expected_cells
    }
    expected_paths = {
        path + ".json": identity for path, identity in expected_paths.items()
    }
    observed = {}
    for member in audit["observed_evaluator_cache_members"]:
        path = member["path"]
        if path not in expected_paths:
            raise RecoveryConcordanceError(
                "unselected or mixed-layout evaluator cache member: " + path
            )
        identity = expected_paths[path]
        if identity in observed:
            raise RecoveryConcordanceError("duplicate evaluator cache identity")
        observed[identity] = (member["sha256"], member["uncompressed_bytes"])
    return observed


def _verify_evaluator_cache_continuity(
    original: dict, recovered: dict,
) -> tuple[int, int]:
    """Check 37 historical evaluator caches survived the 3-cell resume.

    This checks decompressed bytes and membership, not whether any evaluator
    JSON is semantically valid or independently authentic.
    """
    cells = original["observed_source_content_manifest"]["cells"]
    expected = {(cell["treatment"], cell["task_id"]) for cell in cells}
    if len(expected) != 40 or not RECOVERY_ONLY_EVALUATOR_CELLS <= expected:
        raise RecoveryConcordanceError("frozen evaluator cell matrix is incomplete")
    original_cache = _evaluator_cache_map(original, expected)
    recovery_cache = _evaluator_cache_map(recovered, expected)
    preserved = expected - RECOVERY_ONLY_EVALUATOR_CELLS
    if set(original_cache) != preserved:
        raise RecoveryConcordanceError(
            "original evaluator cache is not the historical 37-cell partial state"
        )
    if set(recovery_cache) != expected:
        raise RecoveryConcordanceError(
            "recovered evaluator cache is not the complete 40-cell state"
        )
    for identity in sorted(preserved):
        if original_cache[identity] != recovery_cache[identity]:
            raise RecoveryConcordanceError(
                "preserved evaluator cache bytes changed for "
                + "/".join(identity)
            )
    return len(preserved), len(RECOVERY_ONLY_EVALUATOR_CELLS)



# A recovered cache record is expected to be small. Bound the second, semantic
# inspection independently of the already-bounded structural ZIP preflight.
MAX_EVALUATOR_CACHE_JSON_BYTES = 4 * 1024 * 1024


def _unique_json_pairs(pairs: list[tuple[str, object]]) -> dict:
    """Do not let JSON's last-key-wins behavior spoof evaluator identities."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryConcordanceError("duplicate key in evaluator cache JSON")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> None:
    raise RecoveryConcordanceError(
        "nonfinite numeric token in evaluator cache JSON: " + value
    )


def _verify_evaluator_cache_json_identities(archive: Path, audit: dict) -> int:
    """Bind every archived evaluator record to its frozen execution identity.

    Only JSON well-formedness, nonambiguity, schema version, and identity are
    checked here. Score arithmetic, evidence fingerprints, prompt inputs, and
    correctness are governed by separate published evaluation audits.
    """
    cells = audit["observed_source_content_manifest"]["cells"]
    expected_run_ids = {
        (cell["treatment"], cell["task_id"]): cell["run_id"]
        for cell in cells
    }
    if len(cells) != 40 or len(expected_run_ids) != 40:
        raise RecoveryConcordanceError("frozen evaluator run identities are incomplete")
    cache = _evaluator_cache_map(audit, set(expected_run_ids))
    prefix = audit["source_layout_prefix"]
    try:
        with zipfile.ZipFile(archive, "r") as source:
            for (variant, task), (expected_digest, size) in sorted(cache.items()):
                path = f"{prefix}posthoc_evaluations/{variant}/{task}.json"
                if not 0 < size <= MAX_EVALUATOR_CACHE_JSON_BYTES:
                    raise RecoveryConcordanceError(
                        "evaluator cache JSON size outside semantic audit bound: " + path
                    )
                with source.open(path, "r") as member:
                    raw = member.read(size + 1)
                if len(raw) != size or hashlib.sha256(raw).hexdigest() != expected_digest:
                    raise RecoveryConcordanceError(
                        "evaluator cache bytes disagree with verified ZIP scan: " + path
                    )
                try:
                    payload = json.loads(
                        raw.decode("utf-8"),
                        object_pairs_hook=_unique_json_pairs,
                        parse_constant=_reject_nonfinite_json,
                    )
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RecoveryConcordanceError(
                        "invalid evaluator cache JSON: " + path
                    ) from exc
                if type(payload) is not dict:
                    raise RecoveryConcordanceError(
                        "evaluator cache JSON must be an object: " + path
                    )
                if (
                    type(payload.get("schema_version")) is not int
                    or payload["schema_version"] not in (1, 2)
                ):
                    raise RecoveryConcordanceError(
                        "evaluator cache JSON schema_version must be 1 or 2: " + path
                    )
                expected_identity = {
                    "study_id": "budget-main-v1",
                    "variant_id": variant,
                    "task_id": task,
                    "run_id": expected_run_ids[(variant, task)],
                }
                for field, expected in expected_identity.items():
                    if payload.get(field) != expected:
                        raise RecoveryConcordanceError(
                            f"evaluator cache {field} differs from frozen run: {path}"
                        )
    except (zipfile.BadZipFile, KeyError) as exc:
        raise RecoveryConcordanceError(
            "evaluator cache member cannot be read from verified ZIP"
        ) from exc
    return len(cache)


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
    # Evaluator-only recovery must add exactly the three declared missing
    # cache cells, without rewriting any of the 37 preserved JSON outputs.
    # This cannot be inferred from treatment-source hashes alone.
    preserved_count, new_count = _verify_evaluator_cache_continuity(
        original, recovered,
    )
    original_identity_count = _verify_evaluator_cache_json_identities(
        original_archive, original,
    )
    recovered_identity_count = _verify_evaluator_cache_json_identities(
        recovery_archive, recovered,
    )
    # The second ZIP read must be inside the same source-generation custody
    # window. A change during JSON inspection cannot authorize this receipt.
    if (
        _archive_source_snapshot(original_archive) != original_start
        or _archive_source_snapshot(recovery_archive) != recovery_start
        or matrix._capture_evaluator(evaluator_path) != evaluator_start
    ):
        raise RecoveryConcordanceError(
            "original, recovery, or evaluator source changed during comparison"
        )
    return {
        "schema_version": 1,
        "status": "original_and_evaluator_recovery_40_source_pairs_match_not_authenticated",
        "source_cells_compared": 40,
        "trace_sources_unchanged": 40,
        "report_sources_unchanged": 40,
        "preserved_evaluator_cache_members_byte_identical": preserved_count,
        "recovery_only_evaluator_cache_members_present": new_count,
        "original_evaluator_cache_json_identities_checked": original_identity_count,
        "recovery_evaluator_cache_json_identities_checked": recovered_identity_count,
        "evaluator_cache_json_duplicate_keys_rejected": True,
        "recovery_only_evaluator_cells": [
            {"treatment": variant, "task_id": task}
            for variant, task in sorted(RECOVERY_ONLY_EVALUATOR_CELLS)
        ],
        "evaluator_cache_payload_semantics_verified": False,
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
            "bytes for 40 frozen run identities; 37 pre-existing evaluator "
            "cache JSON byte streams also match, and only the three historically "
            "missing evaluator cache members appear in recovery. This checks "
            "cache membership, byte continuity, and JSON/schema/run identity "
            "for 37 original plus 40 recovered caches. This does not verify "
            "score arithmetic, evidence inputs, or correctness. Same-provider "
            "log anchors and "
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

"""Offline, read-only concordance check for the retained canonical-analysis ZIP.

A passing result shows that the archive contains the seven published analysis
files. Six must byte-match the currently verified checkout; the provenance
receipt may instead match the exact historical v1 member observed in GitHub's
canonical artifact. This is a provider-observed pin, not independent custody
or authentication of original treatment traces or reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts import analyze_main_study_task_influence as custody
from scripts import preflight_recovered_artifact_zip as zip_preflight

ROOT = Path(__file__).resolve().parents[1]
# Frozen upload set from canonical-main-study-analysis run 36070798723.
CANONICAL_MEMBERS = (
    "outputs/canonical_analysis_source.json",
    "outputs/main_study_analysis_inputs_manifest.json",
    "outputs/main_study_analysis_provenance.json",
    "outputs/main_study_inference.json",
    "outputs/main_study_runs.csv",
    "outputs/posthoc_support_runs.csv",
    "paper/MAIN_STUDY_INFERENCE.md",
)

PROVENANCE_RECEIPT = "outputs/main_study_analysis_provenance.json"
# Observed in artifact 10837878458 of canonical workflow 36070798723
# (downloaded on 2026-10-29, GitHub-reported ZIP sha256:
# 226f009ba6b158b77fc98f4e56ec96e1943d1749bc818b0876e90f76077de4b5).
# The uploaded receipt was schema v1. Later, the checked-in receipt became
# schema v2 as provenance checks were strengthened; its bytes must not be
# misrepresented as the exact historical ZIP member. This pin is derived from
# GitHub's retained artifact, NOT an independent pre-existing historical hash.
PUBLISHED_ARCHIVED_PROVENANCE_SHA256 = (
    "73f12a725f3cf4d27748a95e1f380ca5cfcac3b8fdd5adeda7abaa2f3f6e10e0"
)


def _capture_checkout(root: Path) -> dict[str, bytes]:
    return {
        relative: custody._read_regular_bounded(
            root / relative, label=f"canonical snapshot {relative}"
        )
        for relative in CANONICAL_MEMBERS
    }


def verify_archive_against_checkout(
    archive_path: Path,
    *,
    root: Path = ROOT,
    expected_archive_sha256: str | None = None,
) -> dict:
    """Bind a candidate archived snapshot to a checked, existing canonical tree.

    Capture the checkout on both sides of the upstream provenance verification
    and ZIP scan. These comparisons detect observable mutation; they are not
    an atomic filesystem snapshot or an independent historical attestation.
    """
    root = Path(root)
    before = _capture_checkout(root)
    custody.run_verified(root)
    if before != _capture_checkout(root):
        raise ValueError("canonical checkout changed during upstream verification")

    inspected = zip_preflight.audit_recovered_zip(
        Path(archive_path), expected_archive_sha256=expected_archive_sha256
    )
    if before != _capture_checkout(root):
        raise ValueError("canonical checkout changed during archive verification")

    members = inspected["files"]
    paths = [member["path"] for member in members]
    expected = set(CANONICAL_MEMBERS)
    if len(paths) != len(expected) or set(paths) != expected:
        raise ValueError(
            "canonical ZIP member set differs from the seven published snapshot files: "
            f"missing={sorted(expected - set(paths))}, "
            f"unexpected={sorted(set(paths) - expected)}"
        )

    mismatched = []
    match_basis = {}
    for member in members:
        path = member["path"]
        source = before[path]
        if (
            member["uncompressed_bytes"] == len(source)
            and member["sha256"] == hashlib.sha256(source).hexdigest()
        ):
            match_basis[path] = "verified_checkout"
        elif (
            path == PROVENANCE_RECEIPT
            and member["sha256"] == PUBLISHED_ARCHIVED_PROVENANCE_SHA256
        ):
            # The retained workflow ZIP has a v1 provenance receipt, whereas
            # today's verified checkout contains an expanded v2 receipt.
            # Only the exact observed historical receipt bytes are exempted;
            # all six substantive analysis inputs/outputs still must match.
            match_basis[path] = "pinned_github_workflow_v1_receipt"
        else:
            mismatched.append(path)
    if mismatched:
        raise ValueError(
            "canonical ZIP file bytes differ from the verified checkout or "
            "pinned published provenance receipt: "
            + ", ".join(sorted(mismatched))
        )

    used_historical_receipt = (
        match_basis[PROVENANCE_RECEIPT] == "pinned_github_workflow_v1_receipt"
    )
    archive_by_path = {member["path"]: member for member in members}
    return {
        "schema_version": 2,
        "status": (
            "canonical_archive_matches_checkout_and_pinned_historical_receipt_not_original_evidence"
            if used_historical_receipt
            else "canonical_archive_matches_verified_checkout_not_original_evidence"
        ),
        "historical_workflow_receipt_exception_used": used_historical_receipt,
        "historical_workflow_receipt_pin_source": (
            "github_retained_artifact_10837878458_observed_2026-10-29"
            if used_historical_receipt else None
        ),
        "archived_provenance_receipt_sha256": archive_by_path[
            PROVENANCE_RECEIPT
        ]["sha256"],
        "archive_sha256_observed_now": inspected["archive_sha256_observed_now"],
        "independently_supplied_archive_pin_matched": inspected[
            "expected_archive_sha256_matched"
        ],
        "verified_checkout_inference_sha256": hashlib.sha256(
            before["outputs/main_study_inference.json"]
        ).hexdigest(),
        "verified_checkout_provenance_receipt_sha256": hashlib.sha256(
            before["outputs/main_study_analysis_provenance.json"]
        ).hexdigest(),
        "matched_files": [
            {
                "path": relative,
                "bytes": archive_by_path[relative]["uncompressed_bytes"],
                "sha256": archive_by_path[relative]["sha256"],
                "match_basis": match_basis[relative],
            }
            for relative in CANONICAL_MEMBERS
        ],
        "original_treatment_traces_authenticated": False,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "human_ratings_generated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="retained canonical ZIP, never extracted")
    parser.add_argument("--root", type=Path, default=ROOT, help="published canonical checkout")
    parser.add_argument(
        "--expected-archive-sha256",
        help="optional independently retained ZIP-byte pin, not computed during this check",
    )
    args = parser.parse_args()
    try:
        result = verify_archive_against_checkout(
            args.archive,
            root=args.root,
            expected_archive_sha256=args.expected_archive_sha256,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"CANONICAL ARCHIVE CONCORDANCE: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline, read-only concordance check for the retained canonical-analysis ZIP.

A passing result shows that the structurally inspected archive contains exactly
the seven published canonical-analysis snapshot files, with bytes identical to
a provenance-verified checkout. It does NOT authenticate original treatments
or establish historical custody, and it cannot replace missing original reports.
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
    for member in members:
        source = before[member["path"]]
        if (
            member["uncompressed_bytes"] != len(source)
            or member["sha256"] != hashlib.sha256(source).hexdigest()
        ):
            mismatched.append(member["path"])
    if mismatched:
        raise ValueError(
            "canonical ZIP file bytes differ from the verified checkout: "
            + ", ".join(sorted(mismatched))
        )

    return {
        "schema_version": 1,
        "status": "canonical_archive_matches_verified_checkout_not_original_evidence",
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
                "bytes": len(before[relative]),
                "sha256": hashlib.sha256(before[relative]).hexdigest(),
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

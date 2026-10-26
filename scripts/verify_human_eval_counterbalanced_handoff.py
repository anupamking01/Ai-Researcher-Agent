"""Verify a pair of independently source-bound, counterordered annotator bundles.

Coordinator-only pre-distribution check. No ratings, blinding key, experimental
runs, or treatment-level outputs are read or produced by this module.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from scripts import export_human_eval_annotator_bundle as exporter


def verify_counterbalanced_handoff(
    *,
    packet_root: Path,
    canonical_root: Path,
    reverse_root: Path,
    expected_coordinator_manifest_sha256: str,
    expected_n_reports: int = 40,
    task_manifest_path: Path = exporter.DEFAULT_TASK_MANIFEST,
    repo_root: Path = exporter.REPO_ROOT,
    annotator_guide_path: Path = exporter.DEFAULT_ANNOTATOR_GUIDE,
) -> dict:
    """Require both distribution orders to derive from one externally pinned packet.

    The coordinator must retain the expected manifest SHA-256 independently
    before this verification. Each existing source-bound verifier snapshots and
    rechecks its bundle; this gate checks the pair, not independent human identity.
    """
    if (
        not isinstance(expected_coordinator_manifest_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_coordinator_manifest_sha256) is None
    ):
        raise ValueError("expected coordinator manifest SHA-256 must be 64 lowercase hex digits")
    if type(expected_n_reports) is not int or expected_n_reports < 1:
        raise ValueError("expected report count must be a positive integer")

    canonical_root, reverse_root = Path(canonical_root), Path(reverse_root)
    # Reject the same directory or a symlink alias before making two claims
    # of separately provisioned presentation-order bundles.
    try:
        if canonical_root.samefile(reverse_root):
            raise ValueError("counterbalanced handoff requires two distinct bundle directories")
    except FileNotFoundError:
        # The underlying source-bound verifier will report missing artifacts.
        pass

    common = {
        "packet_root": Path(packet_root),
        "task_manifest_path": Path(task_manifest_path),
        "repo_root": Path(repo_root),
        "annotator_guide_path": Path(annotator_guide_path),
    }
    receipts = {
        "canonical": exporter.verify_annotator_bundle_against_source(
            output_root=canonical_root,
            expected_presentation_order="canonical",
            **common,
        ),
        "reverse": exporter.verify_annotator_bundle_against_source(
            output_root=reverse_root,
            expected_presentation_order="reverse",
            **common,
        ),
    }
    for order, receipt in receipts.items():
        if receipt.get("source_bound_to_verified_coordinator") is not True:
            raise ValueError(f"{order} bundle has no verified coordinator source binding")
        if receipt.get("coordinator_manifest_sha256") != expected_coordinator_manifest_sha256:
            raise ValueError(f"{order} bundle does not match the independently pinned coordinator manifest")
        if type(receipt.get("n_reports")) is not int or receipt["n_reports"] != expected_n_reports:
            raise ValueError(f"{order} bundle does not cover the expected report count")
    if receipts["canonical"]["annotator_guide_sha256"] != receipts["reverse"]["annotator_guide_sha256"]:
        raise ValueError("counterbalanced annotator guides do not match")

    # The export verifier proves both presentations contain the same rows and
    # content in opposite order relative to the pinned coordinator source.
    # Do not include paths (which may expose local identities) in the receipt.
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_eval_counterbalanced_handoff_verified",
        "n_reports": expected_n_reports,
        "coordinator_manifest_sha256": expected_coordinator_manifest_sha256,
        "presentation_orders": ["canonical", "reverse"],
        "bundles": {
            order: {
                "packet_sha256": receipt["packet_sha256"],
                "ratings_template_sha256": receipt["ratings_template_sha256"],
                "annotator_guide_sha256": receipt["annotator_guide_sha256"],
            }
            for order, receipt in receipts.items()
        },
        "interpretation": (
            "Coordinator-only source-bound distribution preflight; no ratings "
            "collected, annotator identities authenticated, or human outcomes established"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--reverse-root", type=Path, required=True)
    parser.add_argument("--coordinator-manifest-sha256", required=True)
    parser.add_argument("--task-manifest", type=Path, default=exporter.DEFAULT_TASK_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=exporter.REPO_ROOT)
    parser.add_argument("--annotator-guide", type=Path, default=exporter.DEFAULT_ANNOTATOR_GUIDE)
    parser.add_argument("--expected-n-reports", type=int, default=40)
    args = parser.parse_args()
    try:
        receipt = verify_counterbalanced_handoff(
            packet_root=args.packet_root,
            canonical_root=args.canonical_root,
            reverse_root=args.reverse_root,
            expected_coordinator_manifest_sha256=args.coordinator_manifest_sha256,
            expected_n_reports=args.expected_n_reports,
            task_manifest_path=args.task_manifest,
            repo_root=args.repo_root,
            annotator_guide_path=args.annotator_guide,
        )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"counterbalanced handoff verification failed: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

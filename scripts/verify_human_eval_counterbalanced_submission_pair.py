"""Reconcile two blinded submissions with a pinned, counterbalanced handoff.

Read-only coordinator gate. Checks evidence about submitted ratings; it never
opens a blinding key, combines scores, or creates a frozen human dataset.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import stat

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_counterbalanced_handoff as handoff
from scripts import verify_human_eval_submission_preflight as preflight
from scripts import export_human_eval_annotator_bundle as exporter


def _require_distinct_paths(first: Path, second: Path, *, kind: str) -> None:
    try:
        if Path(first).samefile(second):
            raise ValueError(f"counterbalanced submissions require distinct {kind}")
    except FileNotFoundError:
        # The corresponding source-bound verifier gives the missing-file error.
        pass



def _pin_original_file(path: Path) -> tuple:
    """Observe a source's parent, inode, metadata and bounded exact bytes.

    The underlying freeze capture rejects symlinks and non-regular files and
    requires a stable descriptor/path through its own read window. Rechecking
    *both* inputs later closes the serial-verification cross-window gap.
    """
    path = Path(path)
    parent_before = path.parent.lstat()
    before = path.lstat()
    if not stat.S_ISDIR(parent_before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("counterbalanced submission/receipt must be a regular file under a regular directory")
    content = freeze._capture_regular_input(
        path, label="counterbalanced submission/receipt"
    )
    after = path.lstat()
    parent_after = path.parent.lstat()
    if (
        (parent_before.st_dev, parent_before.st_ino)
        != (parent_after.st_dev, parent_after.st_ino)
        or (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_ctime_ns,
        ) != (
            after.st_dev, after.st_ino, after.st_size,
            after.st_mtime_ns, after.st_ctime_ns,
        )
    ):
        raise ValueError("counterbalanced submission/receipt changed during source capture")
    return (
        parent_before.st_dev, parent_before.st_ino,
        before.st_dev, before.st_ino, before.st_size,
        before.st_mtime_ns, before.st_ctime_ns,
        hashlib.sha256(content).hexdigest(),
    )


def _pin_receipt_directory(path: Path) -> tuple:
    snapshot = Path(path).lstat()
    if not stat.S_ISDIR(snapshot.st_mode):
        raise ValueError("counterbalanced receipt root must be a regular directory")
    return snapshot.st_dev, snapshot.st_ino, snapshot.st_mtime_ns, snapshot.st_ctime_ns


@contextmanager
def _retained_pair_window(
    canonical_submission: Path,
    reverse_submission: Path,
    canonical_receipt_root: Path,
    reverse_receipt_root: Path,
):
    """Detect observable rewrites/replacements across the serial two-order audit.

    This is an observational guard, not a filesystem transaction or a claim
    about the people who submitted the ratings.
    """
    sources = {
        "canonical_submission": Path(canonical_submission),
        "reverse_submission": Path(reverse_submission),
        "canonical_receipt": Path(canonical_receipt_root) / preflight.RECEIPT_NAME,
        "reverse_receipt": Path(reverse_receipt_root) / preflight.RECEIPT_NAME,
    }
    roots = {
        "canonical_receipt_root": Path(canonical_receipt_root),
        "reverse_receipt_root": Path(reverse_receipt_root),
    }

    def snapshot() -> tuple[dict, dict]:
        directory_pins = {label: _pin_receipt_directory(root) for label, root in roots.items()}
        file_pins = {label: _pin_original_file(path) for label, path in sources.items()}
        return directory_pins, file_pins

    original = snapshot()
    yield
    if snapshot() != original:
        raise ValueError(
            "counterbalanced submission/receipt sources changed during pair verification"
        )


def verify_counterbalanced_submission_pair(
    *,
    packet_root: Path,
    canonical_root: Path,
    reverse_root: Path,
    canonical_submission: Path,
    reverse_submission: Path,
    canonical_receipt_root: Path,
    reverse_receipt_root: Path,
    expected_coordinator_manifest_sha256: str,
    expected_n_reports: int = 40,
    task_manifest_path: Path = exporter.DEFAULT_TASK_MANIFEST,
    repo_root: Path = exporter.REPO_ROOT,
    annotator_guide_path: Path = exporter.DEFAULT_ANNOTATOR_GUIDE,
) -> dict:
    """Require two verified preflight claims to bind to opposite verified orders.

    This is an optional pre-freeze custody check, not proof that two humans
    independently scored reports. Eligibility remains a separate protocol gate.
    """
    _require_distinct_paths(canonical_submission, reverse_submission, kind="rating files")
    _require_distinct_paths(canonical_receipt_root, reverse_receipt_root, kind="receipt directories")

    with _retained_pair_window(
        canonical_submission, reverse_submission,
        canonical_receipt_root, reverse_receipt_root,
    ):
        verified_handoff = handoff.verify_counterbalanced_handoff(
            packet_root=packet_root,
            canonical_root=canonical_root,
            reverse_root=reverse_root,
            expected_coordinator_manifest_sha256=expected_coordinator_manifest_sha256,
            expected_n_reports=expected_n_reports,
            task_manifest_path=task_manifest_path,
            repo_root=repo_root,
            annotator_guide_path=annotator_guide_path,
        )

        submissions = {}
        identity_keys = set()
        for order, submission, receipt_root, bundle_root in (
            ("canonical", canonical_submission, canonical_receipt_root, canonical_root),
            ("reverse", reverse_submission, reverse_receipt_root, reverse_root),
        ):
            verified = preflight.verify_preflight_receipt(
                receipt_root=Path(receipt_root),
                rating_path=Path(submission),
                annotator_bundle_root=Path(bundle_root),
            )
            if verified.get("presentation_order") != order:
                raise ValueError(f"{order} submission receipt is not for the assigned presentation order")
            if type(verified.get("n_reports")) is not int or verified["n_reports"] != expected_n_reports:
                raise ValueError(f"{order} submission does not cover the pinned report count")
            for key in ("packet_sha256", "ratings_template_sha256", "annotator_guide_sha256"):
                if verified.get(key) != verified_handoff["bundles"][order][key]:
                    raise ValueError(f"{order} submission does not bind to the verified counterbalanced handoff: {key}")
            identity = freeze._annotator_identity_key(verified["annotator_id"])
            if identity in identity_keys:
                raise ValueError("counterbalanced receipts do not identify distinct annotators")
            identity_keys.add(identity)
            # Return only provenance, not annotator IDs or score/note contents.
            submissions[order] = {
                "submission_sha256": verified["submission"]["sha256"],
                "annotator_manifest_sha256": verified["annotator_manifest_sha256"],
                "n_reports": verified["n_reports"],
                "n_missing_dimension_values": verified["n_missing_dimension_values"],
            }

        return {
            "schema_version": 1,
            "study_id": "budget-main-v1",
            "status": "human_eval_counterbalanced_submissions_source_bound",
            "n_reports": expected_n_reports,
            "coordinator_manifest_sha256": verified_handoff["coordinator_manifest_sha256"],
            "presentation_orders": ["canonical", "reverse"],
            "distinct_annotator_pseudonyms": True,
            "submissions": submissions,
            "interpretation": (
                "Coordinator-only read-only provenance check; no annotator identities "
                "authenticated, rating independence established, freeze performed, "
                "or human-validation results obtained"
            ),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--reverse-root", type=Path, required=True)
    parser.add_argument("--canonical-submission", type=Path, required=True)
    parser.add_argument("--reverse-submission", type=Path, required=True)
    parser.add_argument("--canonical-receipt-root", type=Path, required=True)
    parser.add_argument("--reverse-receipt-root", type=Path, required=True)
    parser.add_argument("--coordinator-manifest-sha256", required=True)
    parser.add_argument("--expected-n-reports", type=int, default=40)
    parser.add_argument("--task-manifest", type=Path, default=exporter.DEFAULT_TASK_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=exporter.REPO_ROOT)
    parser.add_argument("--annotator-guide", type=Path, default=exporter.DEFAULT_ANNOTATOR_GUIDE)
    args = parser.parse_args()
    try:
        receipt = verify_counterbalanced_submission_pair(
            packet_root=args.packet_root,
            canonical_root=args.canonical_root,
            reverse_root=args.reverse_root,
            canonical_submission=args.canonical_submission,
            reverse_submission=args.reverse_submission,
            canonical_receipt_root=args.canonical_receipt_root,
            reverse_receipt_root=args.reverse_receipt_root,
            expected_coordinator_manifest_sha256=args.coordinator_manifest_sha256,
            expected_n_reports=args.expected_n_reports,
            task_manifest_path=args.task_manifest,
            repo_root=args.repo_root,
            annotator_guide_path=args.annotator_guide,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"counterbalanced submission-pair verification failed: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

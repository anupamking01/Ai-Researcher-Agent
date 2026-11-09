"""Verify the *downloaded pair* of qualified VERA report and CI receipt.

Unlike the receipt producer, this consumer-side check requires that an existing
receipt match the exact canonical serialized receipt newly recomputed from the
historically pinned source checkout and the downloaded report. It is read-only
and does not independently authenticate missing treatment reports or traces.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.assemble_qualified_main_study_report import ROOT, _capture_markdown
from scripts.verify_qualified_reporting_copy import verify_qualified_copy


def verify_distributed_artifact(
    *, report_path: Path, receipt_path: Path, repo_root: Path = ROOT,
) -> dict:
    """Reject a replaced, reinterpreted, malformed, or noncanonical receipt."""
    # Capture before the expensive source-bound reassembly. The capture helper
    # rejects symlinks, non-regular files, hardlinks, and unstable/oversize data.
    receipt_bytes = _capture_markdown(Path(receipt_path))
    expected = verify_qualified_copy(
        report_path=Path(report_path), repo_root=Path(repo_root),
    )
    # Exact-byte comparison is intentional: a JSON parser can equate 1/true,
    # silently accept duplicate keys, or tolerate undeclared extra fields.
    # The producer is required to emit one deterministic JSON encoding.
    canonical_bytes = (
        json.dumps(expected, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if receipt_bytes != canonical_bytes:
        raise ValueError(
            "distributed verification receipt differs from source-bound canonical bytes"
        )
    # Observe both physical inputs again after the source-bound verification.
    closing_report = _capture_markdown(Path(report_path))
    if (
        len(closing_report) != expected["qualified_copy_bytes"]
        or hashlib.sha256(closing_report).hexdigest() != expected["qualified_copy_sha256"]
    ):
        raise ValueError("distributed qualified report changed during verification")
    if _capture_markdown(Path(receipt_path)) != receipt_bytes:
        raise ValueError("distributed verification receipt changed during verification")
    return {
        "status": "downloaded_pair_matches_checkout_local_source_bound_receipt",
        "qualified_copy_sha256": expected["qualified_copy_sha256"],
        "verification_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "original_reports_and_traces_independently_authenticated": False,
        "human_validation_performed": False,
        "interpretation": (
            "Checkout-local verification of the noncanonical downloadable report "
            "and its exact companion receipt only; not external artifact attestation "
            "or authenticated original treatment/human evidence"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        verification = verify_distributed_artifact(
            report_path=args.report, receipt_path=args.receipt, repo_root=args.repo_root,
        )
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, f"qualified reporting artifact verification blocked: {exc}\n")
    print(json.dumps(verification, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

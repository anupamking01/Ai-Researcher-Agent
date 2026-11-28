"""Verify a VERA qualified reporting copy and issue a noncanonical receipt.

No treatment, evaluator, statistical analysis, or human-rating run occurs here.
The copy must equal a fresh source-verified assembly *byte for byte*.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.assemble_qualified_main_study_report import (
    ROOT,
    ORIGINAL_JSON_SHA256,
    ORIGINAL_MARKDOWN_SHA256,
    REVIEWED_REPORTING_COVER_SHA256,
    _capture_markdown,
    assemble_qualified_report,
)
from scripts.verify_published_main_study_inputs import FROZEN_INPUT_AGGREGATE_SHA256


def verify_qualified_copy(*, report_path: Path, repo_root: Path = ROOT) -> dict:
    """Fail closed on an altered, partial, redirected, or stale reporting copy."""
    report_path = Path(report_path)
    observed = _capture_markdown(report_path)
    expected = assemble_qualified_report(repo_root=repo_root).encode("utf-8")
    if observed != expected:
        raise ValueError("qualified reporting copy does not match source-verified assembly")
    # Require the output pathname to retain the same bytes after verification.
    if _capture_markdown(report_path) != observed:
        raise ValueError("qualified reporting copy changed before receipt creation")
    return {
        "schema_version": 1,
        "status": "noncanonical_qualified_reporting_copy_verified",
        "qualified_copy_sha256": hashlib.sha256(observed).hexdigest(),
        "qualified_copy_bytes": len(observed),
        "historical_inference_markdown_sha256": ORIGINAL_MARKDOWN_SHA256,
        "historical_inference_json_sha256": ORIGINAL_JSON_SHA256,
        "reviewed_reporting_cover_sha256": REVIEWED_REPORTING_COVER_SHA256,
        "published_frozen_csv_aggregate_sha256": FROZEN_INPUT_AGGREGATE_SHA256,
        "original_reports_and_traces_independently_authenticated": False,
        "prospective_precollection_statistical_preregistration_established": False,
        "randomized_causal_effect_identified": False,
        "human_validation_performed": False,
        "interpretation": (
            "Verified checkout-local, noncanonical reading copy only; not a new "
            "statistical result, independent historical source attestation, "
            "or replacement for genuine blinded human evaluation"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        receipt = verify_qualified_copy(report_path=args.report, repo_root=args.repo_root)
        # Never overwrite a prior verification receipt.
        with args.receipt.open("x", encoding="utf-8") as target:
            json.dump(receipt, target, sort_keys=True, indent=2)
            target.write("\n")
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, f"qualified reporting-copy verification blocked: {exc}\n")
    print("Qualified, noncanonical reporting copy: PASS (no independent source/human claims)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

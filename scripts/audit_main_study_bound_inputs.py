"""Verify that one numeric audit parsed the CSV generation pinned by publication.

This offline tool combines two existing read-only gates. It does not rerun
treatments, common evaluation, inferential analysis, or human rating.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.audit_main_study_numeric_inputs import ROOT, NumericInputError, audit_files
from scripts.verify_published_main_study_inputs import verify_published_frozen_inputs


def verify_bound_numeric_inputs(*, repo_root: Path = ROOT) -> dict:
    """Refuse separate successes on different local source generations."""
    root = Path(repo_root)
    published = verify_published_frozen_inputs(repo_root=root)
    numeric = audit_files(root)
    if numeric["input_sha256"] != published["verified_input_sha256"]:
        raise NumericInputError(
            "numeric audit captured CSV fingerprints different from the "
            "published-source verifier's checked generation"
        )
    return {
        **numeric,
        "numeric_snapshot_bound_to_published_inputs": True,
        "published_input_aggregate_sha256": published["published_aggregate_sha256"],
        "original_treatment_report_trace_source_authenticated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        receipt = verify_bound_numeric_inputs(repo_root=args.repo_root)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"bound main-study numeric preflight failed: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only batch triage of caller-disclosed historical VERA ZIP candidates.

Compare *every supplied candidate* with the two historically recorded GitHub
job-log ZIP pins. Do not extract evidence, auto-discover backups, choose a
candidate by experimental results, or claim independent archive custody.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from scripts import preflight_recovered_artifact_zip as zip_preflight

ROLES = ("original_treatment", "evaluator_recovery")
MAX_CANDIDATES = 16


class CandidateTriageError(ValueError):
    """The candidate inventory is ambiguous or exceeds safe input bounds."""


def triage_candidates(assignments: Sequence[tuple[str, Path]]) -> dict:
    """Inspect every explicitly supplied candidate; retain negative observations.

    Successful structural checks and matching GitHub-provider ZIP metadata are
    only preliminary *same-provider concordance*. No result authorizes human
    packet distribution or authenticates a historical treatment/report.
    """
    if not 0 < len(assignments) <= MAX_CANDIDATES:
        raise CandidateTriageError(
            f"provide 1 to {MAX_CANDIDATES} explicitly identified ZIP candidates"
        )

    # Reject duplicate input paths before inspecting any source. Distinct
    # aliases/hardlinks are separately rejected by the ZIP preflight's
    # single-link and stable-descriptor checks; this is not a custody proof.
    seen_paths: set[str] = set()
    for role, path in assignments:
        if role not in ROLES:
            raise CandidateTriageError("unknown historical archive role")
        if not isinstance(path, Path) or not str(path) or "\x00" in str(path):
            raise CandidateTriageError("candidate must be a valid local path")
        normalized = os.path.normcase(os.path.abspath(os.fspath(path)))
        if normalized in seen_paths:
            raise CandidateTriageError("same candidate path supplied more than once")
        seen_paths.add(normalized)

    rows = []
    for index, (role, path) in enumerate(assignments, 1):
        anchor = zip_preflight.GITHUB_JOB_LOG_ARCHIVES[role]
        row = {
            "candidate_index": index,
            "role": role,
            "supplied_filename": path.name,
            "status": None,
            "structural_preflight_succeeded": False,
            "github_provider_zip_digest_and_size_match": False,
        }
        try:
            # Do not ask the preflight to fail early on a GitHub digest mismatch:
            # all structurally valid candidates must be inventoried, including
            # mismatches. No candidate is silently discarded as "unfavorable".
            evidence = zip_preflight.audit_recovered_zip(path)
        except (zip_preflight.RecoveredArchiveError, OSError, ValueError) as exc:
            row["status"] = "structural_preflight_failed"
            row["diagnostic"] = str(exc)[:300]
        else:
            row["structural_preflight_succeeded"] = True
            row["observed_zip_bytes"] = evidence["archive_bytes"]
            row["observed_zip_sha256"] = evidence["archive_sha256_observed_now"]
            row["file_count"] = evidence["file_count"]
            matched = (
                evidence["archive_bytes"] == anchor["size_bytes"]
                and evidence["archive_sha256_observed_now"] == anchor["zip_sha256"]
            )
            row["github_provider_zip_digest_and_size_match"] = matched
            row["status"] = (
                "github_provider_zip_concordant_not_authenticated"
                if matched else "does_not_match_historical_github_provider_zip"
            )
        rows.append(row)

    by_role = {
        role: {
            "candidate_count": sum(row["role"] == role for row in rows),
            "provider_concordant_count": sum(
                row["role"] == role
                and row["github_provider_zip_digest_and_size_match"]
                for row in rows
            ),
        }
        for role in ROLES
    }
    return {
        "schema_version": 1,
        "status": "candidate_triage_only_no_historical_authentication",
        "candidates": rows,
        "by_role": by_role,
        "all_explicit_candidates_accounted_for": len(rows) == len(assignments),
        "supplied_candidates_proven_exhaustive": False,
        "github_service_metadata_is_independent_custody": False,
        "original_treatment_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
        "interpretation": (
            "Matching both historical GitHub job-log ZIP byte count and SHA-256 "
            "is same-provider concordance, not independently authenticated "
            "original trace/report custody. Every caller-supplied candidate, "
            "including mismatches and unsafe archives, is retained; unsubmitted "
            "backups cannot be inventoried. Human distribution remains blocked "
            "until separate independent source and handoff checks pass."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--original-treatment", type=Path, action="append", default=[],
        metavar="ZIP", help="unchanged original-treatment backup candidate (repeatable)",
    )
    parser.add_argument(
        "--evaluator-recovery", type=Path, action="append", default=[],
        metavar="ZIP", help="unchanged evaluator-recovery backup candidate (repeatable)",
    )
    args = parser.parse_args()
    assignments = [
        *(("original_treatment", path) for path in args.original_treatment),
        *(("evaluator_recovery", path) for path in args.evaluator_recovery),
    ]
    try:
        receipt = triage_candidates(assignments)
    except CandidateTriageError as exc:
        parser.exit(2, f"VERA ARCHIVE CANDIDATE TRIAGE: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    # Exit 0 means only that all *listed* candidates were inventoried.
    # Evidence authentication and human-evaluation readiness remain false.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

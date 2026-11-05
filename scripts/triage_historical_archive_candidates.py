"""Read-only batch triage of caller-disclosed historical VERA ZIP candidates.

Compare *every supplied candidate* with the two historically recorded GitHub
job-log ZIP pins. Do not extract evidence, auto-discover backups, choose a
candidate by experimental results, or claim independent archive custody.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
from typing import Sequence

from scripts import preflight_recovered_artifact_zip as zip_preflight

ROLES = ("original_treatment", "evaluator_recovery")
MAX_CANDIDATES = 16
# Cap cumulative declared decompressed bytes across attempted members, including
# archives that fail CRC after inspection starts. Individual ZIP limits still apply.
MAX_BATCH_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024


class BatchUncompressedBudgetExceeded(zip_preflight.RecoveredArchiveError):
    """A candidate cannot be decompressed within the remaining batch allowance."""


class CandidateTriageError(ValueError):
    """The candidate inventory is ambiguous or exceeds safe input bounds."""


def _regular_member_content_sha256(evidence: dict) -> str:
    """Canonical identity of the ZIP's *decompressed regular files*, not its ZIP bytes.

    ZIP compression, member order, timestamps, and empty directory records do
    not contribute; file paths, uncompressed lengths, and SHA-256s do. Inputs
    have already passed the bounded structural ZIP preflight, including its
    unique-path, member-hash, and stable-source checks. This identifies
    content-equivalent backups, not independent custody or historical origin.
    """
    members = sorted(
        (
            {
                "path": item["path"],
                "uncompressed_bytes": item["uncompressed_bytes"],
                "sha256": item["sha256"],
            }
            for item in evidence["files"]
        ),
        key=lambda item: item["path"],
    )
    encoded = json.dumps(
        {"schema": "vera_zip_regular_members_v1", "members": members},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def _failure_diagnostic(exc: BaseException) -> str:
    """Keep local backup paths out of the otherwise filename-only receipt.

    The ZIP preflight wraps OS errors with their original exception as
    __cause__. Its default string includes absolute backup paths, even though
    this recovery receipt deliberately discloses only candidate basenames.
    Retain a stable, actionable errno category, not OS exception filenames.
    Structural ZIP failures still include their bounded preflight message.
    """
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, OSError):
            return (
                "cannot safely inspect ZIP: filesystem error "
                f"({errno.errorcode.get(current.errno, 'UNKNOWN')})"
            )
        current = current.__cause__
    return str(exc)[:300]


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

    remaining_uncompressed_budget = MAX_BATCH_UNCOMPRESSED_BYTES

    def reserve_batch_uncompressed_bytes(declared_bytes: int) -> None:
        nonlocal remaining_uncompressed_budget
        if declared_bytes > remaining_uncompressed_budget:
            raise BatchUncompressedBudgetExceeded(
                "candidate exceeds remaining batch decompression budget"
            )
        # Deliberately no refund on a later ZIP CRC, stream, or digest failure.
        remaining_uncompressed_budget -= declared_bytes

    rows = []
    first_verified_by_sha256: dict[str, int] = {}
    first_regular_member_content_by_sha256: dict[str, int] = {}
    for index, (role, path) in enumerate(assignments, 1):
        anchor = zip_preflight.GITHUB_JOB_LOG_ARCHIVES[role]
        row = {
            "candidate_index": index,
            "role": role,
            "supplied_filename": path.name,
            "status": None,
            "structural_preflight_succeeded": False,
            "github_provider_zip_digest_and_size_match": False,
            "other_role_github_provider_zip_match": None,
            "duplicate_verified_zip_of_candidate_index": None,
            "observed_regular_member_content_sha256": None,
            "same_regular_members_as_candidate_index": None,
        }
        try:
            # Do not ask the preflight to fail early on a GitHub digest mismatch:
            # all structurally valid candidates must be inventoried, including
            # mismatches. No candidate is silently discarded as "unfavorable".
            evidence = zip_preflight.audit_recovered_zip(
                path, reserve_uncompressed_bytes=reserve_batch_uncompressed_bytes
            )
        except BatchUncompressedBudgetExceeded:
            row["status"] = "not_inspected_batch_decompression_budget_exceeded"
            row["diagnostic"] = "candidate exceeds remaining batch decompression budget"
        except (zip_preflight.RecoveredArchiveError, OSError, ValueError) as exc:
            row["status"] = "structural_preflight_failed"
            row["diagnostic"] = _failure_diagnostic(exc)
        else:
            row["structural_preflight_succeeded"] = True
            row["observed_zip_bytes"] = evidence["archive_bytes"]
            row["observed_zip_sha256"] = evidence["archive_sha256_observed_now"]
            row["file_count"] = evidence["file_count"]
            # Two structurally sound ZIPs can carry the exact same research
            # files under different compression/order metadata. Keep both
            # candidates and their distinct container digests, but do not
            # mistake their equal extracted regular members for new evidence.
            content_sha = _regular_member_content_sha256(evidence)
            row["observed_regular_member_content_sha256"] = content_sha
            first_content_index = first_regular_member_content_by_sha256.get(content_sha)
            if first_content_index is None:
                first_regular_member_content_by_sha256[content_sha] = index
            else:
                row["same_regular_members_as_candidate_index"] = first_content_index
            # Different pathnames are not necessarily different backups. Keep
            # every observation, but identify repeated verified ZIP bytes by
            # the first candidate index, even across declared archive roles.
            digest = evidence["archive_sha256_observed_now"]
            first_index = first_verified_by_sha256.get(digest)
            if first_index is None:
                first_verified_by_sha256[digest] = index
            else:
                row["duplicate_verified_zip_of_candidate_index"] = first_index
            matched = (
                evidence["archive_bytes"] == anchor["size_bytes"]
                and evidence["archive_sha256_observed_now"] == anchor["zip_sha256"]
            )
            row["github_provider_zip_digest_and_size_match"] = matched
            # A sound ZIP may have been assigned the wrong historical role.
            # This is an alternate recovery lead, not a source reassignment.
            other_role = next(
                (
                    alternative for alternative in ROLES if alternative != role
                    and evidence["archive_bytes"]
                    == zip_preflight.GITHUB_JOB_LOG_ARCHIVES[alternative]["size_bytes"]
                    and digest
                    == zip_preflight.GITHUB_JOB_LOG_ARCHIVES[alternative]["zip_sha256"]
                ),
                None,
            ) if not matched else None
            row["other_role_github_provider_zip_match"] = other_role
            row["status"] = (
                "github_provider_zip_concordant_not_authenticated" if matched
                else "matches_other_historical_role_not_declared_role" if other_role
                else "does_not_match_historical_github_provider_zip"
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
            "other_role_provider_concordant_count": sum(
                row["role"] == role
                and row["other_role_github_provider_zip_match"] is not None
                for row in rows
            ),
            "distinct_regular_member_content_count": len({
                row["observed_regular_member_content_sha256"] for row in rows
                if row["role"] == role and row["structural_preflight_succeeded"]
            }),
            "distinct_structurally_verified_zip_count": len({
                row["observed_zip_sha256"] for row in rows
                if row["role"] == role and row["structural_preflight_succeeded"]
            }),
            "distinct_provider_concordant_zip_count": len({
                row["observed_zip_sha256"] for row in rows
                if row["role"] == role and row["github_provider_zip_digest_and_size_match"]
            }),
        }
        for role in ROLES
    }
    return {
        "schema_version": 3,
        "status": "candidate_triage_only_no_historical_authentication",
        "candidates": rows,
        "by_role": by_role,
        "all_explicit_candidates_accounted_for": len(rows) == len(assignments),
        "batch_declared_uncompressed_byte_budget": MAX_BATCH_UNCOMPRESSED_BYTES,
        "batch_declared_uncompressed_bytes_reserved": (
            MAX_BATCH_UNCOMPRESSED_BYTES - remaining_uncompressed_budget
        ),
        "batch_candidates_not_inspected_due_to_budget": sum(
            row["status"] == "not_inspected_batch_decompression_budget_exceeded"
            for row in rows
        ),
        "same_regular_members_duplicate_count": sum(
            row["same_regular_members_as_candidate_index"] is not None
            for row in rows
        ),
        "verified_zip_byte_duplicate_count": sum(
            row["duplicate_verified_zip_of_candidate_index"] is not None
            for row in rows
        ),
        "other_role_provider_concordant_candidate_count": sum(
            row["other_role_github_provider_zip_match"] is not None
            for row in rows
        ),
        "distinct_zip_bytes_establish_independent_custody": False,
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
            "including mismatches and unsafe archives, is retained. A bounded "
            "batch-wide declared decompression budget is reserved BEFORE ZIP "
            "member reads, including candidates that later fail integrity; "
            "budget-exceeded inputs are explicitly not inspected, not "
            "misreported as structurally invalid. Repeated "
            "verified ZIP bytes are identified but not removed or treated as "
            "independent backup custody. Decompressed regular-file content "
            "equivalence is separately flagged even for different ZIP bytes; "
            "it ignores ZIP-only metadata and proves neither historical "
            "origin nor independent custody. A candidate matching the other "
            "historical role's provider pin is flagged without relabelling "
            "the caller's declaration; unsubmitted "
            "backups cannot be inventoried. Human distribution remains blocked "
            "until separate independent source and handoff checks pass."
        ),
    }


class _OrderedCandidate(argparse.Action):
    """Keep caller-supplied ZIP roles and paths in the exact CLI sequence.

    The row numbers and first-seen duplicate links in the recovery receipt
    must refer to argv order, not an implicit grouping by treatment role.
    """

    def __init__(self, option_strings, dest, *, role: str, **kwargs):
        super().__init__(option_strings, dest, **kwargs)
        self.role = role

    def __call__(self, parser, namespace, values, option_string=None):
        current = getattr(namespace, self.dest, None)
        setattr(namespace, self.dest, [*(current or []), (self.role, values)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--original-treatment", dest="assignments", type=Path,
        action=_OrderedCandidate, role="original_treatment",
        metavar="ZIP", help="unchanged original-treatment backup candidate (repeatable)",
    )
    parser.add_argument(
        "--evaluator-recovery", dest="assignments", type=Path,
        action=_OrderedCandidate, role="evaluator_recovery",
        metavar="ZIP", help="unchanged evaluator-recovery backup candidate (repeatable)",
    )
    args = parser.parse_args()
    try:
        receipt = triage_candidates(args.assignments or [])
    except CandidateTriageError as exc:
        parser.exit(2, f"VERA ARCHIVE CANDIDATE TRIAGE: FAIL: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    # Exit 0 means only that all *listed* candidates were inventoried.
    # Evidence authentication and human-evaluation readiness remain false.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

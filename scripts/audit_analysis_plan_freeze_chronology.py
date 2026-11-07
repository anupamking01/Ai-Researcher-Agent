"""Read-only Git ancestry audit of the historical VERA analysis-plan freeze.

This audits *when the written analysis plan entered Git history*; it cannot
establish when a researcher first saw, learned, or analyzed outcomes.
Requires an unshallowed checkout containing the pinned historical commits.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class Milestones:
    prior_protocol: str = "e390c0de7001011c171d0161a6eb1b96517a3583"
    treatment: str = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
    evaluator_recovery: str = "8733ce492abc74e7b2966ed22ce08d3fddec43ca"
    analysis_plan: str = "7352cae144e82e7862630db9501c00570adec640"
    canonical_publication: str = "1ddc84c261bc4207206e9e1d8724743392585598"


class FreezeChronologyError(ValueError):
    """Historical checkout does not satisfy the pinned chronology contract."""


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False
    )
    if result.returncode:
        raise FreezeChronologyError(
            f"git {args[0]} failed (exit {result.returncode}); "
            "a complete, authentic local Git history is required"
        )
    return result.stdout


def _ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True, check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise FreezeChronologyError("unable to verify historical ancestry")


def audit_history(root: Path, *, milestones: Milestones = Milestones()) -> dict:
    root = root.resolve()
    if _git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root):
        raise FreezeChronologyError("the supplied path is not the Git repository root")
    # A shallow checkout can contain some pinned objects while lacking the
    # complete ancestry needed to audit the order of historical milestones.
    if _git(root, "rev-parse", "--is-shallow-repository").decode().strip() != "false":
        raise FreezeChronologyError("complete, non-shallow Git history is required")
    refs = vars(milestones)
    for name, sha in refs.items():
        if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
            raise FreezeChronologyError(f"{name} is not an exact historical commit SHA")
        resolved = _git(root, "rev-parse", f"{sha}^{{commit}}").decode().strip()
        if resolved != sha:
            raise FreezeChronologyError(f"{name} does not resolve to the pinned commit")

    ordered = (
        ("prior_protocol", "treatment"),
        ("treatment", "evaluator_recovery"),
        ("evaluator_recovery", "analysis_plan"),
        ("analysis_plan", "canonical_publication"),
    )
    for left, right in ordered:
        if not _ancestor(root, refs[left], refs[right]) or refs[left] == refs[right]:
            raise FreezeChronologyError(f"historical order not established: {left} before {right}")
    if not _ancestor(root, milestones.canonical_publication, "HEAD"):
        raise FreezeChronologyError("this checkout does not descend from canonical publication")

    plan_path = root / "paper" / "ANALYSIS_PLAN.md"
    if plan_path.is_symlink() or not plan_path.is_file():
        raise FreezeChronologyError("analysis-plan working copy is not a regular file")
    frozen = _git(root, "show", f"{milestones.analysis_plan}:paper/ANALYSIS_PLAN.md")
    head = _git(root, "show", "HEAD:paper/ANALYSIS_PLAN.md")
    if not frozen or frozen != head or frozen != plan_path.read_bytes():
        raise FreezeChronologyError("the historical analysis-plan bytes have changed")

    reporting = _audit_reporting_boundary(root, milestones)
    return {
        **reporting,
        "status": "verified_git_history_sequence_not_outcome_blinding",
        "historical_commit_shas": dict(refs),
        "prior_protocol_precedes_treatments_in_git": True,
        "written_analysis_plan_postdates_treatment_commit_in_git": True,
        "written_analysis_plan_postdates_evaluator_recovery_commit_in_git": True,
        "written_analysis_plan_precedes_canonical_git_publication": True,
        "current_analysis_plan_bytes_equal_original_commit": True,
        "prospective_precollection_analysis_preregistration_established": False,
        "pre_analysis_outcome_blinding_established": False,
        "original_treatment_authenticity_established": False,
        "human_validation_performed": False,
    }



# The original manuscript-facing report cannot be silently rewritten to correct
# a retrospective scientific claim. Require a separately committed, qualified
# cover whose wording is auditable alongside the preserved publication bytes.
_FROZEN_REPORT_FILES = (
    "paper/MAIN_STUDY_INFERENCE.md",
    "outputs/main_study_inference.json",
)
_REPORTING_COVER = "paper/MAIN_STUDY_REPORTING_COVER.md"
_LEGACY_CLAIM = b"three preregistered strict-support contrasts"
_REQUIRED_COVER_CLAIMS = (
    "prospective precollection statistical preregistration is not established",
    "outcome blinding at the september 14 freeze is not established",
    "designated primary contrasts",
    "post-collection, pre-canonical-publication analysis",
    "fixed-order temporal confounding",
    "five-task pilot remains diagnostic",
    "post-hoc exploratory diagnostics remain exploratory",
    "human validation remains pending",
    "original source custody remains unverified",
    "main_study_inference.md",
    "main_study_analysis_freeze_chronology.md",
)


def _reporting_regular_bytes(root: Path, relative: str, limit: int) -> bytes:
    path = root / relative
    # No redirected source/cover pathname may be presented as a repository file.
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise FreezeChronologyError(f"reporting source uses symlink: {relative}")
        cursor = cursor.parent
    if not path.is_file() or path.stat().st_size > limit:
        raise FreezeChronologyError(f"reporting source is absent or oversized: {relative}")
    return path.read_bytes()


def _audit_reporting_boundary(root: Path, milestones: Milestones) -> dict:
    publication_fingerprints = {}
    for relative in _FROZEN_REPORT_FILES:
        limit = 1024 * 1024 if relative.endswith(".json") else 256 * 1024
        historical = _git(root, "show", f"{milestones.canonical_publication}:{relative}")
        at_head = _git(root, "show", f"HEAD:{relative}")
        working = _reporting_regular_bytes(root, relative, limit)
        if not historical or historical != at_head or historical != working:
            raise FreezeChronologyError(
                f"canonical publication/report bytes changed: {relative}"
            )
        publication_fingerprints[relative] = hashlib.sha256(historical).hexdigest()

    historic_report = _git(
        root, "show",
        f"{milestones.canonical_publication}:paper/MAIN_STUDY_INFERENCE.md",
    )
    if _LEGACY_CLAIM not in historic_report:
        raise FreezeChronologyError(
            "expected unqualified historical wording was not found in canonical report"
        )

    cover = _reporting_regular_bytes(root, _REPORTING_COVER, 64 * 1024)
    if cover != _git(root, "show", f"HEAD:{_REPORTING_COVER}"):
        raise FreezeChronologyError("reporting cover differs from committed HEAD")
    try:
        prose = " ".join(cover.decode("utf-8").casefold().split())
    except UnicodeDecodeError as exc:
        raise FreezeChronologyError("reporting cover must be UTF-8") from exc
    for claim in _REQUIRED_COVER_CLAIMS:
        if claim not in prose:
            raise FreezeChronologyError(f"reporting cover lacks required claim: {claim}")

    return {
        "canonical_publication_report_bytes_unchanged": True,
        "canonical_publication_inference_json_bytes_unchanged": True,
        "historical_report_contains_unqualified_preregistration_wording": True,
        "separate_committed_reporting_cover_checked": True,
        "original_publication_sha256_by_path": publication_fingerprints,
        "reporting_cover_sha256": hashlib.sha256(cover).hexdigest(),
        "reporting_scope": "postcollection_designated_primary_not_prospective_preregistration",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report = audit_history(args.root)
    except FreezeChronologyError as exc:
        parser.exit(1, f"freeze chronology audit failed: {exc}\n")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

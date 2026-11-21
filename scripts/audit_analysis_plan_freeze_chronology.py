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
import re
import subprocess


@dataclass(frozen=True)
class Milestones:
    prior_protocol: str = "e390c0de7001011c171d0161a6eb1b96517a3583"
    treatment: str = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
    evaluator_recovery: str = "8733ce492abc74e7b2966ed22ce08d3fddec43ca"
    analysis_plan: str = "7352cae144e82e7862630db9501c00570adec640"
    canonical_publication: str = "1ddc84c261bc4207206e9e1d8724743392585598"
    human_analysis_plan: str = "682d2861f1eaa988e196efcc492b0b23c9e838da"
    # Git blob ID of the September 9 broad protocol, not another commit.
    prior_protocol_blob_sha: str = "706986c65eeb4628255198570e4e0f2fb48ee7ac"


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



# This source check prevents Git chronology alone from being mistaken for
# evidence that the *realized* four-arm, three-test inference was frozen in the
# earlier broader protocol. The Git blob is pinned independently of HEAD.
_PRIOR_PROTOCOL_PATH = "paper/RESEARCH_PROTOCOL.md"
_PRIOR_PROTOCOL_CANDIDATE_VARIANTS = (
    "D3", "D6", "D12", "P3", "P6", "P12", "D6V", "P6V",
)
_REALIZED_MAIN_STUDY_VARIANTS = ("D3", "D6", "P6", "P6V")


def _parse_prior_protocol_scope(raw: bytes) -> tuple[str, ...]:
    """Inspect the literal candidate-variant table, never execute protocol text."""
    if not raw or len(raw) > 256 * 1024:
        raise FreezeChronologyError("historical prior protocol is empty or oversized")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FreezeChronologyError("historical prior protocol is not UTF-8") from exc
    match = re.search(
        r"(?ms)^## Variants[ \t]*\r?\n(.*?)(?=^## |\Z)", source
    )
    if match is None or "Minimum viable main-study matrix:" not in match.group(1):
        raise FreezeChronologyError("historical prior protocol variant table is missing")
    rows = re.findall(
        r"(?m)^\|\s*([A-Za-z][A-Za-z0-9]*)\s*\|", match.group(1)
    )
    candidates = tuple(row for row in rows if row != "ID")
    if candidates != _PRIOR_PROTOCOL_CANDIDATE_VARIANTS:
        raise FreezeChronologyError(
            "historical prior protocol candidate variant matrix differs from source contract"
        )
    # The later exact three-test sign-flip/Holm procedure is not in this
    # historical document. The absence of its named procedure is a scoped
    # text observation, not proof of the authors' precollection knowledge.
    if re.search(r"\bholm\b|\bsign[\s-]?flip\b", source, flags=re.IGNORECASE):
        raise FreezeChronologyError(
            "historical prior protocol contains later exact inference terminology"
        )
    return candidates


def _audit_prior_protocol_source(root: Path, milestones: Milestones) -> dict:
    expected = milestones.prior_protocol_blob_sha
    if len(expected) != 40 or any(c not in "0123456789abcdef" for c in expected):
        raise FreezeChronologyError("prior protocol Git blob pin must be a full SHA")
    source_ref = f"{milestones.prior_protocol}:{_PRIOR_PROTOCOL_PATH}"
    actual = _git(root, "rev-parse", source_ref).decode().strip()
    if actual != expected:
        raise FreezeChronologyError("historical prior protocol Git blob differs from pin")
    raw = _git(root, "show", source_ref)
    candidates = _parse_prior_protocol_scope(raw)
    # This earlier table is an eight-arm *candidate* set. The actual main
    # treatment was four arms; the protocol cannot be cited as the exact
    # prospective specification of the later inferential family.
    return {
        "historical_prior_protocol_git_blob_sha": actual,
        "historical_prior_protocol_sha256": hashlib.sha256(raw).hexdigest(),
        "historical_prior_protocol_candidate_variants": list(candidates),
        "realized_main_study_variants": list(_REALIZED_MAIN_STUDY_VARIANTS),
        "prior_candidate_matrix_identical_to_realized_matrix": (
            candidates == _REALIZED_MAIN_STUDY_VARIANTS
        ),
        "prior_protocol_specified_later_exact_holm_signflip_procedure": False,
        "prior_protocol_source_bound_not_exact_precollection_plan": True,
    }


def audit_history(root: Path, *, milestones: Milestones = Milestones()) -> dict:
    root = root.resolve()
    if _git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root):
        raise FreezeChronologyError("the supplied path is not the Git repository root")
    # A shallow checkout can contain some pinned objects while lacking the
    # complete ancestry needed to audit the order of historical milestones.
    if _git(root, "rev-parse", "--is-shallow-repository").decode().strip() != "false":
        raise FreezeChronologyError("complete, non-shallow Git history is required")
    refs = {
        name: value for name, value in vars(milestones).items()
        if name != "prior_protocol_blob_sha"
    }
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
        ("canonical_publication", "human_analysis_plan"),
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

    prior_protocol = _audit_prior_protocol_source(root, milestones)
    reporting = _audit_reporting_boundary(root, milestones)
    return {
        **reporting,
        **prior_protocol,
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
_HUMAN_PLAN_FILE = "paper/HUMAN_EVAL_ANALYSIS_PLAN.md"
_HUMAN_PLAN_LEGACY_CLAIM = (
    "the automated strict-support analysis remains the study's "
    "preregistered confirmatory analysis"
)
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
    "human_eval_analysis_plan.md",
    "does not retroactively establish prospective",
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

    # Preserve the independent human-analysis-plan freeze without backdating
    # the earlier automated statistical plan or inventing outcome blinding.
    human_original = _git(root, "show",
                          f"{milestones.human_analysis_plan}:{_HUMAN_PLAN_FILE}")
    human_head = _git(root, "show", f"HEAD:{_HUMAN_PLAN_FILE}")
    human_working = _reporting_regular_bytes(root, _HUMAN_PLAN_FILE, 256 * 1024)
    if not human_original or human_original != human_head or human_original != human_working:
        raise FreezeChronologyError("frozen human-evaluation analysis plan bytes changed")
    try:
        human_prose = " ".join(human_original.decode("utf-8").casefold().split())
    except UnicodeDecodeError as exc:
        raise FreezeChronologyError("frozen human-analysis plan must be UTF-8") from exc
    if _HUMAN_PLAN_LEGACY_CLAIM not in human_prose:
        raise FreezeChronologyError(
            "expected historical automated-preregistration claim absent from human plan"
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
        "historical_human_analysis_plan_bytes_unchanged": True,
        "historical_human_plan_contains_unqualified_automated_preregistration_wording": True,
        "historical_human_analysis_plan_sha256": hashlib.sha256(human_original).hexdigest(),
        "human_plan_freeze_does_not_backdate_automated_plan": True,
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

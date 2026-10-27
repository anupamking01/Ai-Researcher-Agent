"""Read-only inventory of ORIGINAL VERA evidence required before human handoff.

This is a recovery diagnostic, NOT a provenance PASS. A path's presence (or
40 trace candidates) never proves its content, run identity, archive custody,
or suitability for human assessment. Use verify_human_eval_automated_handoff
with independently retained pins for the actual acceptance decision.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path

from scripts import export_human_eval_annotator_bundle as exporter
from scripts import verify_published_main_study_inputs as published

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TRACES = 40


def _file_status(path: Path) -> str:
    """Do not silently classify symlinks or nonregular evidence as available."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "inaccessible"
    if not stat.S_ISREG(mode):
        return "unsafe_file_type"
    try:
        if any(parent.is_symlink() for parent in path.parents):
            return "unsafe_parent_symlink"
    except OSError:
        return "inaccessible"
    return "present_unverified"


def _trace_status(root: Path) -> tuple[str, int]:
    """Count only direct <variant>/<run>.json regular candidates, not content."""
    if not root.exists() and not root.is_symlink():
        return "missing", 0
    try:
        if not stat.S_ISDIR(root.lstat().st_mode):
            return "unsafe_directory_type", 0
        count = 0
        for variant in root.iterdir():
            if not stat.S_ISDIR(variant.lstat().st_mode):
                return "unsafe_directory_type", count
            for candidate in variant.iterdir():
                if not stat.S_ISREG(candidate.lstat().st_mode):
                    return "unsafe_file_type", count
                if candidate.suffix == ".json":
                    count += 1
    except OSError:
        return "inaccessible", 0
    if count != EXPECTED_TRACES:
        return "candidate_count_mismatch", count
    return "40_candidates_unverified", count


def _pin_status(value: str | None) -> str:
    if value is None:
        return "independent_pin_not_supplied"
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        return "invalid_pin_format"
    return "pin_supplied_not_authenticated"


def audit_archive_readiness(
    *,
    repo_root: Path = ROOT,
    packet_root: Path | None = None,
    canonical_root: Path | None = None,
    reverse_root: Path | None = None,
    research_manifest_path: Path | None = None,
    research_manifest_sha256: str | None = None,
    coordinator_manifest_sha256: str | None = None,
) -> dict:
    """Enumerate missing custody inputs without generating or changing evidence."""
    root = Path(repo_root)
    packet = Path(packet_root) if packet_root is not None else root / "outputs/human_eval"
    canonical = (Path(canonical_root) if canonical_root is not None
                 else packet / "annotator-canonical-v1")
    reverse = (Path(reverse_root) if reverse_root is not None
               else packet / "annotator-reverse-v1")
    manifest = (Path(research_manifest_path) if research_manifest_path is not None
                else root / published.MANIFEST)

    sources = {
        "research_manifest": manifest,
        "frozen_task_manifest": root / "experiments/main_budget_tasks.json",
        "frozen_annotator_guide": root / "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
        "treatment_csv": root / published.FROZEN_INPUTS[0],
        "common_evaluator_csv": root / published.FROZEN_INPUTS[1],
    }
    for artifact in exporter.COORDINATOR_ARTIFACTS:
        sources[f"coordinator/{artifact}"] = packet / artifact
    for order, bundle in (("canonical", canonical), ("reverse", reverse)):
        for artifact in exporter.ANNOTATOR_ARTIFACTS:
            sources[f"{order}/{artifact}"] = bundle / artifact

    resources = {label: _file_status(path) for label, path in sources.items()}
    trace_status, trace_count = _trace_status(root / "outputs/experiment_traces")
    pins = {
        "research_manifest_file": _pin_status(research_manifest_sha256),
        "coordinator_manifest_file": _pin_status(coordinator_manifest_sha256),
    }
    # The repository's canonical CSVs and manifest can be verified even when
    # the original report archive is unavailable; never infer report validity.
    if all(resources[label] == "present_unverified" for label in (
        "research_manifest", "treatment_csv", "common_evaluator_csv"
    )):
        try:
            published.verify_published_frozen_inputs(
                repo_root=root, manifest_path=manifest
            )
        except (OSError, ValueError, json.JSONDecodeError):
            input_anchor = "verification_failed"
        else:
            input_anchor = "published_aggregate_matches"
    else:
        input_anchor = "cannot_verify_missing_or_unsafe_input"

    gaps = [label for label, status in resources.items() if status != "present_unverified"]
    if trace_status != "40_candidates_unverified":
        gaps.append("original_experiment_trace_candidates")
    gaps.extend(label for label, status in pins.items()
                if status != "pin_supplied_not_authenticated")
    if input_anchor != "published_aggregate_matches":
        gaps.append("published_automated_input_anchor")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blocked" if gaps else "candidate_inputs_present_not_verified",
        "resources": resources,
        "trace_candidates": {"status": trace_status, "count": trace_count,
                             "expected": EXPECTED_TRACES},
        "independent_pins": pins,
        "published_automated_input_anchor": input_anchor,
        "blockers": sorted(gaps),
        "handoff_verified": False,
        "human_ratings_used": False,
        "treatments_rerun": False,
        "interpretation": (
            "Recovery inventory only. Even with zero blockers, independently "
            "run the integrated source-pinned handoff verifier on the original "
            "archive; no human validation or historical authenticity is claimed."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--packet-root", type=Path)
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--reverse-root", type=Path)
    parser.add_argument("--research-manifest", type=Path)
    parser.add_argument("--research-manifest-sha256")
    parser.add_argument("--coordinator-manifest-sha256")
    parser.add_argument("--require-candidates", action="store_true",
                        help="Exit nonzero unless all evidence candidates and pins are supplied")
    args = parser.parse_args()
    result = audit_archive_readiness(
        repo_root=args.repo_root, packet_root=args.packet_root,
        canonical_root=args.canonical_root, reverse_root=args.reverse_root,
        research_manifest_path=args.research_manifest,
        research_manifest_sha256=args.research_manifest_sha256,
        coordinator_manifest_sha256=args.coordinator_manifest_sha256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(args.require_candidates and result["status"] == "blocked")


if __name__ == "__main__":
    raise SystemExit(main())

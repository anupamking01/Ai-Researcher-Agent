"""Read-only inventory of ORIGINAL VERA evidence required before human handoff.

This is a recovery diagnostic, NOT a provenance PASS. A path's presence (or
40 trace candidates) never proves its content, run identity, archive custody,
or suitability for human assessment. Use verify_human_eval_automated_handoff
with independently retained pins for the actual acceptance decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path

from scripts import build_human_eval_packet as packet_builder
from scripts import export_human_eval_annotator_bundle as exporter
from scripts import verify_published_main_study_inputs as published

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TRACES = 40
VARIANTS = packet_builder.EXPECTED_VARIANTS
EXPECTED_PER_VARIANT = EXPECTED_TRACES // len(VARIANTS)


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


def _directory_status(path: Path) -> str:
    """Reject redirected and non-directory archive roots before enumeration."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "inaccessible"
    if not stat.S_ISDIR(mode):
        return "unsafe_directory_type"
    try:
        if any(parent.is_symlink() for parent in path.parents):
            return "unsafe_parent_symlink"
    except OSError:
        return "inaccessible"
    return "present_unverified"


def _trace_status(root: Path) -> tuple[dict, tuple[str, ...]]:
    """Inventory 4 x 10 candidate filenames without parsing or endorsing traces.

    An unbalanced 40-file directory cannot possibly represent the frozen
    4 x 10 design. Avoid following links, accepting unfamiliar variants, or
    conflating the existence of JSON filenames with run/task provenance.
    """
    by_variant = {variant: 0 for variant in VARIANTS}
    run_ids: set[str] = set()

    def result(status: str) -> dict:
        return {
            "status": status,
            "count": sum(by_variant.values()),
            "expected": EXPECTED_TRACES,
            "by_variant": dict(by_variant),
            "expected_per_variant": EXPECTED_PER_VARIANT,
        }

    status = _directory_status(root)
    if status != "present_unverified":
        return result(status), ()
    try:
        for variant_dir in sorted(root.iterdir()):
            if variant_dir.name not in by_variant:
                return result("unexpected_trace_root_entry"), ()
            if _directory_status(variant_dir) != "present_unverified":
                return result("unsafe_variant_directory"), ()
            for candidate in sorted(variant_dir.iterdir()):
                if candidate.suffix != ".json" or candidate.stem in ("", ".", ".."):
                    return result("unexpected_trace_entry"), ()
                if _file_status(candidate) != "present_unverified":
                    return result("unsafe_trace_file_type"), ()
                if candidate.stem in run_ids:
                    return result("duplicate_trace_run_id"), ()
                run_ids.add(candidate.stem)
                by_variant[variant_dir.name] += 1
                if sum(by_variant.values()) > EXPECTED_TRACES:
                    return result("candidate_count_mismatch"), ()
    except OSError:
        return result("inaccessible"), ()

    if len(run_ids) != EXPECTED_TRACES:
        return result("candidate_count_mismatch"), tuple(sorted(run_ids))
    if any(count != EXPECTED_PER_VARIANT for count in by_variant.values()):
        return result("candidate_matrix_mismatch"), tuple(sorted(run_ids))
    return result("40_matrix_candidates_unverified"), tuple(sorted(run_ids))


def _report_status(root: Path, run_ids: tuple[str, ...]) -> dict:
    """Check one expected Markdown filename per run, without opening reports."""
    result = {"status": "not_checked_without_trace_candidates", "count": 0,
              "expected": EXPECTED_TRACES, "missing_or_unsafe": {}}
    if not run_ids:
        return result
    status = _directory_status(root)
    if status != "present_unverified":
        result["status"] = status
        return result

    failed: dict[str, int] = {}
    for run_id in run_ids:
        status = _file_status(root / run_id / "research_report.md")
        if status == "present_unverified":
            result["count"] += 1
        else:
            failed[status] = failed.get(status, 0) + 1
    result["missing_or_unsafe"] = dict(sorted(failed.items()))
    if failed:
        result["status"] = "missing_or_unsafe_report_candidates"
    elif result["count"] != EXPECTED_TRACES:
        result["status"] = "candidate_count_mismatch"
    else:
        result["status"] = "40_report_candidates_unverified"
    return result


def _pin_status(value: str | None, path: Path) -> str:
    """Compare a supplied pin to bounded, captured manifest bytes.

    Matching proves only local file/pin consistency. The coordinator must
    independently establish when and where the expected digest was retained.
    """
    if value is None:
        return "independent_pin_not_supplied"
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        return "invalid_pin_format"
    if _file_status(path) != "present_unverified":
        return "pinned_file_missing_or_unsafe"
    try:
        actual = hashlib.sha256(
            packet_builder._read_regular_file_captured(
                path, label="archival manifest for pin comparison"
            )
        ).hexdigest()
    except (OSError, ValueError):
        return "pinned_file_unreadable_or_unstable"
    return (
        "pin_matches_file_not_authenticated"
        if actual == value else "pin_mismatch"
    )


def audit_archive_readiness(
    *,
    repo_root: Path = ROOT,
    trace_root: Path | None = None,
    report_root: Path | None = None,
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
    traces = Path(trace_root) if trace_root is not None else root / "outputs/experiment_traces"
    reports = Path(report_root) if report_root is not None else root / "outputs"
    trace_candidates, run_ids = _trace_status(traces)
    report_candidates = _report_status(reports, run_ids)
    pins = {
        "research_manifest_file": _pin_status(
            research_manifest_sha256, manifest
        ),
        "coordinator_manifest_file": _pin_status(
            coordinator_manifest_sha256, packet / "manifest.json"
        ),
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
    if trace_candidates["status"] != "40_matrix_candidates_unverified":
        gaps.append("original_experiment_trace_candidates")
    if report_candidates["status"] != "40_report_candidates_unverified":
        gaps.append("original_markdown_report_candidates")
    gaps.extend(label for label, status in pins.items()
                if status != "pin_matches_file_not_authenticated")
    if input_anchor != "published_aggregate_matches":
        gaps.append("published_automated_input_anchor")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blocked" if gaps else "candidate_inputs_present_not_verified",
        "resources": resources,
        "trace_candidates": trace_candidates,
        "report_candidates": report_candidates,
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
    parser.add_argument("--trace-root", type=Path)
    parser.add_argument("--report-root", type=Path)
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
        repo_root=args.repo_root, trace_root=args.trace_root,
        report_root=args.report_root, packet_root=args.packet_root,
        canonical_root=args.canonical_root, reverse_root=args.reverse_root,
        research_manifest_path=args.research_manifest,
        research_manifest_sha256=args.research_manifest_sha256,
        coordinator_manifest_sha256=args.coordinator_manifest_sha256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(args.require_candidates and result["status"] == "blocked")


if __name__ == "__main__":
    raise SystemExit(main())

"""Coordinator-only gate linking frozen automated runs to both rater handoffs.

This is an optional pre-distribution *verification* command, not a human
assessment or a new experimental analysis. Both source manifests must have
independently retained SHA-256 pins; unpinned diagnostics cannot pass this gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from scripts import build_human_eval_packet as packet_builder
from scripts import export_human_eval_annotator_bundle as exporter
from scripts import verify_human_eval_automated_run_lineage as lineage
from scripts import verify_human_eval_counterbalanced_handoff as handoff
from scripts import verify_published_main_study_inputs as published
from scripts import verify_frozen_main_study_tasks as frozen_tasks


def _require_pin(value: str, *, label: str) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} must be 64 lowercase hexadecimal SHA-256 digits")


def _capture_sources(paths: dict[str, Path]) -> dict[str, str]:
    """Fingerprint bounded, descriptor-captured evidence without retaining reports.

    A digest is computed from each exact regular-file capture, not an
    independently reread pathname. Only a single source's bytes are held at
    a time, even when both 40-report annotator packets are included.
    """
    return {
        label: hashlib.sha256(
            packet_builder._read_regular_file_captured(path, label=label)
        ).hexdigest()
        for label, path in paths.items()
    }


def verify_automated_handoff(
    *,
    repo_root: Path,
    packet_root: Path,
    canonical_root: Path,
    reverse_root: Path,
    research_manifest_path: Path,
    expected_research_manifest_sha256: str,
    expected_coordinator_manifest_sha256: str,
    task_manifest_path: Path | None = None,
    annotator_guide_path: Path = exporter.DEFAULT_ANNOTATOR_GUIDE,
    expected_tasks: tuple[str, ...] = lineage.TASKS,
) -> dict:
    """Require both independent archival pins and both complementary checks.

    The standalone lineage and counterbalanced handoff verifiers are each
    necessary but neither alone establishes end-to-end rater-distribution
    continuity. Capture the shared files before and after both checks to reject
    observable changes across the sequential verification window.
    """
    _require_pin(expected_research_manifest_sha256, label="research manifest pin")
    _require_pin(expected_coordinator_manifest_sha256, label="coordinator manifest pin")
    if (
        type(expected_tasks) is not tuple or not expected_tasks
        or any(type(task) is not str or not task for task in expected_tasks)
        or len(set(expected_tasks)) != len(expected_tasks)
    ):
        raise ValueError("expected task IDs must be a nonempty unique tuple")
    repo_root, packet_root = Path(repo_root), Path(packet_root)
    research_manifest_path = Path(research_manifest_path)
    task_manifest_path = (
        Path(task_manifest_path) if task_manifest_path is not None
        else repo_root / "experiments/main_budget_tasks.json"
    )
    critical_paths = {
        "research manifest": research_manifest_path,
        "frozen task manifest": task_manifest_path,
        "frozen annotator guide": Path(annotator_guide_path),
        "treatment CSV": repo_root / lineage.MAIN_REL,
        "common-evaluator CSV": repo_root / lineage.SUPPORT_REL,
    }
    # Preserve every coordinator and distribution file across both verifier
    # windows, not just the anchored manifests and automated CSVs. Otherwise
    # the first verified bundle could change while the second is checked.
    for name in exporter.COORDINATOR_ARTIFACTS:
        critical_paths[f"coordinator {name}"] = packet_root / name
    for order, root in (("canonical", canonical_root), ("reverse", reverse_root)):
        for name in exporter.ANNOTATOR_ARTIFACTS:
            critical_paths[f"{order} {name}"] = Path(root) / name

    initial = _capture_sources(critical_paths)
    if initial["research manifest"] != expected_research_manifest_sha256:
        raise ValueError("research manifest does not match independently retained pin")
    if initial["coordinator manifest.json"] != expected_coordinator_manifest_sha256:
        raise ValueError("coordinator manifest does not match independently retained pin")

    # A newly pinned, internally consistent archive is not necessarily the
    # *published* 40-cell dataset. For the real frozen task matrix require
    # both external file-byte anchoring and the historical aggregate digest.
    # Noncanonical task tuples are supported only for synthetic diagnostics;
    # their receipt explicitly records that historical anchoring did not run.
    published_anchor_verified = expected_tasks == lineage.TASKS
    original_task_source_verified = False
    if published_anchor_verified:
        published.verify_published_frozen_inputs(
            repo_root=repo_root,
            manifest_path=research_manifest_path,
            expected_manifest_sha256=expected_research_manifest_sha256,
        )
        # Published CSVs do not anchor the original research questions.
        # The coordinator pin alone could be renewed after a task/packet
        # rewrite, so bind the canonical handoff to original treatment source.
        frozen_tasks.verify_frozen_task_manifest(
            repo_root=repo_root, task_manifest_path=task_manifest_path,
        )
        original_task_source_verified = True

    aligned = lineage.audit_files(
        repo_root=repo_root,
        packet_root=packet_root,
        task_manifest_path=task_manifest_path,
        research_manifest_path=research_manifest_path,
        expected_manifest_sha256=expected_research_manifest_sha256,
        expected_tasks=expected_tasks,
    )
    distributed = handoff.verify_counterbalanced_handoff(
        packet_root=packet_root,
        canonical_root=Path(canonical_root),
        reverse_root=Path(reverse_root),
        expected_coordinator_manifest_sha256=expected_coordinator_manifest_sha256,
        expected_n_reports=len(expected_tasks) * len(lineage.VARIANTS),
        task_manifest_path=task_manifest_path,
        repo_root=repo_root,
        annotator_guide_path=Path(annotator_guide_path),
    )
    # A component's status/count alone cannot authenticate the *claims* that
    # become part of the combined receipt. Reconcile source and bundle digests
    # to our own bounded capture, not only to the component's reported values.
    for component_name, receipt in (("automated lineage", aligned), ("distribution", distributed)):
        if (
            type(receipt) is not dict
            or type(receipt.get("schema_version")) is not int
            or receipt["schema_version"] != 1
            or receipt.get("study_id") != "budget-main-v1"
        ):
            raise ValueError(f"{component_name} component receipt identity differs")
    # Never promote a partial, contradictory, or non-verifying component receipt
    # to a successful joint handoff. A matching short count from *both*
    # components was previously enough to pass this composition layer.
    if aligned.get("status") != "human_packet_automated_run_lineage_consistent":
        raise ValueError("automated lineage component did not verify run identity")
    if distributed.get("status") != "human_eval_counterbalanced_handoff_verified":
        raise ValueError("counterbalanced distribution component did not verify packet")
    expected_reports = len(expected_tasks) * len(lineage.VARIANTS)
    if published_anchor_verified and expected_reports != 40:
        raise ValueError("canonical VERA handoff must cover exactly 40 cells")
    for label, actual in (
        ("automated packet reports", aligned.get("n_reports")),
        ("automated evaluator run IDs", aligned.get("run_ids_matched")),
        ("counterbalanced distribution reports", distributed.get("n_reports")),
    ):
        if type(actual) is not int or actual != expected_reports:
            raise ValueError(
                f"{label} does not cover expected {expected_reports} reports"
            )
    if aligned.get("archival_manifest_externally_pinned") is not True:
        raise ValueError("automated lineage was not independently archive-pinned")
    if type(aligned.get("n_tasks")) is not int or aligned["n_tasks"] != len(expected_tasks):
        raise ValueError("automated lineage task count differs from expected matrix")
    for flag in ("human_ratings_read", "treatment_outputs_rerun", "evaluator_outputs_rerun"):
        if aligned.get(flag) is not False:
            raise ValueError(f"automated lineage {flag} receipt contract differs")
    if distributed.get("coordinator_manifest_sha256") != expected_coordinator_manifest_sha256:
        raise ValueError("distribution component does not match the pinned coordinator manifest")
    if distributed.get("presentation_orders") != ["canonical", "reverse"]:
        raise ValueError("distribution component presentation-order contract differs")
    bundles = distributed.get("bundles")
    if type(bundles) is not dict or set(bundles) != {"canonical", "reverse"}:
        raise ValueError("distribution component bundle identities differ")
    for order in ("canonical", "reverse"):
        bundle = bundles[order]
        if type(bundle) is not dict:
            raise ValueError(f"{order} distribution component bundle receipt is invalid")
        for field, artifact in (
            ("packet_sha256", "packet.jsonl"),
            ("ratings_template_sha256", "ratings_template.csv"),
            ("annotator_guide_sha256", "annotator_instructions.md"),
        ):
            if bundle.get(field) != initial[f"{order} {artifact}"]:
                raise ValueError(
                    f"{order} distribution {field} does not match captured source bytes"
                )

    final = _capture_sources(critical_paths)
    for label in critical_paths:
        if final[label] != initial[label]:
            raise ValueError(f"{label} changed during combined handoff verification")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": (
            "automated_run_and_counterbalanced_handoff_verified"
            if published_anchor_verified else
            "noncanonical_handoff_diagnostic_not_historical_release"
        ),
        "historical_40_cell_source_checks_completed": (
            published_anchor_verified and original_task_source_verified
        ),
        "human_validation_performed": False,
        "n_reports": aligned["n_reports"],
        "run_ids_matched": aligned["run_ids_matched"],
        "research_manifest_externally_pinned": True,
        "coordinator_manifest_externally_pinned": True,
        "coordinator_manifest_sha256": expected_coordinator_manifest_sha256,
        "published_frozen_input_anchor_verified": published_anchor_verified,
        "original_treatment_run_task_manifest_verified": original_task_source_verified,
        "published_frozen_input_aggregate_sha256": (
            published.FROZEN_INPUT_AGGREGATE_SHA256
            if published_anchor_verified else None
        ),
        "presentation_orders": ["canonical", "reverse"],
        "bundle_packet_sha256": {
            order: distributed["bundles"][order]["packet_sha256"]
            for order in ("canonical", "reverse")
        },
        "bundle_manifest_sha256": {
            order: initial[f"{order} annotator_manifest.json"]
            for order in ("canonical", "reverse")
        },
        "human_ratings_read": False,
        "treatment_outputs_rerun": False,
        "evaluator_outputs_rerun": False,
        "interpretation": (
            "Coordinator-only pre-distribution source/run alignment, not "
            "an atomic archive snapshot, proof of independent human rating, "
            "or evidence of human-validation outcomes; noncanonical task "
            "diagnostics verify neither the historical published-input "
            "nor original treatment-run task source anchors"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=lineage.ROOT)
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--reverse-root", type=Path, required=True)
    parser.add_argument("--research-manifest", type=Path, required=True)
    parser.add_argument("--research-manifest-sha256", required=True)
    parser.add_argument("--coordinator-manifest-sha256", required=True)
    parser.add_argument("--task-manifest", type=Path)
    parser.add_argument("--annotator-guide", type=Path, default=exporter.DEFAULT_ANNOTATOR_GUIDE)
    args = parser.parse_args()
    try:
        receipt = verify_automated_handoff(
            repo_root=args.repo_root,
            packet_root=args.packet_root,
            canonical_root=args.canonical_root,
            reverse_root=args.reverse_root,
            research_manifest_path=args.research_manifest,
            expected_research_manifest_sha256=args.research_manifest_sha256,
            expected_coordinator_manifest_sha256=args.coordinator_manifest_sha256,
            task_manifest_path=args.task_manifest,
            annotator_guide_path=args.annotator_guide,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"automated-to-human handoff verification failed: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

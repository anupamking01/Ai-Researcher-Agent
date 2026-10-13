"""Verify and independently recompute a human-evaluation analysis result bundle.

The canonical JSON is the machine-readable human-validation result. Markdown is
only a deterministic rendering of that JSON. The manifest must bind both output
byte streams and the exact analysis implementation source files used to produce
them. The command-line verifier additionally recomputes the complete payload
from retained frozen ratings and exact governing inputs. It makes no model/API
calls, generates no ratings, and reruns no treatments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts import analyze_human_eval
from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as core

DEFAULT_OUTPUT_ROOT = analyze_human_eval.OUTPUT_ROOT


def _require_finite_json(value, *, label: str, path: str = "$") -> None:
    """Reject non-finite JSON numbers, including exponent overflow, at any depth."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} has a non-finite numeric value at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _require_finite_json(child, label=label, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _require_finite_json(child, label=label, path=f"{path}[{index}]")


def _regular_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _load_json(content: bytes, *, label: str) -> dict:
    # A valid fingerprint cannot resolve ambiguous duplicate JSON members.
    # Decode escape-equivalent keys before checking, at every object depth.
    def unique_object_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"{label} contains duplicate JSON key {key!r}")
            obj[key] = value
        return obj

    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=unique_object_pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    _require_finite_json(payload, label=label)
    return payload


def _fingerprint(content: bytes) -> dict:
    return {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _canonical_json_bytes(value) -> bytes:
    """Encode JSON with type distinctions preserved for exact comparisons."""
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _retained_rating_paths(freeze_root: Path) -> list[Path]:
    raw_root = Path(freeze_root) / "raw_rating_inputs"
    if raw_root.is_symlink() or not raw_root.is_dir():
        raise ValueError(
            f"retained raw rating archive must be a regular directory: {raw_root}"
        )
    children = sorted(raw_root.iterdir(), key=lambda path: path.name)
    if not children:
        raise ValueError(f"retained raw rating archive is empty: {raw_root}")
    for path in children:
        if path.is_symlink() or not path.is_file() or path.suffix != ".csv":
            raise ValueError(
                "retained raw rating archive contains an undeclared or non-regular "
                f"artifact: {path}"
            )
    return children


def _require_equal(actual, expected, *, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def _verify_entry(entry, *, expected_path: str, content: bytes, label: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} manifest entry must be an object")
    _require_equal(entry.get("path"), expected_path, label=f"{label} path")
    _require_equal(
        {"bytes": entry.get("bytes"), "sha256": entry.get("sha256")},
        _fingerprint(content),
        label=f"{label} fingerprint",
    )


def _validate_analysis_identity(payload: dict) -> None:
    required = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests": "none_predeclared_for_human_validation",
        "report_score_aggregation": "mean_observed_rater_scores_per_report_dimension",
        "bootstrap_seed": core.SEED,
        "bootstrap_draws": core.BOOTSTRAP_DRAWS,
    }
    for key, expected in required.items():
        _require_equal(payload.get(key), expected, label=f"analysis {key}")

    _require_equal(payload.get("variants"), list(core.VARIANTS), label="analysis variants")
    _require_equal(payload.get("dimensions"), list(core.DIMS), label="analysis dimensions")

    verification = payload.get("verification")
    if not isinstance(verification, dict):
        raise ValueError("analysis verification must be an object")
    snapshot_bound = verification.get("analysis_inputs_snapshot_bound")
    if snapshot_bound is not True:
        raise ValueError(
            "analysis input snapshot binding mismatch: "
            f"expected literal true, got {snapshot_bound!r}"
        )

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("analysis provenance must be an object")
    plan_entry = provenance.get("analysis_plan")
    if not isinstance(plan_entry, dict):
        raise ValueError("analysis plan provenance must be an object")
    plan_bytes = _regular_bytes(core.PLAN, label="current frozen human-analysis plan")
    expected_plan = _fingerprint(plan_bytes)
    _require_equal(
        expected_plan["sha256"],
        core.FROZEN_ANALYSIS_PLAN_SHA256,
        label="current frozen analysis plan fingerprint",
    )
    _require_equal(
        {
            "bytes": plan_entry.get("bytes"),
            "sha256": plan_entry.get("sha256"),
        },
        expected_plan,
        label="analysis plan provenance",
    )


def verify_bundle(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    """Verify exact outputs, deterministic rendering, and implementation hashes."""
    output_root = Path(output_root)
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError(f"human-analysis output root must be a regular directory: {output_root}")

    json_path = output_root / analyze_human_eval.ANALYSIS_JSON
    markdown_path = output_root / analyze_human_eval.ANALYSIS_MARKDOWN
    manifest_path = output_root / analyze_human_eval.ANALYSIS_MANIFEST

    json_bytes = _regular_bytes(json_path, label="canonical human-analysis JSON")
    markdown_bytes = _regular_bytes(markdown_path, label="human-analysis Markdown")
    manifest_bytes = _regular_bytes(manifest_path, label="human-analysis output manifest")

    payload = _load_json(json_bytes, label="canonical human-analysis JSON")
    manifest = _load_json(manifest_bytes, label="human-analysis output manifest")
    _validate_analysis_identity(payload)

    expected_markdown = analyze_human_eval.render_markdown(payload).encode("utf-8")
    if markdown_bytes != expected_markdown:
        raise ValueError(
            "human-analysis Markdown does not match canonical JSON; regenerate the "
            "bundle instead of editing manuscript-facing results by hand"
        )

    _require_equal(manifest.get("schema_version"), 1, label="manifest schema_version")
    _require_equal(manifest.get("study_id"), payload["study_id"], label="manifest study_id")
    _require_equal(
        manifest.get("status"),
        "human_validation_analysis_bundle",
        label="manifest status",
    )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("analysis manifest artifacts must be an object")
    _require_equal(
        set(artifacts),
        {"canonical_analysis", "manuscript_rendering"},
        label="analysis manifest artifact set",
    )
    _verify_entry(
        artifacts["canonical_analysis"],
        expected_path=analyze_human_eval.ANALYSIS_JSON,
        content=json_bytes,
        label="canonical analysis",
    )
    _verify_entry(
        artifacts["manuscript_rendering"],
        expected_path=analyze_human_eval.ANALYSIS_MARKDOWN,
        content=markdown_bytes,
        label="manuscript rendering",
    )

    implementation = manifest.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("analysis manifest implementation must be an object")
    _require_equal(
        set(implementation),
        {"analysis_core", "analysis_renderer", "analysis_verifier"},
        label="analysis manifest implementation set",
    )

    core_bytes = _regular_bytes(Path(core.__file__), label="current human-analysis core")
    renderer_bytes = _regular_bytes(
        Path(analyze_human_eval.__file__),
        label="current human-analysis renderer",
    )
    verifier_bytes = _regular_bytes(
        Path(__file__),
        label="current human-analysis verifier",
    )
    _verify_entry(
        implementation["analysis_core"],
        expected_path="scripts/human_eval_analysis_core.py",
        content=core_bytes,
        label="analysis core implementation",
    )
    _verify_entry(
        implementation["analysis_renderer"],
        expected_path="scripts/analyze_human_eval.py",
        content=renderer_bytes,
        label="analysis renderer implementation",
    )
    _verify_entry(
        implementation["analysis_verifier"],
        expected_path="scripts/verify_human_eval_analysis_outputs.py",
        content=verifier_bytes,
        label="analysis verifier implementation",
    )

    return {
        "schema_version": 1,
        "study_id": payload["study_id"],
        "status": "human_validation_analysis_bundle_verified",
        "analysis_scope": payload["analysis_scope"],
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "canonical_analysis_sha256": _fingerprint(json_bytes)["sha256"],
        "manuscript_rendering_sha256": _fingerprint(markdown_bytes)["sha256"],
        "output_manifest_sha256": _fingerprint(manifest_bytes)["sha256"],
        "implementation_bound": True,
        "independent_recomputation_verified": False,
    }


def verify_bundle_against_inputs(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    rating_paths=None,
    freeze_root: Path = core.FREEZE_ROOT,
    packet_root: Path = core.PACKET_ROOT,
    packet_path: Path = freeze.DEFAULT_PACKET,
    protocol_path: Path = freeze.DEFAULT_PROTOCOL,
    assignment_plan_path: Path = freeze.DEFAULT_ASSIGNMENT_PLAN,
    analysis_plan_path: Path = core.PLAN,
    task_manifest_path: Path = core.TASKS,
    repo_root: Path = core.ROOT,
) -> dict:
    """Verify bundle integrity, then independently recompute its full payload."""
    output_root = Path(output_root)
    receipt = verify_bundle(output_root)

    # Capture the complete published bundle only after ordinary manifest and
    # rendering checks pass, and bind every captured stream to that receipt.
    # These are the exact bytes that must remain in place while the slower
    # independent recomputation runs.
    output_specs = {
        "canonical human-analysis JSON": (
            output_root / analyze_human_eval.ANALYSIS_JSON,
            "canonical_analysis_sha256",
        ),
        "human-analysis Markdown": (
            output_root / analyze_human_eval.ANALYSIS_MARKDOWN,
            "manuscript_rendering_sha256",
        ),
        "human-analysis output manifest": (
            output_root / analyze_human_eval.ANALYSIS_MANIFEST,
            "output_manifest_sha256",
        ),
    }
    captured_outputs = {}
    for label, (path, receipt_key) in output_specs.items():
        content = _regular_bytes(path, label=label)
        _require_equal(
            _fingerprint(content)["sha256"],
            receipt[receipt_key],
            label=f"{label} stability",
        )
        captured_outputs[label] = content
    payload = _load_json(
        captured_outputs["canonical human-analysis JSON"],
        label="canonical human-analysis JSON",
    )

    from_retained_archive = rating_paths is None
    if from_retained_archive:
        # Validate the retained archive layout here, but let the blinded freeze
        # verifier consume its declared archive paths. Passing those numbered
        # archive names as if they were external inputs would incorrectly compare
        # them with the original source filenames recorded in the manifest.
        _retained_rating_paths(freeze_root)
        analysis_rating_paths = []
    else:
        analysis_rating_paths = [Path(path) for path in rating_paths]
        if not analysis_rating_paths:
            raise ValueError("independent recomputation requires at least one rating file")

    recomputed = core.analyze(
        analysis_rating_paths,
        freeze_root=freeze_root,
        packet_root=packet_root,
        packet_path=packet_path,
        protocol_path=protocol_path,
        assignment_plan_path=assignment_plan_path,
        analysis_plan_path=analysis_plan_path,
        task_manifest_path=task_manifest_path,
        repo_root=repo_root,
    )

    for label, (path, _receipt_key) in output_specs.items():
        if _regular_bytes(path, label=label) != captured_outputs[label]:
            raise ValueError(f"{label} changed during independent recomputation")

    if _canonical_json_bytes(payload) != _canonical_json_bytes(recomputed):
        raise ValueError(
            "canonical result does not match independently recomputed human analysis"
        )

    receipt["independent_recomputation_verified"] = True
    receipt["recomputed_from_retained_ratings"] = from_retained_archive
    receipt["outputs_stable_during_independent_recomputation"] = True
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratings", nargs="*", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--freeze-root", type=Path, default=core.FREEZE_ROOT)
    parser.add_argument("--packet-root", type=Path, default=core.PACKET_ROOT)
    parser.add_argument("--packet", type=Path, default=freeze.DEFAULT_PACKET)
    parser.add_argument("--protocol", type=Path, default=freeze.DEFAULT_PROTOCOL)
    parser.add_argument(
        "--assignment-plan", type=Path, default=freeze.DEFAULT_ASSIGNMENT_PLAN
    )
    parser.add_argument("--analysis-plan", type=Path, default=core.PLAN)
    parser.add_argument("--task-manifest", type=Path, default=core.TASKS)
    parser.add_argument("--repo-root", type=Path, default=core.ROOT)
    args = parser.parse_args()
    try:
        receipt = verify_bundle_against_inputs(
            args.output_root,
            rating_paths=args.ratings or None,
            freeze_root=args.freeze_root,
            packet_root=args.packet_root,
            packet_path=args.packet,
            protocol_path=args.protocol,
            assignment_plan_path=args.assignment_plan,
            analysis_plan_path=args.analysis_plan,
            task_manifest_path=args.task_manifest,
            repo_root=args.repo_root,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL ANALYSIS VERIFY: FAIL: {exc}") from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL ANALYSIS VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

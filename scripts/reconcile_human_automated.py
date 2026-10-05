"""Compute and publish the frozen descriptive automated-human reconciliation.

This module does not create ratings, rerun treatments/evaluators, add hypothesis
tests, or alter the confirmatory automated analysis. It only executes the
pre-frozen descriptive reconciliation contract after the readiness gate passes.

Published reconciliation results are create-only: canonical JSON is the source
of truth, manuscript Markdown is a deterministic rendering, and a manifest binds
both artifacts, the verified upstream inputs, the producing Git commit, and the
exact reconciliation implementation bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import subprocess
from pathlib import Path

from scripts import verify_human_reconciliation_readiness as readiness

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "human_eval" / "reconciliation-v1"
RECONCILIATION_JSON = "reconciliation.json"
RECONCILIATION_MARKDOWN = "reconciliation.md"
RECONCILIATION_MANIFEST = "reconciliation_manifest.json"

CATEGORIES = (
    "concordant_positive",
    "concordant_negative",
    "discordant",
    "automated_tie",
    "human_tie",
    "both_tie",
)


def _category(automated_difference: float, human_difference: float) -> str:
    """Classify two directional differences according to the frozen contract."""
    if automated_difference == 0 and human_difference == 0:
        return "both_tie"
    if automated_difference == 0:
        return "automated_tie"
    if human_difference == 0:
        return "human_tie"
    if automated_difference > 0 and human_difference > 0:
        return "concordant_positive"
    if automated_difference < 0 and human_difference < 0:
        return "concordant_negative"
    return "discordant"


def _dimension_result(tasks, automated_result, human_result):
    auto_by_task = dict(zip(tasks, automated_result["task_differences"]))
    included = list(human_result["task_ids_included"])
    missing = list(human_result["missing_pair_tasks"])
    human_by_task = human_result["task_differences"]

    taskwise = []
    counts = {category: 0 for category in CATEGORIES}
    automated_values = []
    human_values = []
    for task_id in included:
        automated_difference = float(auto_by_task[task_id])
        human_difference = float(human_by_task[task_id])
        category = _category(automated_difference, human_difference)
        counts[category] += 1
        automated_values.append(automated_difference)
        human_values.append(human_difference)
        taskwise.append(
            {
                "task_id": task_id,
                "automated_difference": automated_difference,
                "human_difference": human_difference,
                "direction_category": category,
            }
        )

    denominator = (
        counts["concordant_positive"]
        + counts["concordant_negative"]
        + counts["discordant"]
    )
    if included:
        automated_mean = statistics.mean(automated_values)
        human_mean = statistics.mean(human_values)
        mean_category = _category(automated_mean, human_mean)
    else:
        automated_mean = None
        human_mean = None
        mean_category = None

    return {
        "n_comparable_tasks": len(included),
        "task_ids_included": included,
        "missing_pair_tasks": missing,
        "direction_category_counts": counts,
        "non_tie_directional_concordance": (
            (counts["concordant_positive"] + counts["concordant_negative"]) / denominator
            if denominator
            else None
        ),
        "mean_automated_difference_on_comparable_tasks": automated_mean,
        "mean_human_difference_on_comparable_tasks": human_mean,
        "mean_direction_category": mean_category,
        "taskwise": taskwise,
    }


def reconcile_payloads(automated: dict, human: dict) -> dict:
    """Execute only the descriptive operations frozen before human unblinding."""
    identity = readiness.validate_payloads(automated, human)
    tasks = identity["task_ids"]

    results = {}
    for contrast in readiness.CONTRASTS:
        results[contrast] = {}
        automated_result = automated["primary_contrasts"][contrast]
        for dimension in readiness.DIMS:
            results[contrast][dimension] = _dimension_result(
                tasks,
                automated_result,
                human["paired_contrasts"][contrast][dimension],
            )

    return {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "status": "automated_human_descriptive_reconciliation",
        "analysis_scope": "descriptive_reconciliation_only",
        "primary_outcome": "strict_support_rate",
        "human_dimensions": list(readiness.DIMS),
        "contrasts": list(readiness.CONTRASTS),
        "task_ids": tasks,
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests_added": False,
        "method": {
            "task_pairing": "same_frozen_task_id",
            "missingness": "preserve_missing_human_pairs_without_imputation",
            "direction_categories": list(CATEGORIES),
            "non_tie_directional_concordance_denominator": (
                "concordant_positive + concordant_negative + discordant"
            ),
            "inference": "descriptive_only",
        },
        "results": results,
    }


def reconcile_verified(root=ROOT, human_root=None, contract=None) -> dict:
    """Run reconciliation from bytes bound to a passing readiness receipt."""
    root = Path(root)
    human_root = Path(human_root) if human_root else root / readiness.HUMAN_ROOT
    contract = Path(contract) if contract else root / readiness.CONTRACT

    receipt = readiness.verify_readiness(
        root=root,
        human_root=human_root,
        contract=contract,
    )

    paths = {
        "automated_analysis": root / readiness.AUTO_JSON,
        "human_analysis": human_root / "analysis.json",
    }
    captured = {
        name: readiness._regular_bytes(path, name)
        for name, path in paths.items()
    }
    verified = receipt["verified_input_fingerprints"]
    for name, content in captured.items():
        current = readiness._fingerprint(content)
        readiness._require(
            current == verified.get(name),
            f"{name} changed after readiness verification",
        )

    result = reconcile_payloads(
        readiness._load(captured["automated_analysis"], "automated analysis"),
        readiness._load(captured["human_analysis"], "human analysis"),
    )
    result["verified_input_fingerprints"] = verified
    result["verification"] = {
        **receipt["verification"],
        "reconciliation_inputs_bound_to_readiness_receipt": True,
    }
    return result


def render_markdown(payload: dict) -> str:
    """Render a compact manuscript-facing view deterministically from canonical JSON."""
    lines = [
        "# Automated–human descriptive reconciliation",
        "",
        "Descriptive reconciliation only; automated confirmatory and human-validation "
        "claims remain separate.",
        "",
        "| Contrast | Human dimension | Comparable tasks | Non-tie concordance | Mean direction |",
        "|---|---|---:|---:|---|",
    ]
    for contrast in readiness.CONTRASTS:
        for dimension in readiness.DIMS:
            block = payload["results"][contrast][dimension]
            concordance = block["non_tie_directional_concordance"]
            concordance_text = "NA" if concordance is None else f"{concordance:.3f}"
            mean_direction = block["mean_direction_category"] or "NA"
            lines.append(
                f"| {contrast} | {dimension} | {block['n_comparable_tasks']} | "
                f"{concordance_text} | {mean_direction} |"
            )
    lines += [
        "",
        "Missing human pairs are preserved without imputation. No reconciliation "
        "p-values, multiplicity rules, correlations, composite scores, or treatment-"
        "validation thresholds are added.",
        "",
    ]
    return "\n".join(lines)


def _fingerprint_bytes(content: bytes) -> dict:
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _regular_file_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _implementation_fingerprint(path: Path, *, logical_path: str) -> dict:
    content = _regular_file_bytes(path, label=f"reconciliation implementation {logical_path}")
    return {"path": logical_path, **_fingerprint_bytes(content)}


def _producer_commit(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("unable to resolve producing Git commit") from exc
    sha = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("producing Git commit must be a full 40-character SHA")
    return sha


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with Path(path).open("xb") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite reconciliation artifact: {path}") from exc


def write_bundle(payload: dict, output_root: Path, *, root: Path = ROOT) -> dict:
    """Publish and independently verify a create-only reconciliation bundle."""
    output_root = Path(output_root)
    try:
        output_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError(
            f"refusing to overwrite reconciliation output: {output_root}"
        ) from exc

    json_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    markdown_bytes = render_markdown(payload).encode("utf-8")

    json_path = output_root / RECONCILIATION_JSON
    markdown_path = output_root / RECONCILIATION_MARKDOWN
    manifest_path = output_root / RECONCILIATION_MANIFEST

    _write_exclusive(json_path, json_bytes)
    _write_exclusive(markdown_path, markdown_bytes)

    verified_inputs = payload.get("verified_input_fingerprints")
    if not isinstance(verified_inputs, dict) or not verified_inputs:
        raise ValueError("reconciliation payload lacks verified input fingerprints")

    manifest = {
        "schema_version": 1,
        "study_id": payload.get("study_id"),
        "status": "automated_human_reconciliation_bundle",
        "producer_git_commit": _producer_commit(Path(root)),
        "verified_input_fingerprints": verified_inputs,
        "artifacts": {
            "canonical_reconciliation": {
                "path": RECONCILIATION_JSON,
                **_fingerprint_bytes(json_bytes),
            },
            "manuscript_rendering": {
                "path": RECONCILIATION_MARKDOWN,
                **_fingerprint_bytes(markdown_bytes),
            },
        },
        "implementation": {
            "reconciler": _implementation_fingerprint(
                Path(__file__),
                logical_path="scripts/reconcile_human_automated.py",
            ),
            "readiness_gate": _implementation_fingerprint(
                Path(readiness.__file__),
                logical_path="scripts/verify_human_reconciliation_readiness.py",
            ),
        },
        "integrity_note": (
            "Canonical JSON is the source of truth. The deterministic Markdown, "
            "upstream verified-input fingerprints, producing Git commit, and exact "
            "implementation source bytes are bound here. The verifier independently "
            "recomputes the frozen descriptive reconciliation before success."
        ),
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_exclusive(manifest_path, manifest_bytes)

    from scripts.verify_human_reconciliation_outputs import verify_bundle

    return verify_bundle(output_root, root=Path(root))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--human-root", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    try:
        result = reconcile_verified(args.root, args.human_root, args.contract)
        write_bundle(result, args.output_root, root=args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"HUMAN RECONCILIATION: FAIL: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    print("HUMAN RECONCILIATION: PASS (result bundle verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

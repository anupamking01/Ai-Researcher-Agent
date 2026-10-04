"""Compute the frozen descriptive automated-human reconciliation.

This module does not create ratings, rerun treatments/evaluators, add hypothesis
tests, or alter the confirmatory automated analysis. It only executes the
pre-frozen descriptive reconciliation contract after the readiness gate passes.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from scripts import verify_human_reconciliation_readiness as readiness

ROOT = Path(__file__).resolve().parents[1]

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--human-root", type=Path)
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    try:
        result = reconcile_verified(args.root, args.human_root, args.contract)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"HUMAN RECONCILIATION: FAIL: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    print("HUMAN RECONCILIATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

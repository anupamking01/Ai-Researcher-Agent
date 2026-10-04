"""Synthetic-only tests for the automated-human reconciliation readiness gate."""

import copy
import statistics

import pytest

from scripts import verify_human_reconciliation_readiness as readiness


def _summary(diffs):
    return {
        "n_pairs": len(diffs),
        "mean_difference": statistics.mean(diffs) if diffs else None,
        "positive_tasks": sum(x > 0 for x in diffs),
        "negative_tasks": sum(x < 0 for x in diffs),
        "tied_tasks": sum(x == 0 for x in diffs),
    }


def _payloads():
    tasks = [f"main-{index:02d}" for index in range(1, 11)]
    base_diffs = [0.25, -0.5, 0.0, 0.25, -0.25, 0.5, 0.0, 0.25, -0.25, 0.0]
    automated = {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "n_tasks": len(tasks),
        "task_ids": tasks,
        "primary_outcome": "strict_support_rate",
        "primary_contrasts": {},
    }
    for name in readiness.CONTRASTS:
        automated["primary_contrasts"][name] = {
            **_summary(base_diffs),
            "task_differences": list(base_diffs),
        }

    human = {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests": "none_predeclared_for_human_validation",
        "n_tasks": len(tasks),
        "task_ids": tasks,
        "dimensions": list(readiness.DIMS),
        "paired_contrasts": {},
    }
    for name in readiness.CONTRASTS:
        human["paired_contrasts"][name] = {}
        for dimension in readiness.DIMS:
            diffs = {task: base_diffs[index] for index, task in enumerate(tasks)}
            human["paired_contrasts"][name][dimension] = {
                **_summary(list(diffs.values())),
                "task_ids_included": list(tasks),
                "missing_pair_tasks": [],
                "task_differences": diffs,
            }
    return automated, human


def test_valid_synthetic_inputs_pass_without_computing_reconciliation_results():
    automated, human = _payloads()
    receipt = readiness.validate_payloads(automated, human)
    assert receipt["status"] == "automated_human_reconciliation_identity_valid"
    assert receipt["analysis_scope"] == "descriptive_reconciliation_only"
    assert receipt["human_ratings_generated"] is False
    assert receipt["treatment_outputs_rerun"] is False
    assert receipt["hypothesis_tests_added"] is False
    assert "results" not in receipt


def test_missing_human_pair_remains_explicit_and_is_not_imputed():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    dimension = readiness.DIMS[0]
    block = human["paired_contrasts"][name][dimension]
    missing_task = human["task_ids"][-1]
    block["task_ids_included"] = human["task_ids"][:-1]
    block["missing_pair_tasks"] = [missing_task]
    block["task_differences"].pop(missing_task)
    diffs = list(block["task_differences"].values())
    block.update(_summary(diffs))

    receipt = readiness.validate_payloads(automated, human)
    assert receipt["status"] == "automated_human_reconciliation_identity_valid"


def test_ordered_task_identity_mismatch_is_rejected():
    automated, human = _payloads()
    human["task_ids"] = list(reversed(human["task_ids"]))
    with pytest.raises(ValueError, match="ordered task identity mismatch"):
        readiness.validate_payloads(automated, human)


def test_human_missingness_must_partition_the_frozen_task_set():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    dimension = readiness.DIMS[0]
    human["paired_contrasts"][name][dimension]["missing_pair_tasks"] = [
        human["task_ids"][0]
    ]
    with pytest.raises(ValueError, match="partition frozen tasks"):
        readiness.validate_payloads(automated, human)


def test_human_task_difference_summary_drift_is_rejected():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    dimension = readiness.DIMS[0]
    human["paired_contrasts"][name][dimension]["mean_difference"] = 99.0
    with pytest.raises(ValueError, match="mean_difference inconsistent"):
        readiness.validate_payloads(automated, human)


def test_posthoc_dimension_or_contrast_selection_is_rejected():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    human["paired_contrasts"][name].pop(readiness.DIMS[-1])
    with pytest.raises(ValueError, match="dimensions mismatch"):
        readiness.validate_payloads(automated, human)

    automated, human = _payloads()
    human["paired_contrasts"].pop(readiness.CONTRASTS[-1])
    with pytest.raises(ValueError, match="human contrast set mismatch"):
        readiness.validate_payloads(automated, human)

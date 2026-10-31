"""Synthetic-only tests for the frozen reconciliation execution."""

import statistics

from scripts import reconcile_human_automated as reconcile
from scripts import verify_human_reconciliation_readiness as readiness


def _summary(values):
    return {
        "n_pairs": len(values),
        "mean_difference": statistics.mean(values) if values else None,
        "positive_tasks": sum(value > 0 for value in values),
        "negative_tasks": sum(value < 0 for value in values),
        "tied_tasks": sum(value == 0 for value in values),
    }


def _payloads():
    tasks = [f"main-{i:02d}" for i in range(1, 11)]
    auto_diffs = [0.5, -0.5, 0.0, 0.5, -0.5, 0.25, -0.25, 0.0, 0.5, -0.5]
    human_diffs = [1.0, -1.0, 1.0, -1.0, 0.0, 1.0, -1.0, 0.0, 0.5, 0.5]
    automated = {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "n_tasks": len(tasks),
        "task_ids": tasks,
        "primary_outcome": "strict_support_rate",
        "primary_contrasts": {},
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
    for contrast in readiness.CONTRASTS:
        automated["primary_contrasts"][contrast] = {
            **_summary(auto_diffs),
            "task_differences": list(auto_diffs),
        }
        human["paired_contrasts"][contrast] = {}
        for dimension in readiness.DIMS:
            human["paired_contrasts"][contrast][dimension] = {
                **_summary(human_diffs),
                "task_ids_included": list(tasks),
                "missing_pair_tasks": [],
                "task_differences": dict(zip(tasks, human_diffs)),
            }
    return automated, human


def test_frozen_categories_and_non_tie_concordance():
    automated, human = _payloads()
    result = reconcile.reconcile_payloads(automated, human)
    block = result["results"][readiness.CONTRASTS[0]][readiness.DIMS[0]]
    assert block["direction_category_counts"] == {
        "concordant_positive": 3,
        "concordant_negative": 2,
        "discordant": 2,
        "automated_tie": 1,
        "human_tie": 1,
        "both_tie": 1,
    }
    assert block["non_tie_directional_concordance"] == 5 / 7


def test_missing_human_pairs_remain_missing():
    automated, human = _payloads()
    contrast, dimension = readiness.CONTRASTS[0], readiness.DIMS[0]
    block = human["paired_contrasts"][contrast][dimension]
    missing = human["task_ids"][-2:]
    block["task_ids_included"] = human["task_ids"][:-2]
    block["missing_pair_tasks"] = missing
    for task in missing:
        block["task_differences"].pop(task)
    observed = [block["task_differences"][task] for task in block["task_ids_included"]]
    block.update(_summary(observed))

    result = reconcile.reconcile_payloads(automated, human)
    actual = result["results"][contrast][dimension]
    assert actual["n_comparable_tasks"] == 8
    assert actual["missing_pair_tasks"] == missing
    assert [row["task_id"] for row in actual["taskwise"]] == human["task_ids"][:-2]


def test_all_ties_report_na_non_tie_concordance():
    automated, human = _payloads()
    for contrast in readiness.CONTRASTS:
        auto = automated["primary_contrasts"][contrast]
        auto["task_differences"] = [0.0] * 10
        auto.update(_summary(auto["task_differences"]))
        for dimension in readiness.DIMS:
            block = human["paired_contrasts"][contrast][dimension]
            block["task_differences"] = {task: 0.0 for task in human["task_ids"]}
            block.update(_summary([0.0] * 10))
    result = reconcile.reconcile_payloads(automated, human)
    block = result["results"][readiness.CONTRASTS[0]][readiness.DIMS[0]]
    assert block["non_tie_directional_concordance"] is None
    assert block["mean_direction_category"] == "both_tie"

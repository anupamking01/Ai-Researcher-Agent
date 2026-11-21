"""Synthetic cross-stage denominator checks; no real annotator data is created."""
import copy

import pytest

from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verify


TASKS = ("synthetic-task-a", "synthetic-task-b")


def _fixture(counts=None):
    counts = counts or {
        (variant, task): 2 for variant in core.VARIANTS for task in TASKS
    }
    summary = {}
    for variant in core.VARIANTS:
        observed = [counts[(variant, task)] for task in TASKS]
        raw = sum(observed)
        summary[variant] = {
            field: {
                "n_reports_total": len(TASKS),
                "n_reports_scored": sum(value > 0 for value in observed),
                "n_raw_scores": raw,
                "raw_score_distribution": {
                    str(n): raw if n == 3 else 0 for n in range(1, 6)
                },
            }
            for field in core.DIMS
        }
    contrasts = {}
    for left, right, name in core.CONTRASTS:
        groups = {cell: [] for cell in core.RATER_COVERAGE_CELLS}
        for task in TASKS:
            groups[f"{counts[(left, task)]}/{counts[(right, task)]}"].append(task)
        included = [
            task for task in TASKS
            if counts[(left, task)] > 0 and counts[(right, task)] > 0
        ]
        block = {
            "n_pairs": len(included),
            "task_ids_included": included,
            "missing_pair_tasks": [task for task in TASKS if task not in included],
            "rater_coverage": {
                "count_by_rater_pair": {
                    cell: len(ids) for cell, ids in groups.items()
                },
                "task_ids_by_rater_pair": groups,
            },
        }
        contrasts[name] = {field: copy.deepcopy(block) for field in core.DIMS}

    values = list(counts.values())
    single = sum(n == 1 for n in values)
    missingness = {
        "n_double_rated": sum(n == 2 for n in values),
        "n_annotator_a_only_rated": single // 2,
        "n_annotator_b_only_rated": single - single // 2,
        "n_neither_rated": sum(n == 0 for n in values),
    }
    return {
        "n_tasks": len(TASKS),
        "task_ids": list(TASKS),
        "variant_summary": summary,
        "paired_contrasts": contrasts,
        "pre_unblinding_agreement": {
            "n_annotators": 2,
            "pairwise": [{
                "n_shared_items": len(TASKS) * len(core.VARIANTS),
                "dimensions": {
                    field: dict(missingness) for field in core.DIMS
                },
            }],
        },
    }


def _check(payload):
    verify._validate_paired_rater_coverage(payload)
    verify._validate_rating_denominator_lineage(payload)


def test_all_double_rated_evidence_lineage_is_valid():
    _check(_fixture())


@pytest.mark.parametrize("key,bad_value", [
    ("n_reports_total", 3),
    ("n_reports_scored", 1),
    ("n_raw_scores", 3),
    ("n_raw_scores", True),
])
def test_rejects_variant_summary_claims_that_disagree_with_coverage(key, bad_value):
    payload = _fixture()
    payload["variant_summary"]["D3"][core.DIMS[0]][key] = bad_value
    # Existing contrast-local and shared-arm checks cannot see summary totals.
    verify._validate_paired_rater_coverage(payload)
    with pytest.raises(ValueError, match="variant summary"):
        verify._validate_rating_denominator_lineage(payload)


@pytest.mark.parametrize("bad_distribution", [
    {"1": 0, "2": 0, "3": 3, "4": 0, "5": 0},
    {"1": 0, "2": 0, "3": 4, "4": -1, "5": 1},
    {"1": 0, "2": 0, "3": 4, "4": 0, "5": True},
    {"1": 0, "2": 0, "3": 4, "4": 0, "5": 0, "6": 0},
])
def test_rejects_invalid_independent_score_distributions(bad_distribution):
    payload = _fixture()
    payload["variant_summary"]["D6"][core.DIMS[1]][
        "raw_score_distribution"
    ] = bad_distribution
    with pytest.raises(ValueError, match="raw-score distribution"):
        _check(payload)


@pytest.mark.parametrize("key", [
    "n_double_rated", "n_annotator_a_only_rated",
    "n_annotator_b_only_rated", "n_neither_rated",
])
def test_rejects_blinded_missingness_disagreeing_with_coverage(key):
    payload = _fixture()
    payload["pre_unblinding_agreement"]["pairwise"][0][
        "dimensions"
    ][core.DIMS[2]][key] += 1
    verify._validate_paired_rater_coverage(payload)
    with pytest.raises(ValueError, match="pre-unblinding agreement missingness"):
        verify._validate_rating_denominator_lineage(payload)


def test_rejects_false_blinded_shared_report_total():
    payload = _fixture()
    payload["pre_unblinding_agreement"]["pairwise"][0]["n_shared_items"] = 7
    with pytest.raises(ValueError, match="blinded shared-report count"):
        _check(payload)


def test_rejects_mismatch_in_task_denominator():
    payload = _fixture()
    payload["n_tasks"] = len(TASKS) + 1
    with pytest.raises(ValueError, match="frozen task denominator"):
        _check(payload)


def test_legitimate_singletons_and_complete_missingness_pass_without_imputation():
    counts = {
        ("D3", TASKS[0]): 0,
        ("D3", TASKS[1]): 2,
        ("D6", TASKS[0]): 1,
        ("D6", TASKS[1]): 2,
        ("P6", TASKS[0]): 2,
        ("P6", TASKS[1]): 1,
        ("P6V", TASKS[0]): 2,
        ("P6V", TASKS[1]): 0,
    }
    payload = _fixture(counts)
    _check(payload)
    assert sum(
        payload["variant_summary"][variant][core.DIMS[0]]["n_raw_scores"]
        for variant in core.VARIANTS
    ) == 10
    agreement = payload["pre_unblinding_agreement"]["pairwise"][0][
        "dimensions"
    ][core.DIMS[0]]
    assert agreement == {
        "n_double_rated": 4,
        "n_annotator_a_only_rated": 1,
        "n_annotator_b_only_rated": 1,
        "n_neither_rated": 2,
    }


def test_blinded_singleton_annotator_identity_cannot_be_inferred_from_counts():
    counts = {
        (variant, task): 1
        for variant in core.VARIANTS for task in TASKS
    }
    payload = _fixture(counts)
    agreement = payload["pre_unblinding_agreement"]["pairwise"][0]["dimensions"]
    for field in core.DIMS:
        agreement[field]["n_annotator_a_only_rated"] = 8
        agreement[field]["n_annotator_b_only_rated"] = 0
    _check(payload)


def test_rejects_non_integer_blinded_count():
    payload = _fixture()
    payload["pre_unblinding_agreement"]["pairwise"][0][
        "dimensions"
    ][core.DIMS[3]]["n_double_rated"] = True
    with pytest.raises(ValueError, match="invalid blinded missingness"):
        _check(payload)

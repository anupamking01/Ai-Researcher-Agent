"""Synthetic fail-closed contracts for direct human-analysis statistics helpers.

No human annotations, treatment outputs, or frozen analysis results are used.
The production path also verifies its retained blinded ratings freeze.
"""
import math

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as core


def _row(annotator, blind_id, value="3"):
    return {
        "annotator_id": annotator,
        "blind_id": blind_id,
        "notes": "",
        **{field: value for field in core.DIMS},
    }


@pytest.mark.parametrize("bad_score", ["0", "-1", "6", "NaN", "Infinity", "2.5", "true"])
def test_direct_report_aggregation_rejects_outside_frozen_rubric(bad_score):
    rows = [_row("annotator-a", "H001", bad_score), _row("annotator-b", "H001")]
    with pytest.raises(ValueError, match="integer from 1 to 5|outside the 1-5 rubric"):
        core.report_scores(rows)


def test_direct_report_aggregation_rejects_duplicate_annotator_weighting():
    rows = [
        _row("annotator-a", "H001", "1"),
        _row("annotator-a", "H001", "5"),
        _row("annotator-b", "H001", "3"),
    ]
    with pytest.raises(ValueError, match="duplicate independent rating"):
        core.report_scores(rows)


def test_direct_report_aggregation_rejects_identity_aliases():
    rows = [_row("ANNOTATOR-a", "H001"), _row("annotator-a", "H001")]
    with pytest.raises(ValueError, match="canonically equivalent"):
        core.report_scores(rows)


@pytest.mark.parametrize("missing_identity", ["annotator_id", "blind_id"])
def test_direct_report_aggregation_rejects_missing_identity(missing_identity):
    row = _row("annotator-a", "H001")
    del row[missing_identity]
    with pytest.raises(ValueError, match="nonempty annotator_id and blind_id"):
        core.report_scores([row])


def test_direct_report_scores_preserve_observed_mean_and_missingness():
    rows = [_row("annotator-a", "H001", "2"), _row("annotator-b", "H001", "4")]
    rows[0][core.DIMS[0]] = ""
    scores, counts = core.report_scores(rows)
    assert scores[("H001", core.DIMS[0])] == 4
    assert counts[("H001", core.DIMS[0])] == 1
    assert scores[("H001", core.DIMS[1])] == 3
    assert counts[("H001", core.DIMS[1])] == 2
    assert core.score(_row("annotator-a", "H002", ""), core.DIMS[0]) is None


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True, None, "3", 0, 6])
def test_direct_paired_summary_rejects_invalid_report_means(invalid):
    with pytest.raises(ValueError, match="must be finite and within the 1–5 rubric"):
        core._paired_summary([2.0, invalid], [3.0, 4.0], seed=core.SEED)


@pytest.mark.parametrize("invalid_seed", [True, 1.5, "20260925"])
def test_direct_paired_summary_requires_integer_bootstrap_seed(invalid_seed):
    with pytest.raises(ValueError, match="seed must be an integer"):
        core._paired_summary([2.0], [3.0], seed=invalid_seed)


def test_direct_paired_summary_preserves_fractional_report_means():
    result = core._paired_summary([1.5, 3.5], [2.5, 4.5], seed=core.SEED)
    assert result["n_pairs"] == 2
    assert result["mean_difference"] == 1.0
    assert result["bootstrap_95pct_ci_mean_difference"] == [1.0, 1.0]
    assert result["paired_dz"] is None

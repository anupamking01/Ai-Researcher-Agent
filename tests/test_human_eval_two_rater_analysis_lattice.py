"""Synthetic two-rater/half-point domain cases for direct human-analysis helpers.

This is defense in depth for direct callers; it is not a substitute for blinded
freeze verification and does not invent or summarize collected human ratings.
"""
import pytest

from scripts import human_eval_analysis_core as core


def row(annotator, blind_id, value="3"):
    return {
        "annotator_id": annotator,
        "blind_id": blind_id,
        "notes": "",
        **{field: value for field in core.DIMS},
    }


@pytest.mark.parametrize("scores", [("2", "3", "4"), ("2", "3", "3"), ("2", "4", "4")])
def test_three_distinct_raters_on_one_report_cannot_change_frozen_mean(scores):
    records = [row(f"rater-{i}", "H001", value) for i, value in enumerate(scores)]
    with pytest.raises(ValueError, match="frozen two-annotator analysis plan"):
        core.report_scores(records)


def test_third_rater_on_different_report_cannot_change_rater_population():
    records = [row("rater-a", "H001"), row("rater-b", "H001"), row("rater-c", "H002")]
    with pytest.raises(ValueError, match="frozen two-annotator analysis plan"):
        core.report_scores(iter(records))


def test_frozen_two_raters_preserve_observed_half_point_means_and_blanks():
    records = [
        row("rater-a", "H001", "2"),
        row("rater-b", "H001", "3"),
        row("rater-a", "H002", "4"),
    ]
    records[2][core.DIMS[0]] = ""
    records[2]["notes"] = "The report does not contain evidence for this dimension."
    scores, counts = core.report_scores(records)
    assert scores[("H001", core.DIMS[0])] == 2.5
    assert counts[("H001", core.DIMS[0])] == 2
    assert scores[("H002", core.DIMS[0])] is None
    assert counts[("H002", core.DIMS[0])] == 0
    assert scores[("H002", core.DIMS[1])] == 4
    assert counts[("H002", core.DIMS[1])] == 1


@pytest.mark.parametrize("off_lattice", [1.25, 2.75, 3.125, 4.99999999])
@pytest.mark.parametrize("side", ["left", "right"])
def test_paired_helper_rejects_impossible_report_means_without_rounding(off_lattice, side):
    left, right = [2.5], [3.0]
    (left if side == "left" else right)[0] = off_lattice
    with pytest.raises(ValueError, match="frozen half-point rubric lattice"):
        core._paired_summary(left, right, seed=core.SEED)


@pytest.mark.parametrize("score", [1, 1.5, 2, 2.5, 3.5, 4, 4.5, 5])
def test_paired_helper_preserves_valid_frozen_report_score_values(score):
    result = core._paired_summary([score], [score], seed=core.SEED)
    assert result["n_pairs"] == 1
    assert result["mean_difference"] == 0
    assert result["paired_dz"] is None


def test_huge_integer_is_rejected_with_controlled_rubric_error():
    with pytest.raises(ValueError, match="finite and within the 1–5 rubric"):
        core._paired_summary([10**400], [2], seed=core.SEED)

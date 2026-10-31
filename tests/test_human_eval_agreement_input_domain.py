"""Fail-closed agreement-helper controls (synthetic input; no human ratings)."""

import pytest

from scripts import freeze_human_eval_ratings as freeze


def _row(annotator, blind_id, score="3"):
    # Synthetic endpoint/missingness fixtures satisfy the frozen rubric note
    # requirement unless a test explicitly exercises missing explanations.
    notes = "Synthetic evidence explanation." if score in ("1", "5", "") else ""
    return {
        "annotator_id": annotator,
        "blind_id": blind_id,
        **{field: score for field in freeze.SCORE_FIELDS},
        "notes": notes,
    }


@pytest.mark.parametrize(
    "invalid",
    ["0", "-1", "6", "1.0", "NaN", "True", "+0"],
)
def test_direct_agreement_helper_rejects_invalid_rubric_scores(invalid):
    rows = [_row("rater-a", "H001", invalid), _row("rater-b", "H001", "3")]
    with pytest.raises(ValueError, match="integer from 1 to 5|outside the 1-5 rubric"):
        freeze.build_agreement(rows)


def test_direct_agreement_checks_unpaired_rows_too():
    rows = [
        _row("rater-a", "H001", "3"),
        _row("rater-b", "H001", "3"),
        _row("rater-a", "H002", "0"),
    ]
    with pytest.raises(ValueError, match="outside the 1-5 rubric"):
        freeze.build_agreement(rows)


@pytest.mark.parametrize("invalid", [0, -1, 6, True, 2.5, "3"])
def test_direct_kappa_rejects_out_of_domain_or_noninteger_scores(invalid):
    with pytest.raises(ValueError, match="two integer rubric scores"):
        freeze.quadratic_weighted_kappa([(invalid, 3), (3, 3)])


@pytest.mark.parametrize("bad_pair", [(2,), (1, 2, 3), "12"])
def test_direct_kappa_rejects_nonpair_entries(bad_pair):
    with pytest.raises(ValueError, match="two integer rubric scores"):
        freeze.quadratic_weighted_kappa([bad_pair])


def test_duplicate_direct_agreement_rows_fail_without_last_write_wins():
    rows = [
        _row("rater-a", "H001", "1"),
        _row("rater-a", "H001", "5"),
        _row("rater-b", "H001", "3"),
    ]
    with pytest.raises(ValueError, match="duplicate independent rating"):
        freeze.build_agreement(rows)


def test_valid_helper_inputs_preserve_frozen_agreement_semantics():
    rows = [
        _row("rater-a", "H001", "2"),
        _row("rater-b", "H001", "2"),
        _row("rater-a", "H002", "3"),
        _row("rater-b", "H002", "4"),
    ]
    agreement = freeze.build_agreement(rows)
    field = agreement["pairwise"][0]["dimensions"][freeze.SCORE_FIELDS[0]]
    assert field["n_double_rated"] == 2
    assert field["raw_exact_agreement"] == 0.5
    assert field["mean_absolute_difference"] == 0.5
    assert freeze.quadratic_weighted_kappa([(3, 3), (3, 3)]) is None


def test_blank_dimension_remains_missing_for_direct_helper():
    rows = [_row("rater-a", "H001", ""), _row("rater-b", "H001", "3")]
    field = freeze.build_agreement(rows)["pairwise"][0]["dimensions"][freeze.SCORE_FIELDS[0]]
    assert field["n_double_rated"] == 0
    assert field["raw_exact_agreement"] is None
    assert field["quadratic_weighted_cohen_kappa"] is None

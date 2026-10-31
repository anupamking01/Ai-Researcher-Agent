"""Synthetic pre-unblinding agreement missingness partition contract.

No participant data, treatment labels, or frozen analysis outputs are used.
"""
from __future__ import annotations

import pytest

from scripts import freeze_human_eval_ratings as freeze


DIMENSION = freeze.SCORE_FIELDS[0]
NOTE = "Synthetic fixture explanation for this score or missing dimension."


def _rating(annotator: str, blind_id: str, first_score: str) -> dict[str, str]:
    return {
        "annotator_id": annotator,
        "blind_id": blind_id,
        **{field: (first_score if field == DIMENSION else "3")
           for field in freeze.SCORE_FIELDS},
        "notes": NOTE,
    }


def _paired_rows(cells):
    return [
        _rating(annotator, f"H{index:03d}", value)
        for index, (a_value, b_value) in enumerate(cells, start=1)
        for annotator, value in (("annotator-a", a_value), ("annotator-b", b_value))
    ]


def _block(rows, *, field=DIMENSION):
    pair = freeze.build_agreement(rows)["pairwise"][0]
    return pair["n_shared_items"], pair["dimensions"][field]


def test_partition_exposes_asymmetric_and_joint_dimension_missingness():
    # H001/H005 have two ratings; H002 is B-only; H003 A-only;
    # H004 has two documented blanks. Exactly two reports enter kappa.
    rows = _paired_rows([("3", "3"), ("", "2"), ("4", ""), ("", ""), ("5", "4")])
    n_shared, block = _block(rows)
    assert n_shared == 5
    assert block["n_double_rated"] == 2
    assert block["n_annotator_a_only_rated"] == 1
    assert block["n_annotator_b_only_rated"] == 1
    assert block["n_neither_rated"] == 1
    assert block["raw_exact_agreement"] == 0.5
    assert block["mean_absolute_difference"] == 0.5
    assert sum(block[key] for key in (
        "n_double_rated",
        "n_annotator_a_only_rated",
        "n_annotator_b_only_rated",
        "n_neither_rated",
    )) == n_shared
    _, unaffected_dimension = _block(rows, field=freeze.SCORE_FIELDS[1])
    assert unaffected_dimension["n_double_rated"] == n_shared
    assert all(unaffected_dimension[key] == 0 for key in (
        "n_annotator_a_only_rated",
        "n_annotator_b_only_rated",
        "n_neither_rated",
    ))


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("3", "4", (1, 0, 0, 0)),
        ("3", "", (0, 1, 0, 0)),
        ("", "4", (0, 0, 1, 0)),
        ("", "", (0, 0, 0, 1)),
    ],
)
def test_each_single_item_state_has_exactly_one_coverage_bucket(a, b, expected):
    n_shared, block = _block(_paired_rows([(a, b)]))
    observed = tuple(block[key] for key in (
        "n_double_rated",
        "n_annotator_a_only_rated",
        "n_annotator_b_only_rated",
        "n_neither_rated",
    ))
    assert n_shared == 1
    assert observed == expected
    if not block["n_double_rated"]:
        assert block["raw_exact_agreement"] is None
        assert block["mean_absolute_difference"] is None
        assert block["quadratic_weighted_cohen_kappa"] is None


def test_missingness_counts_are_row_order_and_iterator_independent():
    rows = _paired_rows([("", "2"), ("4", ""), ("3", "3"), ("", "")])
    result = freeze.build_agreement(rows)
    assert freeze.build_agreement(reversed(rows)) == result
    assert freeze.build_agreement(row for row in rows) == result


def test_pair_specific_partition_does_not_count_nonshared_blind_ids():
    rows = [
        _rating("annotator-a", "H001", "4"),
        _rating("annotator-b", "H002", "2"),
    ]
    shared, block = _block(rows)
    assert shared == 0
    assert all(block[key] == 0 for key in (
        "n_double_rated",
        "n_annotator_a_only_rated",
        "n_annotator_b_only_rated",
        "n_neither_rated",
    ))
    assert block["raw_exact_agreement"] is None


def test_incomplete_pairs_never_inflate_agreement_estimate():
    _, block = _block(_paired_rows([("3", "3"), ("", "5"), ("1", ""), ("", "")]))
    assert block["n_double_rated"] == 1
    assert block["raw_exact_agreement"] == 1.0
    assert block["mean_absolute_difference"] == 0.0
    assert block["quadratic_weighted_cohen_kappa"] is None
    assert (block["n_annotator_a_only_rated"],
            block["n_annotator_b_only_rated"],
            block["n_neither_rated"]) == (1, 1, 1)

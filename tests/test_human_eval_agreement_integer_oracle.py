"""Synthetic-only independent oracle for pre-unblinding ordinal agreement.

No historical reports or human ratings are read or generated. The exact integer
oracle does not import any internal contingency-table or expected-weight code.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product

import pytest

from scripts.freeze_human_eval_ratings import (
    SCORE_FIELDS,
    build_agreement,
    quadratic_weighted_kappa,
)


def _independent_rational_oracle(pairs):
    """Compute weighted kappa directly from all pairwise score distances."""
    if not pairs:
        return None
    left = [a for a, _ in pairs]
    right = [b for _, b in pairs]
    observed = sum((a - b) ** 2 for a, b in pairs)
    independent_marginal_distance = sum(
        (a - b) ** 2 for a in left for b in right
    )
    if independent_marginal_distance == 0:
        return None
    return Fraction(
        independent_marginal_distance - len(pairs) * observed,
        independent_marginal_distance,
    )


@pytest.mark.parametrize("length", (1, 2, 3))
def test_kappa_matches_independent_exact_rational_oracle_exhaustively(length):
    # Enumerate all 9**length ordered paired profiles on a spread-out
    # 1/3/5 rubric, including perfect, inverse, and undefined marginals.
    score_pairs = tuple(product((1, 3, 5), repeat=2))
    for pairs in product(score_pairs, repeat=length):
        expected = _independent_rational_oracle(pairs)
        result = quadratic_weighted_kappa(list(pairs))
        if expected is None:
            assert result is None
        else:
            assert result == pytest.approx(float(expected), abs=1e-12)


def test_kappa_is_rater_symmetric_and_item_order_invariant():
    pairs = [(1, 4), (3, 2), (5, 5), (2, 4)]
    baseline = quadratic_weighted_kappa(pairs)
    assert baseline is not None
    assert quadratic_weighted_kappa(list(reversed(pairs))) == pytest.approx(baseline)
    assert quadratic_weighted_kappa([(b, a) for a, b in pairs]) == pytest.approx(baseline)
    assert quadratic_weighted_kappa(
        [(6 - a, 6 - b) for a, b in pairs]
    ) == pytest.approx(baseline)


def _row(annotator, blind_id, correctness):
    row = {
        "annotator_id": annotator,
        "blind_id": blind_id,
        **{field: "3" for field in SCORE_FIELDS},
        "notes": "Insufficient source material to assign a score." if not correctness else "",
    }
    row["correctness_1_5"] = correctness
    return row


def test_blinded_agreement_keeps_all_missingness_denominators_separate():
    rows = [
        _row("rater_a", "blind-01", "4"),
        _row("rater_b", "blind-01", "4"),
        _row("rater_a", "blind-02", "3"),
        _row("rater_b", "blind-02", ""),
        _row("rater_a", "blind-03", ""),
        _row("rater_b", "blind-03", "2"),
        _row("rater_a", "blind-04", ""),
        _row("rater_b", "blind-04", ""),
    ]
    result = build_agreement(rows)
    assert result["status"] == "pre-unblinding_pairwise_agreement"
    assert result["n_annotators"] == 2
    assert result["requires_predeclared_multi_rater_statistic"] is False
    pair = result["pairwise"][0]
    assert pair["n_shared_items"] == 4
    dimension = pair["dimensions"]["correctness_1_5"]
    assert dimension["n_double_rated"] == 1
    assert dimension["n_annotator_a_only_rated"] == 1
    assert dimension["n_annotator_b_only_rated"] == 1
    assert dimension["n_neither_rated"] == 1
    assert dimension["raw_exact_agreement"] == 1.0
    assert dimension["mean_absolute_difference"] == 0.0
    # One identical observed pair has zero expected weighted disagreement:
    # this is undefined kappa, not perfect reliability (kappa=1).
    assert dimension["quadratic_weighted_cohen_kappa"] is None


def test_kappa_rejects_nonordinal_direct_inputs():
    for invalid in ([(0, 2)], [(True, 3)], [(1.0, 4)], [(5, 6)], [(2,)]):
        with pytest.raises(ValueError, match="integer rubric scores"):
            quadratic_weighted_kappa(invalid)

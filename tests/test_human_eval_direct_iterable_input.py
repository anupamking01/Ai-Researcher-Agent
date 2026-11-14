"""Synthetic regression tests for bounded, one-pass direct human-rating inputs.

This tests only statistics-helper input custody; it does not read a human freeze,
unblind a packet, rerun a treatment, or invent an annotation.
"""
import pytest

from scripts import human_eval_analysis_core as core


def _row(annotator, blind_id, value="3"):
    return {
        "annotator_id": annotator,
        "blind_id": blind_id,
        "notes": "",
        **{field: value for field in core.DIMS},
    }


def test_one_shot_iterator_preserves_all_independent_ratings():
    rows = (
        row
        for row in [
            _row("rater-a", "H001", "2"),
            _row("rater-b", "H001", "4"),
            _row("rater-a", "H002", "3"),
            _row("rater-b", "H002", "4"),
        ]
    )
    scores, counts = core.report_scores(rows)
    assert scores[("H001", core.DIMS[0])] == 3
    assert counts[("H001", core.DIMS[0])] == 2
    assert scores[("H002", core.DIMS[0])] == 3.5
    assert counts[("H002", core.DIMS[0])] == 2


def test_one_shot_iterator_cannot_hide_duplicate_rater_weight():
    rows = (row for row in [_row("rater-a", "H001"), _row("rater-a", "H001")])
    with pytest.raises(ValueError, match="duplicate independent rating"):
        core.report_scores(rows)


def test_one_shot_iterator_cannot_hide_canonical_identity_aliases():
    rows = (row for row in [_row("RATER-A", "H001"), _row("rater-a", "H002")])
    with pytest.raises(ValueError, match="canonically equivalent"):
        core.report_scores(rows)


def test_one_shot_iterator_cannot_hide_invalid_last_score():
    rows = (row for row in [_row("rater-a", "H001"), _row("rater-b", "H001", "6")])
    with pytest.raises(ValueError, match="integer from 1 to 5|outside the 1-5 rubric"):
        core.report_scores(rows)


@pytest.mark.parametrize("as_generator", [False, True])
def test_empty_inputs_fail_instead_of_returning_empty_evidence(as_generator):
    rows = (row for row in []) if as_generator else []
    with pytest.raises(ValueError, match="must not be empty"):
        core.report_scores(rows)


@pytest.mark.parametrize("invalid", [None, 42, True])
def test_non_iterable_input_has_explicit_error(invalid):
    with pytest.raises(ValueError, match="must be iterable"):
        core.report_scores(invalid)


def test_oversized_single_pass_input_fails_before_truncating_evidence():
    produced = []

    def rows():
        for index in range(core.MAX_DIRECT_RATING_ROWS + 1):
            produced.append(index)
            yield _row(f"rater-{index:03d}", f"H{index:03d}")

    with pytest.raises(ValueError, match="frozen 80-record limit"):
        core.report_scores(rows())
    assert len(produced) == core.MAX_DIRECT_RATING_ROWS + 1


def test_exact_capacity_is_accepted_without_spurious_truncation():
    # This is a direct helper test, not a claim that genuine human ratings exist.
    rows = (
        _row(f"rater-{index % 2}", f"H{index // 2:03d}")
        for index in range(core.MAX_DIRECT_RATING_ROWS)
    )
    scores, counts = core.report_scores(rows)
    assert len(scores) == 40 * len(core.DIMS)
    assert all(count == 2 for count in counts.values())

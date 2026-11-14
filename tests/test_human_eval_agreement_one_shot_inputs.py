"""Synthetic direct agreement input-integrity checks; no human ratings."""

from itertools import repeat

import pytest

from scripts import freeze_human_eval_ratings as freeze


def row(annotator="rater-a", blind="H001", score="3"):
    return {
        "annotator_id": annotator,
        "blind_id": blind,
        **{field: score for field in freeze.SCORE_FIELDS},
        "notes": "",
    }


def pair():
    return [row("rater-a"), row("rater-b")]


def test_generator_produces_identical_agreement_to_list():
    ratings = [
        row("rater-a", "H001", "2"),
        row("rater-b", "H001", "3"),
        row("rater-a", "H002", "3"),
        row("rater-b", "H002", "3"),
    ]
    result = freeze.build_agreement(iter(ratings))
    assert result == freeze.build_agreement(ratings)
    assert result["n_annotators"] == 2
    assert result["pairwise"][0]["n_shared_items"] == 2
    assert result["pairwise"][0]["dimensions"]["correctness_1_5"]["n_double_rated"] == 2


def test_single_use_iterable_is_iterated_exactly_once():
    class Once:
        def __init__(self):
            self.calls = 0

        def __iter__(self):
            self.calls += 1
            if self.calls != 1:
                raise AssertionError("one-shot source was traversed again")
            return iter(pair())

    source = Once()
    assert freeze.build_agreement(source)["n_annotators"] == 2
    assert source.calls == 1


@pytest.mark.parametrize("values", [[], iter(())])
def test_empty_sources_fail_instead_of_reporting_zero_raters(values):
    with pytest.raises(ValueError, match="must not be empty"):
        freeze.build_agreement(values)


@pytest.mark.parametrize("invalid", [None, 42, object()])
def test_noniterable_sources_fail_explicitly(invalid):
    with pytest.raises(ValueError, match="must be iterable"):
        freeze.build_agreement(invalid)


def test_generator_adverse_row_still_fails_closed():
    def stream():
        yield row("rater-a")
        bad = row("rater-b")
        bad["correctness_1_5"] = "6"
        yield bad

    with pytest.raises(ValueError, match="outside the 1-5 rubric"):
        freeze.build_agreement(stream())


def test_generator_duplicate_rating_still_fails_closed():
    def stream():
        yield row("rater-a")
        yield row("rater-a")
        yield row("rater-b")

    with pytest.raises(ValueError, match="duplicate independent rating"):
        freeze.build_agreement(stream())


def test_multi_rater_diagnostic_preserves_all_pairs():
    outcome = freeze.build_agreement(
        (row(identity) for identity in ("rater-a", "rater-b", "rater-c"))
    )
    assert outcome["n_annotators"] == 3
    assert len(outcome["pairwise"]) == 3
    assert outcome["requires_predeclared_multi_rater_statistic"] is True


def test_over_limit_stream_is_consumed_only_to_first_excess_record():
    seen = 0

    def stream():
        nonlocal seen
        for _ in range(freeze.MAX_DIRECT_AGREEMENT_ROWS + 100):
            seen += 1
            yield row()

    with pytest.raises(ValueError, match="record safety limit"):
        freeze.build_agreement(stream())
    assert seen == freeze.MAX_DIRECT_AGREEMENT_ROWS + 1


def test_unbounded_iterator_is_rejected_without_exhaustion():
    with pytest.raises(ValueError, match="record safety limit"):
        freeze.build_agreement(repeat(row()))


def test_exact_bound_does_not_trigger_safety_limit():
    rows = (
        row(
            "rater-a" if index % 2 == 0 else "rater-b",
            f"H{index // 2:04d}",
        )
        for index in range(freeze.MAX_DIRECT_AGREEMENT_ROWS)
    )
    result = freeze.build_agreement(rows)
    assert result["n_annotators"] == 2
    assert result["pairwise"][0]["n_shared_items"] == freeze.MAX_DIRECT_AGREEMENT_ROWS // 2
    assert result["requires_predeclared_multi_rater_statistic"] is False

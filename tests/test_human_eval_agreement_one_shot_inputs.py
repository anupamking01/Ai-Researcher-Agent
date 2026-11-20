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


@pytest.mark.parametrize("use_generator", [False, True])
@pytest.mark.parametrize("n_items", [1, 2])
def test_single_annotator_cannot_produce_pairwise_agreement_receipt(
    use_generator, n_items
):
    # Both list and one-pass direct callers must not turn one human rater into
    # an apparently successful pre-unblinding inter-annotator analysis.
    ratings = [row("rater-a", f"H{index:03d}", "3") for index in range(1, n_items + 1)]
    source = (item for item in ratings) if use_generator else ratings
    with pytest.raises(ValueError, match="at least two independent annotators"):
        freeze.build_agreement(source)


def test_two_distinct_annotators_preserve_missing_overlap_diagnostics():
    # Zero overlapping reports must remain explicitly visible as zero shared
    # items, rather than being mistaken for the forbidden single-rater case.
    result = freeze.build_agreement(
        [row("rater-a", "H001", "3"), row("rater-b", "H002", "3")]
    )
    assert result["n_annotators"] == 2
    assert len(result["pairwise"]) == 1
    pair = result["pairwise"][0]
    assert pair["n_shared_items"] == 0
    assert all(
        summary["quadratic_weighted_cohen_kappa"] is None
        for summary in pair["dimensions"].values()
    )


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
    # The generated H001-H999 namespace has fewer than 4,096 unique labels.
    # Spread the exact-bound stream across synthetic raters while retaining
    # unique (annotator, report) pairs and valid generated identifiers.
    identifiers_per_rater = 999
    rows = (
        row(
            f"rater-{index // identifiers_per_rater + 1:02d}",
            f"H{index % identifiers_per_rater + 1:03d}",
        )
        for index in range(freeze.MAX_DIRECT_AGREEMENT_ROWS)
    )
    result = freeze.build_agreement(rows)
    expected_raters = (
        freeze.MAX_DIRECT_AGREEMENT_ROWS + identifiers_per_rater - 1
    ) // identifiers_per_rater
    assert result["n_annotators"] == expected_raters
    assert len(result["pairwise"]) == expected_raters * (expected_raters - 1) // 2
    assert result["pairwise"][0]["n_shared_items"] == identifiers_per_rater
    assert result["pairwise"][-1]["n_shared_items"] == (
        freeze.MAX_DIRECT_AGREEMENT_ROWS % identifiers_per_rater
    )
    # The resource-bound fixture is NOT a two-rater reliability claim.
    assert result["requires_predeclared_multi_rater_statistic"] is True


def test_exact_rater_fanout_bound_preserves_exploratory_pairwise_diagnostics():
    # Every row is independently identified but the 64-rater ceiling is an
    # engineering resource limit, not a valid human-study design or finding.
    limit = freeze.MAX_DIRECT_AGREEMENT_RATERS
    result = freeze.build_agreement(
        row(f"rater-{index:03d}") for index in range(limit)
    )
    assert result["n_annotators"] == limit
    assert len(result["pairwise"]) == limit * (limit - 1) // 2
    assert result["requires_predeclared_multi_rater_statistic"] is True


def test_excess_distinct_raters_fail_before_pairwise_enumeration(monkeypatch):
    # The raw input is far below the 4,096-row ceiling; this exercises the
    # separate O(raters**2) output-growth guard. No pairwise work may begin.
    def forbidden_pairs(*args, **kwargs):
        raise AssertionError("pairwise enumeration started on oversized input")

    monkeypatch.setattr(freeze, "combinations", forbidden_pairs)
    rows = (
        row(f"rater-{index:03d}")
        for index in range(freeze.MAX_DIRECT_AGREEMENT_RATERS + 1)
    )
    with pytest.raises(ValueError, match="rater pairwise safety limit"):
        freeze.build_agreement(rows)


def test_item_coverage_discloses_unshared_reports_separately_from_score_missingness():
    # Shared-item dimension missingness is not the same as a whole report
    # absent from one annotator's submissions. Keep both denominators visible.
    missing = row("rater-b", "H002")
    missing["correctness_1_5"] = ""
    missing["notes"] = "The available evidence does not support a correctness judgment."
    ratings = [
        row("rater-a", "H001"),
        row("rater-a", "H002"),
        missing,
        row("rater-b", "H003"),
    ]
    result = freeze.build_agreement(iter(ratings))
    pairwise = result["pairwise"][0]
    assert (pairwise["annotator_a"], pairwise["annotator_b"]) == (
        "rater-a", "rater-b"
    )
    assert pairwise["n_shared_items"] == 1
    assert pairwise["n_union_items"] == 3
    assert pairwise["n_items_only_annotator_a"] == 1
    assert pairwise["n_items_only_annotator_b"] == 1
    correctness = pairwise["dimensions"]["correctness_1_5"]
    assert correctness["n_annotator_a_only_rated"] == 1
    assert correctness["n_annotator_b_only_rated"] == 0
    assert correctness["n_double_rated"] == 0
    assert correctness["quadratic_weighted_cohen_kappa"] is None
    assert pairwise["dimensions"]["clarity_1_5"]["n_double_rated"] == 1


def test_item_coverage_distinguishes_complete_from_disjoint_rater_assignments():
    complete = freeze.build_agreement(pair())["pairwise"][0]
    assert complete["n_shared_items"] == complete["n_union_items"] == 1
    assert complete["n_items_only_annotator_a"] == 0
    assert complete["n_items_only_annotator_b"] == 0

    disjoint = freeze.build_agreement(
        [row("rater-a", "H001"), row("rater-b", "H002")]
    )["pairwise"][0]
    assert disjoint["n_shared_items"] == 0
    assert disjoint["n_union_items"] == 2
    assert disjoint["n_items_only_annotator_a"] == 1
    assert disjoint["n_items_only_annotator_b"] == 1
    assert all(
        value["n_double_rated"] == 0
        for value in disjoint["dimensions"].values()
    )

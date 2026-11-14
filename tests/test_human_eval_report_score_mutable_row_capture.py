"""Synthetic regression cases for aliased mutable post-unblinding rating inputs.

This protects the direct report-level aggregation helper, not the separately
verified production CSV freeze, and never opens real treatment identities.
"""
import pytest

from scripts import human_eval_analysis_core as core


def _row(annotator, blind_id, value="3"):
    return {
        "annotator_id": annotator,
        "blind_id": blind_id,
        **{field: value for field in core.DIMS},
        "notes": "",
    }


def _reused_buffer(rows, *, buffer=None):
    shared = {} if buffer is None else buffer
    for source in rows:
        shared.clear()
        shared.update(source)
        yield shared


def test_reused_buffer_yields_same_report_means_as_independent_rows():
    originals = [
        _row("rater-a", "H001", "2"),
        _row("rater-b", "H001", "4"),
        _row("rater-a", "H002", "3"),
        _row("rater-b", "H002", "4"),
    ]
    assert core.report_scores(_reused_buffer(originals)) == core.report_scores(originals)


def test_reused_buffer_preserves_separate_blind_report_identifiers():
    originals = [_row("rater-a", "H001", "2"), _row("rater-a", "H002", "4")]
    scores, counts = core.report_scores(_reused_buffer(originals))
    assert scores[("H001", core.DIMS[0])] == 2
    assert scores[("H002", core.DIMS[0])] == 4
    assert counts[("H001", core.DIMS[0])] == 1
    assert counts[("H002", core.DIMS[0])] == 1


def test_reused_buffer_does_not_erase_early_invalid_score():
    originals = [_row("rater-a", "H001", "6"), _row("rater-b", "H002")]
    with pytest.raises(ValueError, match="integer from 1 to 5|outside the 1-5 rubric"):
        core.report_scores(_reused_buffer(originals))


def test_reused_buffer_does_not_erase_early_unblinding_column():
    first = _row("rater-a", "H001")
    first["variant_id"] = "P6V"
    with pytest.raises(ValueError, match="direct rating row schema mismatch"):
        core.report_scores(_reused_buffer([first, _row("rater-b", "H002")]))


def test_reused_buffer_preserves_early_missing_dimension_reason():
    first = _row("rater-a", "H001", "3")
    first[core.DIMS[0]] = ""
    first["notes"] = "There is insufficient information to score this dimension."
    second = _row("rater-b", "H001", "4")
    scores, counts = core.report_scores(_reused_buffer([first, second]))
    assert scores[("H001", core.DIMS[0])] == 4
    assert counts[("H001", core.DIMS[0])] == 1
    assert scores[("H001", core.DIMS[1])] == 3.5
    assert counts[("H001", core.DIMS[1])] == 2


def test_direct_capture_does_not_mutate_caller_rows():
    originals = [_row("rater-a", "H001", "2"), _row("rater-b", "H001", "4")]
    before = [row.copy() for row in originals]
    core.report_scores(_reused_buffer(originals))
    assert originals == before


def test_builtin_copy_bypasses_mutable_dictionary_subclass_copy_override():
    class MutableBuffer(dict):
        def copy(self):
            raise AssertionError("subclass copy must not run")

    originals = [_row("rater-a", "H001", "2"), _row("rater-b", "H001", "4")]
    scores, _ = core.report_scores(_reused_buffer(originals, buffer=MutableBuffer()))
    assert scores[("H001", core.DIMS[0])] == 3


def test_already_collapsed_aliases_cannot_be_recovered():
    record = _row("rater-a", "H001")
    collapsed = [record, record]
    with pytest.raises(ValueError, match="duplicate independent rating"):
        core.report_scores(collapsed)


def test_alias_capture_remains_bounded_at_first_excess_record():
    produced = []

    def rows():
        shared = {}
        for index in range(core.MAX_DIRECT_RATING_ROWS + 10):
            produced.append(index)
            shared.clear()
            shared.update(_row(f"rater-{index:03d}", f"H{index:03d}"))
            yield shared

    with pytest.raises(ValueError, match="frozen 80-record limit"):
        core.report_scores(rows())
    assert len(produced) == core.MAX_DIRECT_RATING_ROWS + 1


def test_non_dictionary_iterable_item_remains_rejected():
    with pytest.raises(ValueError, match="nonempty annotator_id and blind_id"):
        core.report_scores(iter([_row("rater-a", "H001"), 123]))

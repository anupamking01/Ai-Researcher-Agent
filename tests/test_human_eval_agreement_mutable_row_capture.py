"""Synthetic regression tests for reused-buffer blinded agreement iterators.

These are deliberately fabricated *test fixtures*, not human annotations.
The frozen CSV importer and study estimands are not modified.
"""

from itertools import repeat

import pytest

from scripts import freeze_human_eval_ratings as freeze


def _row(annotator="annotator-a", blind="H001", score="3"):
    return {
        "annotator_id": annotator,
        "blind_id": blind,
        **{field: score for field in freeze.SCORE_FIELDS},
        "notes": "",
    }


def _reusing_buffer(records, *, buffer_class=dict):
    """Emulate an iterator that updates one dictionary before every yield."""
    buffer = buffer_class()
    for record in records:
        buffer.clear()
        buffer.update(record)
        yield buffer


def test_reused_dictionary_buffer_matches_independent_rating_snapshots():
    records = [
        _row("annotator-a", "H001", "2"),
        _row("annotator-b", "H001", "3"),
        _row("annotator-a", "H002", "4"),
        _row("annotator-b", "H002", "4"),
    ]
    expected = freeze.build_agreement(records)
    observed = freeze.build_agreement(_reusing_buffer(records))
    assert observed == expected
    assert observed["n_annotators"] == 2
    assert observed["pairwise"][0]["n_shared_items"] == 2
    dim = observed["pairwise"][0]["dimensions"]["correctness_1_5"]
    assert dim["n_double_rated"] == 2
    assert dim["raw_exact_agreement"] == 0.5
    assert dim["mean_absolute_difference"] == 0.5


def test_invalid_earlier_yield_is_not_erased_by_later_valid_buffer_contents():
    records = [
        _row("annotator-a", "H001", "6"),
        _row("annotator-b", "H001", "3"),
    ]
    with pytest.raises(ValueError, match="outside the 1-5 rubric"):
        freeze.build_agreement(_reusing_buffer(records))


def test_treatment_leakage_in_earlier_yield_is_not_erased_by_later_rewrite():
    first = _row("annotator-a", "H001")
    first["variant_id"] = "P6V"
    with pytest.raises(ValueError, match="rating schema mismatch"):
        freeze.build_agreement(_reusing_buffer([first, _row("annotator-b")]))


def test_reused_buffer_does_not_change_original_input_records():
    records = [_row("annotator-a", "H001", "2"), _row("annotator-b", "H001", "4")]
    before = [dict(record) for record in records]
    freeze.build_agreement(_reusing_buffer(records))
    assert records == before


def test_direct_agreement_rejects_aliases_already_collapsed_before_call():
    same_record = _row()
    with pytest.raises(ValueError, match="duplicate independent rating"):
        freeze.build_agreement([same_record, same_record])


def test_dictionary_subclass_copy_override_cannot_change_capture():
    class HostileCopy(dict):
        def copy(self):
            raise AssertionError("subclass copy must not govern evidence capture")

    records = [_row("annotator-a"), _row("annotator-b")]
    assert freeze.build_agreement(_reusing_buffer(records, buffer_class=HostileCopy)) == (
        freeze.build_agreement(records)
    )


def test_reused_buffer_iterator_is_not_consumed_beyond_size_ceiling():
    seen = 0
    buffer = _row()

    def unbounded():
        nonlocal seen
        for _ in repeat(None):
            seen += 1
            yield buffer

    with pytest.raises(ValueError, match="record safety limit"):
        freeze.build_agreement(unbounded())
    assert seen == freeze.MAX_DIRECT_AGREEMENT_ROWS + 1


def test_non_dictionary_record_keeps_clear_failure():
    with pytest.raises(ValueError, match="must be a dictionary"):
        freeze.build_agreement(iter([_row(), None]))

"""Synthetic, offline checks that blinded rating notes contain a visible reason.

These are only validation fixtures. No annotators, treatments, or evaluations
have been run, and these examples are not human-submitted ratings.
"""
import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as analysis


def _row(annotator: str, score: str, notes: str) -> dict:
    return {
        "annotator_id": annotator,
        "blind_id": "H001",
        **{field: score for field in freeze.SCORE_FIELDS},
        "notes": notes,
    }


@pytest.mark.parametrize("non_reason", [
    "12345",       # A bare number is not a written reason for a 1/5 score.
    "5/5",         # Repeating the score does not explain it.
    "★",           # A visible symbol alone is not an explanation.
    "⚠",           # An attention symbol alone is not an explanation.
])
def test_rendered_numbers_and_symbols_do_not_satisfy_explanation_gate(non_reason):
    # This helper is shared by the strict CSV freeze importer, direct blinded
    # agreement, and the downstream direct analysis helper.
    assert not freeze._note_has_visible_explanation(non_reason)
    with pytest.raises(ValueError, match="visible explanatory content"):
        freeze.build_agreement([
            _row("rater-a", "5", non_reason),
            _row("rater-b", "3", ""),
        ])
    with pytest.raises(ValueError, match="visible explanatory content"):
        analysis.report_scores([
            _row("rater-a", "5", non_reason),
            _row("rater-b", "3", ""),
        ])


@pytest.mark.parametrize("reason", [
    "This report misses a cited source.",
    "Evidence: source returned 404.",
    "Les preuves sont insuffisantes.",
    "来源缺失，无法核查。",
])
def test_international_visible_reason_survives_shared_rating_guards(reason):
    assert freeze._note_has_visible_explanation(reason)
    rows = [_row("rater-a", "5", reason), _row("rater-b", "3", "")]
    agreement = freeze.build_agreement(rows)
    assert agreement["n_annotators"] == 2
    scores, counts = analysis.report_scores(rows)
    assert scores[("H001", freeze.SCORE_FIELDS[0])] == 4
    assert counts[("H001", freeze.SCORE_FIELDS[0])] == 2

"""Direct pre-unblinding agreement must not silently accept malformed rows.

All values here are synthetic engineering fixtures, not human submissions.
The production frozen importer is independently verified before unblinding.
"""
import pytest

from scripts import freeze_human_eval_ratings as freeze


def row(annotator="rater-a", blind="H001", score="3", notes=""):
    return {
        "annotator_id": annotator,
        "blind_id": blind,
        **{field: score for field in freeze.SCORE_FIELDS},
        "notes": notes,
    }


@pytest.mark.parametrize("missing", ["notes", *freeze.SCORE_FIELDS])
def test_missing_rubric_or_note_column_is_not_treated_as_blanked_score(missing):
    malformed = row()
    del malformed[missing]
    with pytest.raises(ValueError, match="direct agreement rating schema mismatch"):
        freeze.build_agreement([malformed, row("rater-b")])


@pytest.mark.parametrize("extra", ["variant_id", "task_id", "treatment"])
def test_direct_agreement_rejects_unblinding_or_extra_columns(extra):
    malformed = row()
    malformed[extra] = "P6V"
    with pytest.raises(ValueError, match="direct agreement rating schema mismatch"):
        freeze.build_agreement([malformed, row("rater-b")])


@pytest.mark.parametrize("field", ["notes", *freeze.SCORE_FIELDS])
def test_direct_agreement_requires_textual_normalized_fields(field):
    malformed = row()
    malformed[field] = None if field == "notes" else 3
    with pytest.raises(ValueError, match="must all be strings"):
        freeze.build_agreement([malformed, row("rater-b")])


@pytest.mark.parametrize("field", ["annotator_id", "blind_id"])
def test_direct_agreement_rejects_noncanonical_whitespace_identity(field):
    malformed = row()
    malformed[field] = " " + malformed[field]
    with pytest.raises(ValueError, match="nonempty and trimmed"):
        freeze.build_agreement([malformed, row("rater-b")])


@pytest.mark.parametrize("score", ["1", "5", ""])
def test_direct_agreement_rejects_endpoint_or_missing_score_without_explanation(score):
    with pytest.raises(ValueError, match="require explanatory notes"):
        freeze.build_agreement([row(score=score), row("rater-b")])


@pytest.mark.parametrize("notes", ["\u200b", "---", "[]", "   "])
def test_nonexplanatory_notes_do_not_satisfy_endpoint_requirement(notes):
    with pytest.raises(ValueError):
        freeze.build_agreement([
            row(score="5", notes=notes),
            row("rater-b", score="5", notes="Synthetic source comparison."),
        ])


@pytest.mark.parametrize("notes", ["=SUM(1,2)", "Review: P6V was better"])
def test_direct_agreement_notes_cannot_restore_formula_or_treatment_leakage(notes):
    with pytest.raises(ValueError, match="spreadsheet-active|treatment leakage"):
        freeze.build_agreement([
            row(score="5", notes=notes),
            row("rater-b"),
        ])


def test_direct_agreement_preserves_valid_explained_endpoint_and_missingness():
    ratings = [
        row("rater-a", "H001", "5", "All claims have evidence."),
        row("rater-b", "H001", "3"),
        row("rater-a", "H002", "", "Insufficient support to assign a rating."),
        row("rater-b", "H002", "3"),
    ]
    outcome = freeze.build_agreement(ratings)
    dimension = freeze.SCORE_FIELDS[0]
    result = outcome["pairwise"][0]["dimensions"][dimension]
    assert result["n_double_rated"] == 1
    assert result["raw_exact_agreement"] == 0
    assert result["mean_absolute_difference"] == 2
    assert outcome["n_annotators"] == 2


def test_direct_agreement_rejects_non_mapping_row():
    with pytest.raises(ValueError, match="must be a dictionary"):
        freeze.build_agreement([None, row("rater-b")])

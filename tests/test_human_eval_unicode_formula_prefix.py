"""Synthetic regression for normalized spreadsheet formula prefixes in human CSVs.

This checks intake safety only; no human annotations or treatment data are used.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze


def _rating_file(tmp_path: Path, *, notes: str, annotator_id: str = "rater-neutral") -> Path:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(freeze.RATING_FIELDS)
    writer.writerow([
        annotator_id, "H001", "3", "3", "3", "3", "3", notes,
    ])
    path = tmp_path / "synthetic-ratings.csv"
    path.write_bytes(buffer.getvalue().encode("utf-8"))
    return path


@pytest.mark.parametrize(
    "unsafe_prefix",
    [
        "\u200b=",  # Zero-width space before a formula
        "\u2060+",  # Word joiner before a formula
        "\ufeff@",  # Invisible BOM-like formatting character
        "\u034f=",  # Combining grapheme joiner
        "\ufe0f=",  # Variation selector
        "＝",       # NFKC maps fullwidth compatibility signs
        "＋",
        "－",
        "＠",
        "\u200b \u2060＝",  # Mixed whitespace, invisible marks and fullwidth
    ],
)
def test_normalized_formula_prefix_in_notes_rejected_without_mutation(
    tmp_path: Path, unsafe_prefix: str
) -> None:
    ratings = _rating_file(
        tmp_path, notes=unsafe_prefix + "SUM(1,1) synthetic explanation"
    )
    original_bytes = ratings.read_bytes()
    with pytest.raises(ValueError, match=r"notes begins with a spreadsheet-active"):
        freeze._load_ratings(
            [ratings], allowed_blind_ids={"H001"}, require_single_annotator=True
        )
    assert ratings.read_bytes() == original_bytes


@pytest.mark.parametrize("unsafe_id", ["＝rater", "＋rater"])
def test_compatibility_formula_prefix_in_annotator_id_rejected(
    tmp_path: Path, unsafe_id: str
) -> None:
    ratings = _rating_file(tmp_path, notes="", annotator_id=unsafe_id)
    with pytest.raises(ValueError, match=r"annotator_id begins with a spreadsheet-active"):
        freeze._load_ratings(
            [ratings], allowed_blind_ids={"H001"}, require_single_annotator=True
        )


def test_interior_compatibility_symbols_are_allowed_as_plain_text(tmp_path: Path) -> None:
    ratings = _rating_file(
        tmp_path,
        notes="The synthetic example contains ＝ and \u200b= after visible words.",
    )
    rows, _ = freeze._load_ratings(
        [ratings], allowed_blind_ids={"H001"}, require_single_annotator=True
    )
    assert len(rows) == 1
    assert rows[0]["notes"] == (
        "The synthetic example contains ＝ and \u200b= after visible words."
    )
